"""Pydantic schemas for Agent validation."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    """Schema for creating a new agent."""
    name: str = Field(..., min_length=1, max_length=100)
    capabilities: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    wallet_address: Optional[str] = Field(None, max_length=128)


class AgentUpdate(BaseModel):
    """Schema for updating an agent profile."""
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    status: Optional[str] = Field(None, pattern="^(available|busy|offline)$")


class AgentPublic(BaseModel):
    """Public agent profile schema (for browsing)."""
    id: UUID
    name: str
    capabilities: List[str]
    description: Optional[str]
    reputation_score: Decimal
    jobs_completed: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentResponse(BaseModel):
    """Full agent response schema (for authenticated user)."""
    id: UUID
    name: str
    wallet_address: Optional[str]
    description: Optional[str]
    capabilities: List[str]
    reputation_score: Decimal
    jobs_completed: int
    jobs_hired: int
    total_earned: Decimal
    total_spent: Decimal
    status: str
    created_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class AgentRegisterResponse(BaseModel):
    """Response when registering a new agent (includes API key)."""
    agent_id: UUID
    name: str
    api_key: str  # ONLY shown once during registration
    created_at: datetime

    model_config = {"from_attributes": True}
