"""Agent service for business logic related to agents."""

from typing import List, Tuple, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentUpdate
from app.core.security import generate_api_key, hash_api_key
from app.core.events import event_bus


async def create_agent(db: AsyncSession, agent_data: AgentCreate) -> Tuple[Agent, str]:
    """
    Create a new agent with API key.

    Args:
        db: Database session
        agent_data: Agent creation data

    Returns:
        Tuple of (Agent, plaintext_api_key)
    """
    # Generate API key
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)

    # Create agent
    agent = Agent(
        name=agent_data.name,
        api_key_hash=api_key_hash,
        capabilities=agent_data.capabilities or [],
        description=agent_data.description,
        wallet_address=agent_data.wallet_address,
    )

    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    # Emit event
    await event_bus.publish("agent_registered", {
        "agent_id": str(agent.id),
        "name": agent.name,
        "capabilities": agent.capabilities,
    })

    return agent, api_key


async def search_agents(
    db: AsyncSession,
    capabilities: Optional[List[str]] = None,
    status: Optional[str] = None,
    min_reputation: Optional[float] = None,
    has_services: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Agent]:
    """
    Search agents with filters.

    Args:
        db: Database session
        capabilities: Filter by capabilities (any match)
        status: Filter by status
        min_reputation: Minimum reputation score
        has_services: Only agents with active services
        limit: Maximum results
        offset: Pagination offset

    Returns:
        List of matching agents
    """
    query = select(Agent)

    # Apply filters
    if status:
        query = query.where(Agent.status == status)

    if min_reputation is not None:
        query = query.where(Agent.reputation_score >= min_reputation)

    if capabilities:
        # Match any of the provided capabilities
        filters = [
            Agent.capabilities.op('@>')(f'["{cap}"]')
            for cap in capabilities
        ]
        query = query.where(or_(*filters))

    # Note: has_services would require a join, simplified for now
    # Could be added with: query = query.join(Service).where(Service.is_active == True)

    # Pagination
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def update_agent(
    db: AsyncSession,
    agent_id: str,
    updates: AgentUpdate
) -> Agent:
    """
    Update an agent's profile.

    Args:
        db: Database session
        agent_id: Agent UUID
        updates: Fields to update

    Returns:
        Updated agent

    Raises:
        ValueError: If agent not found
    """
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise ValueError("Agent not found")

    # Update fields
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)

    # Emit event if status changed
    if "status" in update_data:
        await event_bus.publish("agent_status_changed", {
            "agent_id": str(agent.id),
            "name": agent.name,
            "status": agent.status,
        })

    return agent


async def get_agent_by_id(db: AsyncSession, agent_id: str) -> Optional[Agent]:
    """
    Get an agent by ID.

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        Agent or None if not found
    """
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    return result.scalar_one_or_none()
