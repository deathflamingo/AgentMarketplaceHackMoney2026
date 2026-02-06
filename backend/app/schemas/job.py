"""Pydantic schemas for Job validation."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field, field_validator


class JobCreate(BaseModel):
    """Schema for creating a new job (hiring a service)."""
    service_id: str
    title: Optional[str] = Field(None, max_length=200)
    input_data: Dict[str, Any] = Field(default_factory=dict)
    parent_job_id: Optional[str] = None

    # Negotiated pricing (new)
    quote_id: Optional[str] = Field(None, description="ID of accepted price quote (for LLM negotiation)")
    negotiation_id: Optional[str] = Field(None, description="ID of agreed P2P negotiation")
    agreed_price: Optional[Decimal] = Field(None, description="Agreed price in AGNT (must match quote if quote_id provided)")


class JobStart(BaseModel):
    """Schema for starting a job (empty, just changes status)."""
    pass


class JobDeliver(BaseModel):
    """Schema for delivering work."""
    artifact_type: str = Field(..., pattern="^(text|code|image_url|json|file)$")
    content: str = Field(..., min_length=1)
    artifact_metadata: Optional[Dict[str, Any]] = None


class JobRequestRevision(BaseModel):
    """Schema for requesting revision."""
    feedback: str = Field(..., min_length=1)


class JobComplete(BaseModel):
    """Schema for completing a job with rating."""
    rating: int = Field(..., ge=1, le=5)
    review: Optional[str] = None

    @field_validator('rating')
    @classmethod
    def validate_rating(cls, v: int) -> int:
        """Ensure rating is between 1 and 5."""
        if not 1 <= v <= 5:
            raise ValueError("Rating must be between 1 and 5")
        return v


class DeliverableResponse(BaseModel):
    """Schema for deliverable response."""
    id: str
    artifact_type: str
    content: str
    artifact_metadata: Optional[Dict[str, Any]]
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


class JobStatusResponse(BaseModel):
    """Simple job status response."""
    job_id: str
    status: str
    updated_at: datetime


class JobResponse(BaseModel):
    """Full job response schema."""
    id: str
    service_id: str
    client_agent_id: str
    worker_agent_id: str
    parent_job_id: Optional[str]
    title: str
    input_data: Dict[str, Any]

    # AGNT pricing (new)
    price_agnt: Decimal
    final_price_agreed: Decimal
    initial_price_offer: Optional[Decimal]
    negotiated_by: Optional[str]  # "agent"|"llm"|"p2p"
    quote_id: Optional[str]
    negotiation_id: Optional[str]

    # Computed field
    price_usd: Optional[Decimal] = None  # Computed from price_agnt

    status: str
    rating: Optional[int]
    review: Optional[str]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    delivered_at: Optional[datetime]
    completed_at: Optional[datetime]
    deliverables: List[DeliverableResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}
