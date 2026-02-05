"""Schemas for LLM credentials and gateway usage."""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class LLMCredentialCreate(BaseModel):
    provider: str = Field(..., pattern="^(openai|anthropic)$")
    api_key: str = Field(..., min_length=10)


class LLMCredentialResponse(BaseModel):
    id: str
    provider: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]

    model_config = {"from_attributes": True}


class LLMUsageSummary(BaseModel):
    job_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: str


class LLMChatRequest(BaseModel):
    job_id: str
    provider: str = Field(..., pattern="^(openai|anthropic)$")
    model: str
    messages: List[dict]
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.2, ge=0, le=2)


class LLMChatResponse(BaseModel):
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: str
