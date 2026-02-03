"""Inbox API router for agent messages."""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_agent
from app.models.agent import Agent
from app.schemas.message import MessageList, MessageResponse, MarkReadResponse
from app.services.message_service import get_inbox, mark_as_read

router = APIRouter()


@router.get("", response_model=MessageList)
async def get_agent_inbox(
    unread_only: bool = Query(False),
    job_id: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Get messages for the current agent.
    """
    messages, total, unread_count = await get_inbox(
        db=db,
        agent_id=str(current_agent.id),
        unread_only=unread_only,
        job_id=job_id,
        since=since,
        limit=limit,
        offset=offset
    )

    return MessageList(
        messages=[MessageResponse.model_validate(m) for m in messages],
        total=total,
        unread_count=unread_count
    )


@router.post("/{message_id}/read", response_model=MarkReadResponse)
async def mark_message_read(
    message_id: str,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a message as read.
    """
    try:
        message = await mark_as_read(db, message_id, str(current_agent.id))
        return MarkReadResponse(
            message_id=message.id,
            read_at=message.read_at
        )
    except ValueError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "MESSAGE_NOT_FOUND",
                    "message": str(e)
                }
            )
        elif "not authorized" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "NOT_MESSAGE_RECIPIENT",
                    "message": str(e)
                }
            )
        raise
