"""API dependencies for authentication and database access."""

from typing import Optional
from datetime import datetime
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.security import verify_api_key


async def get_current_agent(
    x_agent_key: str = Header(..., description="API key for authentication"),
    db: AsyncSession = Depends(get_db)
):
    """
    Dependency that validates the X-Agent-Key header and returns the authenticated agent.

    Args:
        x_agent_key: API key from X-Agent-Key header
        db: Database session

    Returns:
        Agent: The authenticated agent

    Raises:
        HTTPException: 401 if API key is invalid
    """
    # Import here to avoid circular imports
    from app.models.agent import Agent

    # Query all agents to find matching API key hash
    result = await db.execute(select(Agent))
    agents = result.scalars().all()

    for agent in agents:
        if verify_api_key(x_agent_key, agent.api_key_hash):
            # Update last_seen_at
            agent.last_seen_at = datetime.utcnow()
            await db.commit()
            return agent

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "INVALID_API_KEY",
            "message": "Invalid API key provided"
        }
    )


async def get_optional_agent(
    x_agent_key: Optional[str] = Header(None, description="Optional API key for authentication"),
    db: AsyncSession = Depends(get_db)
):
    """
    Dependency that optionally validates the X-Agent-Key header.

    Used for public endpoints that optionally use authentication.

    Args:
        x_agent_key: Optional API key from X-Agent-Key header
        db: Database session

    Returns:
        Optional[Agent]: The authenticated agent or None
    """
    if not x_agent_key:
        return None

    try:
        return await get_current_agent(x_agent_key, db)
    except HTTPException:
        return None
