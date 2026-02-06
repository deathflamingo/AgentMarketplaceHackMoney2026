"""Services API router (marketplace)."""

from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_agent
from app.models.agent import Agent
from app.schemas.service import ServiceCreate, ServiceUpdate, ServicePublic, ServiceResponse
from app.services.marketplace_service import (
    create_service,
    search_services,
    update_service,
    get_service_by_id,
    deactivate_service,
)

router = APIRouter()


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_new_service(
    service_data: ServiceCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new service (auth required).
    """
    service = await create_service(db, str(current_agent.id), service_data)
    return service


@router.get("", response_model=List[ServicePublic])
async def browse_services(
    capabilities: Optional[str] = Query(None, description="Comma-separated capabilities"),
    min_price_agnt: Optional[Decimal] = Query(None, ge=0, description="Minimum price in AGNT"),
    max_price_agnt: Optional[Decimal] = Query(None, ge=0, description="Maximum price in AGNT"),
    # Legacy USD filters (deprecated but supported for backward compatibility)
    min_price: Optional[Decimal] = Query(None, ge=0, deprecated=True),
    max_price: Optional[Decimal] = Query(None, ge=0, deprecated=True),
    output_type: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search in name/description"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Browse marketplace services (public endpoint).

    Supports filtering by AGNT price ranges. Legacy USD filters are deprecated.
    """
    from app.config import settings

    # Parse capabilities
    caps_list = None
    if capabilities:
        caps_list = [c.strip() for c in capabilities.split(",")]

    # Convert legacy USD prices to AGNT if provided
    if min_price and not min_price_agnt:
        min_price_agnt = min_price * settings.USDC_TO_AGNT_RATE
    if max_price and not max_price_agnt:
        max_price_agnt = max_price * settings.USDC_TO_AGNT_RATE

    services = await search_services(
        db=db,
        capabilities=caps_list,
        min_price=min_price_agnt,
        max_price=max_price_agnt,
        output_type=output_type,
        agent_id=agent_id,
        search_text=search,
        limit=limit,
        offset=offset
    )

    # Enrich with agent name and USD equivalents
    result = []
    for service in services:
        service_dict = ServiceResponse.model_validate(service).model_dump()
        service_dict["agent_name"] = service.agent.name

        # Calculate USD price range
        min_usd = float(service.min_price_agnt / settings.USDC_TO_AGNT_RATE)
        max_usd = float(service.max_price_agnt / settings.USDC_TO_AGNT_RATE)
        service_dict["price_range_usd"] = f"${min_usd:.2f}-${max_usd:.2f}"

        # Calculate midpoint price
        service_dict["midpoint_price_agnt"] = (service.min_price_agnt + service.max_price_agnt) / Decimal("2")

        # Legacy price_usd (use midpoint)
        service_dict["price_usd"] = (service_dict["midpoint_price_agnt"] / settings.USDC_TO_AGNT_RATE)

        result.append(ServicePublic(**service_dict))

    return result


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service_details(
    service_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get service details (public endpoint).
    """
    service = await get_service_by_id(db, service_id)

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SERVICE_NOT_FOUND",
                "message": f"Service with ID {service_id} not found"
            }
        )

    return service


@router.patch("/{service_id}", response_model=ServiceResponse)
async def update_existing_service(
    service_id: str,
    updates: ServiceUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a service (owner only).
    """
    try:
        updated_service = await update_service(
            db, service_id, str(current_agent.id), updates
        )
        return updated_service
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "SERVICE_NOT_FOUND",
                    "message": str(e)
                }
            )
        elif "not authorized" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "NOT_SERVICE_OWNER",
                    "message": str(e)
                }
            )
        raise


@router.delete("/{service_id}", response_model=ServiceResponse)
async def deactivate_existing_service(
    service_id: str,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Deactivate a service (owner only).
    """
    try:
        service = await deactivate_service(db, service_id, str(current_agent.id))
        return service
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "SERVICE_NOT_FOUND",
                    "message": str(e)
                }
            )
        elif "not authorized" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "NOT_SERVICE_OWNER",
                    "message": str(e)
                }
            )
        raise


@router.get("/agents/{agent_id}/services", response_model=List[ServicePublic])
async def get_agent_services(
    agent_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all services offered by a specific agent.
    """
    services = await search_services(db=db, agent_id=agent_id, limit=100)

    # Enrich with agent name
    result = []
    for service in services:
        service_dict = ServiceResponse.model_validate(service).model_dump()
        service_dict["agent_name"] = service.agent.name
        result.append(ServicePublic(**service_dict))

    return result
