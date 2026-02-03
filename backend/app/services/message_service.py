"""Message service for handling agent communications."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.message import Message


async def create_auto_message(
    db: AsyncSession,
    message_type: str,
    from_agent_id: str,
    to_agent_id: str,
    job_id: Optional[str],
    content_data: Dict[str, Any]
) -> Message:
    """
    Create an automatic message.

    Args:
        db: Database session
        message_type: Type of message
        from_agent_id: Sender agent UUID
        to_agent_id: Recipient agent UUID
        job_id: Optional job UUID
        content_data: Message content

    Returns:
        Created message
    """
    from uuid import UUID
    message = Message(
        from_agent_id=UUID(from_agent_id) if isinstance(from_agent_id, str) else from_agent_id,
        to_agent_id=UUID(to_agent_id) if isinstance(to_agent_id, str) else to_agent_id,
        job_id=UUID(job_id) if job_id and isinstance(job_id, str) else job_id,
        message_type=message_type,
        content=content_data,
    )

    db.add(message)
    await db.commit()
    await db.refresh(message)

    return message


async def get_inbox(
    db: AsyncSession,
    agent_id: str,
    unread_only: bool = False,
    job_id: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0
) -> tuple[List[Message], int, int]:
    """
    Get messages for an agent's inbox.

    Args:
        db: Database session
        agent_id: Recipient agent UUID
        unread_only: Only return unread messages
        job_id: Filter by job
        since: Only messages after this timestamp
        limit: Maximum results
        offset: Pagination offset

    Returns:
        Tuple of (messages, total_count, unread_count)
    """
    # Build query
    query = select(Message).where(Message.to_agent_id == agent_id)

    if unread_only:
        query = query.where(Message.read_at.is_(None))

    if job_id:
        query = query.where(Message.job_id == job_id)

    if since:
        query = query.where(Message.created_at >= since)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar()

    # Get unread count
    unread_query = select(func.count()).where(
        and_(
            Message.to_agent_id == agent_id,
            Message.read_at.is_(None)
        )
    )
    unread_result = await db.execute(unread_query)
    unread_count = unread_result.scalar()

    # Get messages with pagination
    query = query.order_by(Message.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    messages = list(result.scalars().all())

    return messages, total_count, unread_count


async def mark_as_read(
    db: AsyncSession,
    message_id: str,
    agent_id: str
) -> Message:
    """
    Mark a message as read.

    Args:
        db: Database session
        message_id: Message UUID
        agent_id: Agent UUID (for ownership verification)

    Returns:
        Updated message

    Raises:
        ValueError: If message not found or not owned by agent
    """
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise ValueError("Message not found")

    if str(message.to_agent_id) != str(agent_id):
        raise ValueError("Not authorized - this message is not for you")

    if message.read_at is None:
        message.read_at = datetime.utcnow()
        await db.commit()
        await db.refresh(message)

    return message
