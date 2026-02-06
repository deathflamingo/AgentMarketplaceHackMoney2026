"""
Negotiation endpoints for P2P price negotiation between agents.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_agent
from app.models.agent import Agent
from app.services.p2p_negotiation_service import p2p_negotiation_service
from app.schemas.negotiation import (
    NegotiationStartRequest,
    NegotiationResponse,
    NegotiationRespondRequest,
    NegotiationSummary
)

router = APIRouter(prefix="/negotiations", tags=["negotiations"])


@router.post("/start", response_model=NegotiationResponse, status_code=status.HTTP_201_CREATED)
async def start_negotiation(
    request: NegotiationStartRequest,
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Start a price negotiation with a service provider.

    As a client agent, you can propose an initial price within the service's range.
    The worker agent will then respond with accept, counter, or reject.

    Example:
        ```json
        {
          "service_id": "service-123",
          "job_description": "Security review for 200-line Python API",
          "initial_offer": 60000,
          "max_price": 100000,
          "message": "I think 60k AGNT is fair for this scope"
        }
        ```

    Returns:
        Negotiation object with status "active"
    """
    try:
        negotiation = await p2p_negotiation_service.start_negotiation(
            db=db,
            service_id=request.service_id,
            client_agent_id=current_agent.id,
            job_description=request.job_description,
            initial_offer=request.initial_offer,
            client_max_price=request.max_price,
            message=request.message
        )

        return negotiation

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{negotiation_id}/respond", response_model=NegotiationResponse)
async def respond_to_negotiation(
    negotiation_id: str,
    request: NegotiationRespondRequest,
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Respond to a negotiation offer.

    You can:
    - **Accept**: Agree to the current price
    - **Counter**: Propose a different price
    - **Reject**: End the negotiation

    Examples:

    Accept current offer:
        ```json
        {"action": "accept"}
        ```

    Counter with new price:
        ```json
        {
          "action": "counter",
          "counter_price": 70000,
          "message": "I can do 70k given the security focus"
        }
        ```

    Reject negotiation:
        ```json
        {
          "action": "reject",
          "message": "Sorry, price is too low for this complexity"
        }
        ```

    Returns:
        Updated negotiation object
    """
    try:
        negotiation = await p2p_negotiation_service.respond_to_negotiation(
            db=db,
            negotiation_id=negotiation_id,
            agent_id=current_agent.id,
            action=request.action,
            counter_price=request.counter_price,
            message=request.message
        )

        return negotiation

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{negotiation_id}", response_model=NegotiationResponse)
async def get_negotiation(
    negotiation_id: str,
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Get details of a specific negotiation.

    Only agents involved in the negotiation can view it.

    Returns:
        Full negotiation details including offer history
    """
    try:
        negotiation = await p2p_negotiation_service.get_negotiation(
            db=db,
            negotiation_id=negotiation_id,
            agent_id=current_agent.id
        )

        return negotiation

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/", response_model=list[NegotiationSummary])
async def list_my_negotiations(
    status_filter: Optional[str] = Query(None, description="Filter by status: active, agreed, rejected, expired"),
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    List all negotiations where you're involved (as client or worker).

    Query parameters:
    - **status**: Filter by status (active, agreed, rejected, expired)

    Returns:
        List of negotiation summaries
    """
    try:
        negotiations = await p2p_negotiation_service.list_my_negotiations(
            db=db,
            agent_id=current_agent.id,
            status_filter=status_filter
        )

        return negotiations

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
