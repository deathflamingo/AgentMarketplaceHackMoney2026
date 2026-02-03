"""Marketplace service for service-related business logic."""

from typing import List, Optional
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.service import Service
from app.models.agent import Agent
from app.schemas.service import ServiceCreate, ServiceUpdate
from app.core.events import event_bus


async def create_service(
    db: AsyncSession,
    agent_id: str,
    service_data: ServiceCreate
) -> Service:
    """
    Create a new service.

    Args:
        db: Database session
        agent_id: Agent UUID creating the service
        service_data: Service creation data

    Returns:
        Created service
    """
    from uuid import UUID
    service = Service(
        agent_id=UUID(agent_id) if isinstance(agent_id, str) else agent_id,
        name=service_data.name,
        description=service_data.description,
        required_inputs=service_data.required_inputs or [],
        output_type=service_data.output_type,
        output_description=service_data.output_description,
        price_usd=service_data.price_usd,
        estimated_minutes=service_data.estimated_minutes,
        capabilities_required=service_data.capabilities_required or [],
        max_concurrent=service_data.max_concurrent,
    )

    db.add(service)
    await db.commit()
    await db.refresh(service)

    # Emit event
    await event_bus.publish("service_created", {
        "service_id": str(service.id),
        "agent_id": str(agent_id),
        "name": service.name,
        "price_usd": str(service.price_usd),
    })

    return service


async def search_services(
    db: AsyncSession,
    capabilities: Optional[List[str]] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    output_type: Optional[str] = None,
    agent_id: Optional[str] = None,
    search_text: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Service]:
    """
    Search services with filters.

    Args:
        db: Database session
        capabilities: Filter by required capabilities
        min_price: Minimum price
        max_price: Maximum price
        output_type: Filter by output type
        agent_id: Filter by agent
        search_text: Search in name and description
        limit: Maximum results
        offset: Pagination offset

    Returns:
        List of matching services
    """
    query = select(Service).where(Service.is_active == True)

    # Apply filters
    if agent_id:
        query = query.where(Service.agent_id == agent_id)

    if output_type:
        query = query.where(Service.output_type == output_type)

    if min_price is not None:
        query = query.where(Service.price_usd >= min_price)

    if max_price is not None:
        query = query.where(Service.price_usd <= max_price)

    if search_text:
        search_pattern = f"%{search_text}%"
        query = query.where(
            Service.name.ilike(search_pattern) |
            Service.description.ilike(search_pattern)
        )

    # Pagination
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def update_service(
    db: AsyncSession,
    service_id: str,
    agent_id: str,
    updates: ServiceUpdate
) -> Service:
    """
    Update a service.

    Args:
        db: Database session
        service_id: Service UUID
        agent_id: Agent UUID (for ownership verification)
        updates: Fields to update

    Returns:
        Updated service

    Raises:
        ValueError: If service not found or not owned by agent
    """
    result = await db.execute(
        select(Service).where(Service.id == service_id)
    )
    service = result.scalar_one_or_none()

    if not service:
        raise ValueError("Service not found")

    if str(service.agent_id) != str(agent_id):
        raise ValueError("Not authorized to update this service")

    # Update fields
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)

    await db.commit()
    await db.refresh(service)

    # Emit event
    await event_bus.publish("service_updated", {
        "service_id": str(service.id),
        "agent_id": str(agent_id),
        "updates": update_data,
    })

    return service


async def get_service_by_id(db: AsyncSession, service_id: str) -> Optional[Service]:
    """
    Get a service by ID.

    Args:
        db: Database session
        service_id: Service UUID

    Returns:
        Service or None if not found
    """
    result = await db.execute(
        select(Service).where(Service.id == service_id)
    )
    return result.scalar_one_or_none()


async def deactivate_service(
    db: AsyncSession,
    service_id: str,
    agent_id: str
) -> Service:
    """
    Deactivate a service.

    Args:
        db: Database session
        service_id: Service UUID
        agent_id: Agent UUID (for ownership verification)

    Returns:
        Deactivated service

    Raises:
        ValueError: If service not found or not owned by agent
    """
    service = await get_service_by_id(db, service_id)

    if not service:
        raise ValueError("Service not found")

    if str(service.agent_id) != str(agent_id):
        raise ValueError("Not authorized to deactivate this service")

    service.is_active = False
    await db.commit()
    await db.refresh(service)

    return service
