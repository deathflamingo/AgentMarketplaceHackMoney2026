"""Pydantic schemas for Service validation."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class ServiceCreate(BaseModel):
    """Schema for creating a new service."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    required_inputs: List[Dict[str, Any]] = Field(default_factory=list)
    output_type: str = Field(..., pattern="^(text|code|image_url|json|file)$")
    output_description: Optional[str] = None
    price_usd: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    price_per_1k_tokens_usd: Decimal = Field(..., gt=0, decimal_places=4)
    worker_min_payout_usd: Decimal = Field(..., ge=0, decimal_places=2)
    avg_tokens_per_job: int = Field(default=0, ge=0)
    estimated_minutes: Optional[int] = Field(None, gt=0)
    capabilities_required: List[str] = Field(default_factory=list)
    max_concurrent: int = Field(default=5, gt=0)


class ServiceUpdate(BaseModel):
    """Schema for updating a service."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1)
    price_usd: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    price_per_1k_tokens_usd: Optional[Decimal] = Field(None, gt=0, decimal_places=4)
    worker_min_payout_usd: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    avg_tokens_per_job: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    max_concurrent: Optional[int] = Field(None, gt=0)


class ServicePublic(BaseModel):
    """Public service schema for marketplace browsing."""
    id: str
    agent_id: str
    agent_name: str
    name: str
    description: str
    required_inputs: List[Dict[str, Any]]
    output_type: str
    output_description: Optional[str]
    price_usd: Decimal
    price_per_1k_tokens_usd: Decimal
    worker_min_payout_usd: Decimal
    avg_tokens_per_job: int
    estimated_minutes: Optional[int]
    capabilities_required: List[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ServiceResponse(BaseModel):
    """Full service response schema."""
    id: str
    agent_id: str
    name: str
    description: str
    required_inputs: List[Dict[str, Any]]
    output_type: str
    output_description: Optional[str]
    price_usd: Decimal
    price_per_1k_tokens_usd: Decimal
    worker_min_payout_usd: Decimal
    avg_tokens_per_job: int
    estimated_minutes: Optional[int]
    capabilities_required: List[str]
    max_concurrent: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
