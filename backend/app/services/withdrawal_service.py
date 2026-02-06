"""Withdrawal service for converting AGNT to USDC and sending to agents."""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
import uuid
from typing import Dict

from web3 import Web3
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config import settings
from app.models.withdrawal_transaction import WithdrawalTransaction
from app.models.agent import Agent
from app.services.uniswap_service import uniswap_service

logger = logging.getLogger(__name__)


class WithdrawalService:
    """Service for handling agent withdrawals (AGNT → USDC)."""

    def __init__(self):
        self.web3 = Web3(Web3.HTTPProvider(settings.WEB3_RPC_URL))
        self.min_withdrawal = settings.WITHDRAWAL_MIN_AMOUNT
        self.fee_percent = settings.WITHDRAWAL_FEE_PERCENT
        self.rate_limit_per_hour = settings.WITHDRAWAL_RATE_LIMIT_PER_HOUR

        # Platform wallet for executing withdrawals
        self.platform_private_key = settings.PLATFORM_WALLET_PRIVATE_KEY
        if self.platform_private_key:
            self.platform_account = self.web3.eth.account.from_key(self.platform_private_key)
            self.platform_address = self.platform_account.address
        else:
            self.platform_account = None
            self.platform_address = None
            logger.warning("Platform wallet not configured - withdrawals will not execute")

        # Token contracts
        self.agnt_address = settings.AGENTCOIN_ADDRESS
        self.usdc_address = settings.USDC_ADDRESS

        # ERC20 ABI for transfers and approvals
        self.erc20_abi = [
            {
                "constant": False,
                "inputs": [
                    {"name": "spender", "type": "address"},
                    {"name": "value", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"}
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [{"name": "account", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]

    async def validate_withdrawal_request(
        self,
        agent: Agent,
        agnt_amount: Decimal,
        recipient_address: str,
        db: AsyncSession
    ) -> Dict:
        """
        Validate a withdrawal request.

        Returns:
            Dict with 'valid': bool and optional 'error': str
        """
        # Check minimum withdrawal amount
        if agnt_amount < self.min_withdrawal:
            return {
                'valid': False,
                'error': f"Minimum withdrawal amount is {self.min_withdrawal} AGNT"
            }

        # Check agent has sufficient balance
        if agent.balance < agnt_amount:
            return {
                'valid': False,
                'error': f"Insufficient balance. Available: {agent.balance} AGNT"
            }

        # Check recipient address is valid
        if not Web3.is_address(recipient_address):
            return {
                'valid': False,
                'error': f"Invalid recipient address: {recipient_address}"
            }

        # Check rate limiting (max withdrawals per hour)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        result = await db.execute(
            select(func.count(WithdrawalTransaction.id))
            .where(
                WithdrawalTransaction.agent_id == agent.id,
                WithdrawalTransaction.created_at >= one_hour_ago
            )
        )
        recent_withdrawals = result.scalar()

        if recent_withdrawals >= self.rate_limit_per_hour:
            return {
                'valid': False,
                'error': f"Rate limit exceeded. Max {self.rate_limit_per_hour} withdrawals per hour."
            }

        return {'valid': True}

    async def create_withdrawal_request(
        self,
        agent: Agent,
        agnt_amount: Decimal,
        recipient_address: str,
        db: AsyncSession
    ) -> WithdrawalTransaction:
        """
        Create a withdrawal request and deduct balance immediately.

        Args:
            agent: Agent requesting withdrawal
            agnt_amount: Amount of AGNT to withdraw (before fees)
            recipient_address: Wallet address to receive USDC
            db: Database session

        Returns:
            Created WithdrawalTransaction

        Raises:
            ValueError: If validation fails
        """
        # Validate request
        validation = await self.validate_withdrawal_request(
            agent, agnt_amount, recipient_address, db
        )
        if not validation['valid']:
            raise ValueError(validation['error'])

        # Calculate fee
        fee_agnt = agnt_amount * (self.fee_percent / Decimal("100"))
        agnt_after_fee = agnt_amount - fee_agnt

        # Get expected USDC amount (estimate)
        try:
            usdc_estimate = await uniswap_service.get_quote_agnt_to_usdc(agnt_after_fee)
        except Exception as e:
            logger.error(f"Error getting withdrawal quote: {e}")
            usdc_estimate = Decimal("0")

        # Deduct balance immediately
        agent.balance -= agnt_amount
        agent.total_spent += agnt_amount

        # Create withdrawal record
        withdrawal = WithdrawalTransaction(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            agnt_amount_in=agnt_amount,
            usdc_amount_out=usdc_estimate,  # Will be updated after actual swap
            fee_agnt=fee_agnt,
            exchange_rate=Decimal("0"),  # Will be updated after swap
            recipient_address=recipient_address,
            status="pending",
            created_at=datetime.utcnow()
        )

        db.add(withdrawal)
        await db.commit()
        await db.refresh(withdrawal)

        logger.info(
            f"Withdrawal request created: {withdrawal.id} for agent {agent.id}, "
            f"amount: {agnt_amount} AGNT (fee: {fee_agnt} AGNT)"
        )

        return withdrawal

    async def execute_withdrawal(
        self,
        withdrawal: WithdrawalTransaction,
        db: AsyncSession
    ) -> bool:
        """
        Execute the withdrawal: convert AGNT to USDC at fixed rate and transfer.

        Sends USDC from platform wallet to the recipient address.
        Refunds AGNT to agent balance on failure.

        Args:
            withdrawal: Withdrawal transaction to execute
            db: Database session

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.platform_account:
                logger.error("Platform wallet not configured")
                withdrawal.status = "failed"
                withdrawal.error_message = "Platform wallet not configured"
                await db.commit()
                return False

            withdrawal.status = "processing"
            await db.commit()

            logger.info(f"Executing withdrawal {withdrawal.id}...")

            # Calculate USDC amount at fixed rate (no Uniswap swap needed)
            agnt_after_fee = withdrawal.agnt_amount_in - withdrawal.fee_agnt
            usdc_amount = agnt_after_fee / settings.USDC_TO_AGNT_RATE
            exchange_rate = Decimal("1") / settings.USDC_TO_AGNT_RATE

            logger.info(
                f"Withdrawal conversion: {agnt_after_fee} AGNT → {usdc_amount} USDC "
                f"(rate: 1 USDC = {settings.USDC_TO_AGNT_RATE} AGNT)"
            )

            # Transfer USDC from platform wallet to recipient
            usdc_contract = self.web3.eth.contract(
                address=self.web3.to_checksum_address(self.usdc_address),
                abi=self.erc20_abi
            )

            # USDC has 6 decimals
            usdc_raw_amount = int(usdc_amount * Decimal(10 ** 6))

            recipient = self.web3.to_checksum_address(withdrawal.recipient_address)
            nonce = self.web3.eth.get_transaction_count(self.platform_address)

            transfer_tx = usdc_contract.functions.transfer(
                recipient,
                usdc_raw_amount
            ).build_transaction({
                'from': self.platform_address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': self.web3.eth.gas_price,
                'chainId': 84532  # Base Sepolia
            })

            signed_transfer = self.platform_account.sign_transaction(transfer_tx)
            tx_hash = self.web3.eth.send_raw_transaction(signed_transfer.raw_transaction)
            transfer_receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if transfer_receipt['status'] != 1:
                raise Exception(f"USDC transfer failed on-chain: {tx_hash.hex()}")

            transfer_tx_hash = tx_hash.hex()

            logger.info(
                f"USDC transfer executed: {usdc_amount} USDC to {withdrawal.recipient_address} "
                f"(tx: {transfer_tx_hash})"
            )

            # Update withdrawal record
            withdrawal.usdc_amount_out = usdc_amount
            withdrawal.exchange_rate = exchange_rate
            withdrawal.transfer_tx_hash = transfer_tx_hash
            withdrawal.status = "completed"
            withdrawal.completed_at = datetime.utcnow()
            withdrawal.error_message = None

            await db.commit()

            logger.info(f"✅ Withdrawal {withdrawal.id} completed successfully")
            return True

        except Exception as e:
            logger.error(f"Error executing withdrawal {withdrawal.id}: {e}", exc_info=True)

            # Refund AGNT to agent on failure
            try:
                result = await db.execute(
                    select(Agent).where(Agent.id == withdrawal.agent_id)
                )
                agent = result.scalar_one_or_none()
                if agent:
                    agent.balance += withdrawal.agnt_amount_in
                    agent.total_spent -= withdrawal.agnt_amount_in

                withdrawal.status = "failed"
                withdrawal.error_message = str(e)[:500]
                await db.commit()

                logger.info(f"Refunded {withdrawal.agnt_amount_in} AGNT to agent {withdrawal.agent_id}")
            except Exception as refund_error:
                logger.error(f"Error refunding withdrawal: {refund_error}", exc_info=True)

            return False


# Singleton instance
withdrawal_service = WithdrawalService()
