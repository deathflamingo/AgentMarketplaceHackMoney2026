"""Withdrawal request and response schemas."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class WithdrawalRequest(BaseModel):
    """Request to withdraw AGNT to USDC."""

    agnt_amount: Decimal = Field(
        ...,
        description="Amount of AGNT to withdraw (before fees)",
        gt=0
    )
    recipient_address: str = Field(
        ...,
        description="Wallet address to receive USDC",
        min_length=42,
        max_length=42
    )


class WithdrawalResponse(BaseModel):
    """Response for withdrawal transaction."""

    id: str
    agent_id: str
    agnt_amount_in: Decimal
    usdc_amount_out: Decimal
    fee_agnt: Decimal
    exchange_rate: Decimal
    recipient_address: str
    swap_tx_hash: str | None
    transfer_tx_hash: str | None
    status: str
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True


class WithdrawalRequestResponse(BaseModel):
    """Response after creating a withdrawal request."""

    success: bool
    message: str
    withdrawal: WithdrawalResponse
    agent_new_balance: Decimal
    estimated_usdc: Decimal
    fee_agnt: Decimal
