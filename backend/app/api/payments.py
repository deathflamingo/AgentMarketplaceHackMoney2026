"""Payments API router - Production-ready payment verification endpoints."""

import logging
from decimal import Decimal
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator

from app.database import get_db
from app.api.deps import get_current_agent
from app.models.agent import Agent
from app.models.payment_transaction import (
    PaymentTransaction,
    TransactionStatus,
    TransactionType
)
from app.services.payment_verification_service import payment_verification_service

logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic Models for Request/Response
class PaymentVerificationRequest(BaseModel):
    """Request model for payment verification."""

    tx_hash: str = Field(
        ...,
        min_length=64,
        max_length=66,
        description="Transaction hash (with or without 0x prefix)"
    )
    amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=8,
        description="Payment amount in human-readable units (e.g., 10.5 for 10.5 USDC)"
    )
    currency: str = Field(
        default="USDC",
        max_length=10,
        description="Currency code"
    )
    transaction_type: TransactionType = Field(
        default=TransactionType.TOP_UP,
        description="Type of transaction: top_up (deposit to platform) or p2p (peer-to-peer)"
    )
    recipient_agent_id: Optional[str] = Field(
        default=None,
        description="Required for P2P payments - the agent receiving the payment"
    )
    token_address: Optional[str] = Field(
        default=None,
        min_length=42,
        max_length=42,
        description="Optional token contract address (defaults to USDC from config)"
    )

    @field_validator("tx_hash")
    @classmethod
    def validate_tx_hash(cls, v: str) -> str:
        """Validate transaction hash format."""
        v = v.strip()
        if v.startswith("0x"):
            v = v[2:]
        if len(v) != 64:
            raise ValueError("Transaction hash must be 64 hex characters (with or without 0x prefix)")
        try:
            int(v, 16)
        except ValueError:
            raise ValueError("Transaction hash must be a valid hexadecimal string")
        return f"0x{v.lower()}"

    @field_validator("token_address")
    @classmethod
    def validate_token_address(cls, v: Optional[str]) -> Optional[str]:
        """Validate Ethereum address format."""
        if v is None:
            return None
        v = v.strip()
        if not v.startswith("0x") or len(v) != 42:
            raise ValueError("Token address must be a valid Ethereum address (0x + 40 hex chars)")
        return v.lower()


class PaymentVerificationResponse(BaseModel):
    """Response model for payment verification."""

    success: bool = Field(..., description="Whether the payment was successfully verified and credited")
    transaction_id: str = Field(..., description="Internal transaction ID for tracking")
    tx_hash: str = Field(..., description="Blockchain transaction hash")
    amount: Decimal = Field(..., description="Amount credited")
    currency: str = Field(..., description="Currency code")
    new_balance: Decimal = Field(..., description="Updated balance of the credited agent")
    credited_agent_id: str = Field(..., description="ID of the agent who received the credit")
    message: str = Field(..., description="Human-readable status message")
    verified_at: Optional[datetime] = Field(None, description="Timestamp when transaction was verified")
    credited_at: Optional[datetime] = Field(None, description="Timestamp when balance was credited")

    class Config:
        from_attributes = True


class TransactionHistoryItem(BaseModel):
    """Transaction history item."""

    id: str
    tx_hash: str
    amount: Decimal
    currency: str
    transaction_type: TransactionType
    status: TransactionStatus
    initiator_agent_id: str
    recipient_agent_id: Optional[str]
    to_address: str
    block_number: Optional[int]
    failure_reason: Optional[str]
    created_at: datetime
    verified_at: Optional[datetime]
    credited_at: Optional[datetime]

    class Config:
        from_attributes = True


class TransactionHistoryResponse(BaseModel):
    """Response model for transaction history."""

    transactions: List[TransactionHistoryItem]
    total: int
    offset: int
    limit: int


# API Endpoints
@router.post("/verify", response_model=PaymentVerificationResponse, status_code=status.HTTP_200_OK)
async def verify_payment(
    payment_data: PaymentVerificationRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify an on-chain payment and credit the appropriate agent's balance.

    This endpoint implements replay protection by tracking all processed transactions.
    Each transaction hash can only be successfully verified and credited once.

    **Top-up Flow (transaction_type=top_up):**
    - Agent sends USDC to the platform wallet address
    - Agent calls this endpoint with the transaction hash
    - System verifies the transaction on-chain
    - Agent's internal balance is credited

    **P2P Flow (transaction_type=p2p):**
    - Agent A sends USDC to Agent B's wallet address
    - Agent A calls this endpoint with transaction hash and recipient_agent_id
    - System verifies the transaction on-chain
    - Agent B's internal balance is credited

    **Security Features:**
    - Replay attack prevention (each tx_hash can only be credited once)
    - On-chain verification of amount and recipient
    - Transaction audit trail
    - Idempotent retries for failed transactions
    """
    logger.info(
        f"Payment verification request from agent {current_agent.id}: "
        f"tx_hash={payment_data.tx_hash}, amount={payment_data.amount}, "
        f"type={payment_data.transaction_type}"
    )

    # Validate P2P payments have recipient
    if payment_data.transaction_type == TransactionType.P2P and not payment_data.recipient_agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="P2P payments require recipient_agent_id to be specified"
        )

    # Verify and credit the payment
    try:
        payment_tx, credited_agent = await payment_verification_service.verify_and_credit_payment(
            db=db,
            tx_hash=payment_data.tx_hash,
            amount=payment_data.amount,
            currency=payment_data.currency,
            initiator_agent_id=str(current_agent.id),
            transaction_type=payment_data.transaction_type,
            recipient_agent_id=payment_data.recipient_agent_id,
            token_address=payment_data.token_address
        )

        logger.info(
            f"Payment verified and credited successfully: tx_id={payment_tx.id}, "
            f"credited_agent={credited_agent.id}, new_balance={credited_agent.balance}"
        )

        return PaymentVerificationResponse(
            success=True,
            transaction_id=payment_tx.id,
            tx_hash=payment_tx.tx_hash,
            amount=payment_tx.amount,
            currency=payment_tx.currency,
            new_balance=credited_agent.balance,
            credited_agent_id=str(credited_agent.id),
            message=f"Payment verified and {payment_tx.amount} {payment_tx.currency} credited successfully",
            verified_at=payment_tx.verified_at,
            credited_at=payment_tx.credited_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in verify_payment endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your payment"
        )


@router.get("/history", response_model=TransactionHistoryResponse)
async def get_payment_history(
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[TransactionStatus] = Query(None, description="Filter by transaction status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    Get payment transaction history for the current agent.

    Returns all transactions where the current agent is either the initiator
    or the recipient, ordered by creation time (newest first).

    Supports filtering by transaction status and pagination.
    """
    logger.info(
        f"Transaction history request from agent {current_agent.id}: "
        f"status={status_filter}, limit={limit}, offset={offset}"
    )

    transactions = await payment_verification_service.get_transaction_history(
        db=db,
        agent_id=str(current_agent.id),
        status_filter=status_filter,
        limit=limit,
        offset=offset
    )

    return TransactionHistoryResponse(
        transactions=[TransactionHistoryItem.model_validate(tx) for tx in transactions],
        total=len(transactions),
        offset=offset,
        limit=limit
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionHistoryItem)
async def get_transaction_details(
    transaction_id: str,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific payment transaction.

    Only returns transactions where the current agent is the initiator or recipient.
    """
    from sqlalchemy import select

    result = await db.execute(
        select(PaymentTransaction).where(PaymentTransaction.id == transaction_id)
    )
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction {transaction_id} not found"
        )

    # Verify the current agent has access to this transaction
    if (transaction.initiator_agent_id != str(current_agent.id) and
            transaction.recipient_agent_id != str(current_agent.id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this transaction"
        )

    return TransactionHistoryItem.model_validate(transaction)
