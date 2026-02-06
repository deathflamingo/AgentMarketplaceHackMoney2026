"""Price quote request and response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class QuoteRequest(BaseModel):
    """Request for a price quote."""

    service_id: str = Field(..., description="ID of the service to get a quote for")
    job_description: str = Field(
        ...,
        description="Description of the job/task for negotiation context",
        min_length=10,
        max_length=2000
    )
    max_price_willing: Optional[Decimal] = Field(
        None,
        description="Maximum price client is willing to pay (optional budget constraint)",
        gt=0
    )


class QuoteResponse(BaseModel):
    """Response with price quote details."""

    id: str
    service_id: str
    client_agent_id: str
    job_description: str
    max_price_willing: Decimal | None
    quoted_price: Decimal
    service_min_price: Decimal
    service_max_price: Decimal
    negotiation_factors: str | None
    status: str
    created_at: datetime
    valid_until: datetime
    accepted_at: datetime | None

    # Additional computed fields
    quoted_price_usd: Optional[Decimal] = None
    savings_percent: Optional[Decimal] = None

    class Config:
        from_attributes = True


class QuoteCreateResponse(BaseModel):
    """Response after creating a quote."""

    success: bool
    message: str
    quote: QuoteResponse
    expires_in_seconds: int
