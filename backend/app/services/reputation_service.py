"""Reputation service for managing agent reputation scores."""

from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.agent import Agent
from app.core.events import event_bus


async def update_reputation(
    db: AsyncSession,
    worker_agent_id: str,
    new_rating: int
) -> float:
    """
    Update agent reputation with weighted average.

    Algorithm:
    - If jobs_completed == 0: new_score = rating
    - Else: weight = min(jobs_completed, 50)
            new_score = ((old_score * weight) + new_rating) / (weight + 1)
    - Round to 2 decimals

    Args:
        db: Database session
        worker_agent_id: Worker agent UUID
        new_rating: New rating (1-5)

    Returns:
        New reputation score

    Raises:
        ValueError: If agent not found
    """
    result = await db.execute(
        select(Agent).where(Agent.id == worker_agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise ValueError("Agent not found")

    # Calculate weighted average
    if agent.jobs_completed == 0:
        new_score = Decimal(str(new_rating))
    else:
        weight = min(agent.jobs_completed, 50)
        old_score = float(agent.reputation_score)
        new_score = ((old_score * weight) + new_rating) / (weight + 1)
        new_score = Decimal(str(round(new_score, 2)))

    # Update agent
    agent.reputation_score = new_score
    await db.commit()
    await db.refresh(agent)

    # Emit event
    await event_bus.publish("reputation_updated", {
        "agent_id": str(worker_agent_id),
        "new_score": str(new_score),
        "rating": new_rating,
    })

    return float(new_score)
