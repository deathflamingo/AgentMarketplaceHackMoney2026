"""Payment verification service with replay protection and transaction tracking."""

import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.payment_transaction import (
    PaymentTransaction,
    TransactionStatus,
    TransactionType
)
from app.models.agent import Agent
from app.services.chain_service import chain_service
from app.services.agent_service import update_balance, get_agent_by_id
from app.config import settings

logger = logging.getLogger(__name__)


class PaymentVerificationService:
    """Service for verifying on-chain payments and managing transaction records."""

    async def verify_and_credit_payment(
        self,
        db: AsyncSession,
        tx_hash: str,
        amount: Decimal,
        currency: str,
        initiator_agent_id: str,
        transaction_type: TransactionType = TransactionType.TOP_UP,
        recipient_agent_id: Optional[str] = None,
        token_address: Optional[str] = None
    ) -> Tuple[PaymentTransaction, Agent]:
        """
        Verify an on-chain payment and credit the appropriate agent's balance.

        Args:
            db: Database session
            tx_hash: Transaction hash to verify
            amount: Expected amount in human-readable units
            currency: Currency code (e.g., "USDC")
            initiator_agent_id: Agent who initiated this verification
            transaction_type: Type of transaction (TOP_UP or P2P)
            recipient_agent_id: For P2P payments, the receiving agent
            token_address: Optional token contract address

        Returns:
            Tuple of (PaymentTransaction, credited_agent)

        Raises:
            HTTPException: If verification fails or transaction already processed
        """
        # Normalize tx_hash
        tx_hash = tx_hash.strip().lower()
        if not tx_hash.startswith("0x"):
            tx_hash = f"0x{tx_hash}"

        # Check for replay attack - has this transaction already been processed?
        existing_tx = await self._get_transaction_by_hash(db, tx_hash)
        if existing_tx:
            if existing_tx.status == TransactionStatus.CREDITED:
                logger.warning(
                    f"Replay attack attempt: tx_hash={tx_hash} already credited to agent={existing_tx.initiator_agent_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Transaction {tx_hash} has already been processed and credited."
                )
            elif existing_tx.status == TransactionStatus.VERIFIED:
                # Transaction was verified but not credited yet - could be a retry
                logger.info(f"Transaction {tx_hash} already verified, completing credit operation")
                return await self._complete_credit(db, existing_tx)
            elif existing_tx.status == TransactionStatus.FAILED:
                logger.info(f"Retrying previously failed transaction {tx_hash}")
                # Allow retry of failed transactions
                await db.delete(existing_tx)
                await db.commit()

        # Determine recipient address based on transaction type
        recipient_address = await self._get_recipient_address(
            db, transaction_type, recipient_agent_id
        )

        # Create pending transaction record
        payment_tx = PaymentTransaction(
            tx_hash=tx_hash,
            amount=amount,
            currency=currency,
            transaction_type=transaction_type,
            status=TransactionStatus.PENDING,
            initiator_agent_id=initiator_agent_id,
            recipient_agent_id=recipient_agent_id,
            to_address=recipient_address,
            token_address=token_address or settings.USDC_ADDRESS
        )
        db.add(payment_tx)
        await db.commit()

        logger.info(
            f"Created payment transaction record: id={payment_tx.id}, "
            f"tx_hash={tx_hash}, type={transaction_type}"
        )

        try:
            # Verify transaction on blockchain
            is_valid = chain_service.verify_transaction(
                tx_hash=tx_hash,
                expected_amount=amount,
                recipient_address=recipient_address,
                token_address=token_address
            )

            if not is_valid:
                payment_tx.status = TransactionStatus.FAILED
                payment_tx.failure_reason = "Blockchain verification failed: transaction not found, amount mismatch, or invalid recipient"
                await db.commit()

                logger.warning(
                    f"Payment verification failed for tx_hash={tx_hash}: blockchain validation returned False"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Payment verification failed. Please verify the transaction hash, amount, and recipient address."
                )

            # Mark as verified
            payment_tx.status = TransactionStatus.VERIFIED
            payment_tx.verified_at = datetime.utcnow()

            # Get transaction details for metadata
            try:
                receipt = chain_service.web3.eth.get_transaction_receipt(tx_hash)
                payment_tx.block_number = receipt.get('blockNumber')
                payment_tx.from_address = receipt.get('from')
            except Exception as e:
                logger.warning(f"Could not fetch transaction receipt details: {e}")

            await db.commit()

            logger.info(f"Transaction {tx_hash} verified successfully on blockchain")

            # Credit the balance
            return await self._complete_credit(db, payment_tx)

        except HTTPException:
            raise
        except Exception as e:
            payment_tx.status = TransactionStatus.FAILED
            payment_tx.failure_reason = f"Unexpected error during verification: {str(e)}"
            await db.commit()

            logger.error(f"Unexpected error verifying payment {tx_hash}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred during payment verification."
            )

    async def _complete_credit(
        self,
        db: AsyncSession,
        payment_tx: PaymentTransaction
    ) -> Tuple[PaymentTransaction, Agent]:
        """Complete the credit operation for a verified transaction."""

        # Determine which agent to credit
        if payment_tx.transaction_type == TransactionType.TOP_UP:
            agent_to_credit_id = payment_tx.initiator_agent_id
        elif payment_tx.transaction_type == TransactionType.P2P:
            if not payment_tx.recipient_agent_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="P2P payment requires recipient_agent_id"
                )
            agent_to_credit_id = payment_tx.recipient_agent_id
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported transaction type: {payment_tx.transaction_type}"
            )

        # Credit the agent's balance
        try:
            credited_agent = await update_balance(
                db, agent_to_credit_id, payment_tx.amount
            )

            payment_tx.status = TransactionStatus.CREDITED
            payment_tx.credited_at = datetime.utcnow()
            await db.commit()
            await db.refresh(payment_tx)

            logger.info(
                f"Successfully credited {payment_tx.amount} {payment_tx.currency} "
                f"to agent {agent_to_credit_id} from transaction {payment_tx.tx_hash}"
            )

            return payment_tx, credited_agent

        except ValueError as e:
            payment_tx.status = TransactionStatus.FAILED
            payment_tx.failure_reason = f"Balance update failed: {str(e)}"
            await db.commit()

            logger.error(f"Failed to credit balance for tx {payment_tx.tx_hash}: {e}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )

    async def _get_transaction_by_hash(
        self, db: AsyncSession, tx_hash: str
    ) -> Optional[PaymentTransaction]:
        """Check if a transaction has already been processed."""
        result = await db.execute(
            select(PaymentTransaction).where(PaymentTransaction.tx_hash == tx_hash)
        )
        return result.scalar_one_or_none()

    async def _get_recipient_address(
        self,
        db: AsyncSession,
        transaction_type: TransactionType,
        recipient_agent_id: Optional[str]
    ) -> str:
        """Determine the recipient address based on transaction type."""

        if transaction_type == TransactionType.TOP_UP:
            # For top-ups, use the platform wallet address
            if settings.PLATFORM_WALLET_ADDRESS == "0x0000000000000000000000000000000000000000":
                logger.warning(
                    "PLATFORM_WALLET_ADDRESS not configured in production! Using default."
                )
            return settings.PLATFORM_WALLET_ADDRESS

        elif transaction_type == TransactionType.P2P:
            # For P2P, fetch the recipient agent's wallet
            if not recipient_agent_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="P2P payment requires recipient_agent_id"
                )

            recipient_agent = await get_agent_by_id(db, recipient_agent_id)
            if not recipient_agent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Recipient agent {recipient_agent_id} not found"
                )

            if not recipient_agent.wallet_address:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Recipient agent {recipient_agent_id} has no wallet address configured"
                )

            return recipient_agent.wallet_address

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported transaction type: {transaction_type}"
            )

    async def get_transaction_history(
        self,
        db: AsyncSession,
        agent_id: Optional[str] = None,
        status_filter: Optional[TransactionStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> list[PaymentTransaction]:
        """
        Get transaction history with optional filters.

        Args:
            db: Database session
            agent_id: Filter by initiator or recipient agent
            status_filter: Filter by transaction status
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of payment transactions
        """
        query = select(PaymentTransaction)

        if agent_id:
            query = query.where(
                (PaymentTransaction.initiator_agent_id == agent_id) |
                (PaymentTransaction.recipient_agent_id == agent_id)
            )

        if status_filter:
            query = query.where(PaymentTransaction.status == status_filter)

        query = query.order_by(PaymentTransaction.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())


# Singleton instance
payment_verification_service = PaymentVerificationService()
