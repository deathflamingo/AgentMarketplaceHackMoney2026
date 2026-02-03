"""Pydantic schemas for Message validation."""

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Message response schema."""
    id: UUID
    from_agent_id: UUID
    to_agent_id: UUID
    job_id: Optional[UUID]
    message_type: str
    content: Dict[str, Any]
    read_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageList(BaseModel):
    """List of messages with pagination."""
    messages: List[MessageResponse]
    total: int
    unread_count: int


class MarkReadResponse(BaseModel):
    """Response when marking message as read."""
    message_id: UUID
    read_at: datetime
