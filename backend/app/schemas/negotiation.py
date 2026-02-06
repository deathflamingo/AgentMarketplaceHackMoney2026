"""
Negotiation schemas for P2P price negotiation.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field, computed_field


# Negotiation Offer Schemas

class NegotiationOfferBase(BaseModel):
    """Base negotiation offer schema."""
    action: str = Field(..., description="Action: offer, counter, accept, or reject")
    price: Decimal = Field(..., description="Price in AGNT")
    message: Optional[str] = Field(None, description="Optional message")


class NegotiationOfferResponse(NegotiationOfferBase):
    """Negotiation offer response."""
    id: str
    negotiation_id: str
    agent_id: str
    agent_role: str
    created_at: datetime

    class Config:
        from_attributes = True


# Negotiation Schemas

class NegotiationStartRequest(BaseModel):
    """Request to start a new negotiation."""
    service_id: str = Field(..., description="Service to negotiate for")
    job_description: str = Field(..., description="Description of the job")
    initial_offer: Decimal = Field(..., description="Initial price offer in AGNT", gt=0)
    max_price: Optional[Decimal] = Field(None, description="Your maximum budget in AGNT")
    message: Optional[str] = Field(None, description="Optional message with your offer")


class NegotiationRespondRequest(BaseModel):
    """Request to respond to a negotiation."""
    action: str = Field(..., description="Action: accept, counter, or reject")
    counter_price: Optional[Decimal] = Field(None, description="New price if countering (in AGNT)")
    message: Optional[str] = Field(None, description="Optional message")


class NegotiationResponse(BaseModel):
    """Negotiation response with full details."""
    id: str
    service_id: str
    client_agent_id: str
    worker_agent_id: str
    job_description: str
    status: str
    current_price: Decimal
    current_proposer: str
    service_min_price: Decimal
    service_max_price: Decimal
    client_max_price: Optional[Decimal]
    round_count: int
    max_rounds: int
    created_at: datetime
    expires_at: datetime
    agreed_at: Optional[datetime]
    offers: List[NegotiationOfferResponse] = []

    @computed_field
    @property
    def current_price_usd(self) -> float:
        """Current price in USD (1 USDC = 10,000 AGNT)."""
        return float(self.current_price / Decimal("10000"))

    @computed_field
    @property
    def waiting_for(self) -> str:
        """Who needs to respond next."""
        if self.status != "active":
            return self.status
        return "worker" if self.current_proposer == "client" else "client"

    class Config:
        from_attributes = True


class NegotiationSummary(BaseModel):
    """Summarized negotiation info for listings."""
    id: str
    service_id: str
    client_agent_id: str
    worker_agent_id: str
    job_description: str
    status: str
    current_price: Decimal
    current_proposer: str
    round_count: int
    created_at: datetime
    expires_at: datetime

    @computed_field
    @property
    def current_price_usd(self) -> float:
        """Current price in USD."""
        return float(self.current_price / Decimal("10000"))

    @computed_field
    @property
    def waiting_for(self) -> str:
        """Who needs to respond next."""
        if self.status != "active":
            return self.status
        return "worker" if self.current_proposer == "client" else "client"

    class Config:
        from_attributes = True
