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
    client_max_budget_usd: Decimal = Field(..., gt=0, decimal_places=2)


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
    price_usd: Decimal
    price_per_1k_tokens_usd: Decimal
    worker_min_payout_usd: Decimal
    client_max_budget_usd: Decimal
    avg_tokens_per_job: int
    escrow_status: str
    escrow_amount_usd: Decimal
    usage_prompt_tokens: int
    usage_completion_tokens: int
    usage_total_tokens: int
    usage_cost_usd: Decimal
    settlement_amount_usd: Decimal
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
