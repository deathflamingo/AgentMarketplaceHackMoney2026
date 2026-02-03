"""Agents API router."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_agent, get_optional_agent
from app.models.agent import Agent
from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    AgentPublic,
    AgentResponse,
    AgentRegisterResponse,
)
from app.services.agent_service import (
    create_agent,
    search_agents,
    update_agent,
    get_agent_by_id,
)

router = APIRouter()


@router.post("", response_model=AgentRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(
    agent_data: AgentCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new agent (public endpoint).

    Returns the API key ONLY ONCE - save it securely!
    """
    try:
        agent, api_key = await create_agent(db, agent_data)

        return AgentRegisterResponse(
            agent_id=agent.id,
            name=agent.name,
            api_key=api_key,
            created_at=agent.created_at
        )
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "DUPLICATE_AGENT_NAME",
                    "message": f"Agent with name '{agent_data.name}' already exists"
                }
            )
        raise


@router.get("", response_model=List[AgentPublic])
async def list_agents(
    capabilities: Optional[str] = Query(None, description="Comma-separated capabilities"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    min_reputation: Optional[float] = Query(None, description="Minimum reputation score"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_agent: Optional[Agent] = Depends(get_optional_agent)
):
    """
    Search and browse agents (public endpoint with optional auth).
    """
    # Parse capabilities
    caps_list = None
    if capabilities:
        caps_list = [c.strip() for c in capabilities.split(",")]

    agents = await search_agents(
        db=db,
        capabilities=caps_list,
        status=status_filter,
        min_reputation=min_reputation,
        limit=limit,
        offset=offset
    )

    return agents


@router.get("/me", response_model=AgentResponse)
async def get_current_agent_profile(
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Get the current authenticated agent's profile.
    """
    return current_agent


@router.get("/{agent_id}", response_model=AgentPublic)
async def get_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific agent's public profile.
    """
    agent = await get_agent_by_id(db, agent_id)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": f"Agent with ID {agent_id} not found"
            }
        )

    return agent


@router.patch("/me", response_model=AgentResponse)
async def update_current_agent(
    updates: AgentUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Update the current agent's profile.
    """
    try:
        updated_agent = await update_agent(db, str(current_agent.id), updates)
        return updated_agent
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": str(e)
            }
        )


@router.put("/me/status", response_model=AgentResponse)
async def update_agent_status(
    status_update: AgentUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Update the current agent's status.
    """
    if not status_update.status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_STATUS",
                "message": "Status is required"
            }
        )

    try:
        updated_agent = await update_agent(db, str(current_agent.id), status_update)
        return updated_agent
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": str(e)
            }
        )
