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

    # AGNT pricing (new)
    min_price_agnt: Decimal = Field(..., gt=0, description="Minimum price in AGNT tokens")
    max_price_agnt: Decimal = Field(..., gt=0, description="Maximum price in AGNT tokens")
    allow_negotiation: bool = Field(default=True, description="Allow LLM price negotiation")

    # Legacy USD pricing (deprecated, kept for backward compatibility)
    price_usd: Optional[Decimal] = Field(None, gt=0, decimal_places=2, deprecated=True)

    estimated_minutes: Optional[int] = Field(None, gt=0)
    capabilities_required: List[str] = Field(default_factory=list)
    max_concurrent: int = Field(default=5, gt=0)


class ServiceUpdate(BaseModel):
    """Schema for updating a service."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1)

    # AGNT pricing
    min_price_agnt: Optional[Decimal] = Field(None, gt=0)
    max_price_agnt: Optional[Decimal] = Field(None, gt=0)
    allow_negotiation: Optional[bool] = None

    # Legacy USD pricing (deprecated)
    price_usd: Optional[Decimal] = Field(None, gt=0, decimal_places=2, deprecated=True)

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

    # AGNT pricing
    min_price_agnt: Decimal
    max_price_agnt: Decimal
    allow_negotiation: bool

    # Computed fields
    price_range_usd: Optional[str] = None  # e.g., "$5-$15"
    midpoint_price_agnt: Optional[Decimal] = None

    # Legacy
    price_usd: Optional[Decimal] = None

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

    # AGNT pricing
    min_price_agnt: Decimal
    max_price_agnt: Decimal
    allow_negotiation: bool

    # Computed fields (populated in API layer)
    price_range_usd: Optional[str] = None
    midpoint_price_agnt: Optional[Decimal] = None

    # Legacy (deprecated)
    price_usd: Optional[Decimal] = None

    estimated_minutes: Optional[int]
    capabilities_required: List[str]
    max_concurrent: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
