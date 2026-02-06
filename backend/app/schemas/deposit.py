"""Deposit request and response schemas."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class DepositVerifyRequest(BaseModel):
    """Request to verify a deposit transaction."""

    tx_hash: str = Field(..., description="Transaction hash of the USDC→AGNT swap on Uniswap")
    expected_agnt_amount: Decimal = Field(
        ...,
        description="Expected AGNT amount to receive (minimum after slippage)",
        gt=0
    )


class DepositResponse(BaseModel):
    """Response for deposit verification."""

    id: str
    agent_id: str
    swap_tx_hash: str
    usdc_amount_in: Decimal
    agnt_amount_out: Decimal
    exchange_rate: Decimal
    status: str
    created_at: datetime
    verified_at: datetime | None

    class Config:
        from_attributes = True


class DepositVerifyResponse(BaseModel):
    """Response after verifying a deposit."""

    success: bool
    message: str
    deposit: DepositResponse | None
    agent_new_balance: Decimal | None
