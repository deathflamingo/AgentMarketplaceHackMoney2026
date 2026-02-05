"""Events API router for SSE and platform statistics."""

import json
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.core.events import event_bus
from app.models.agent import Agent
from app.models.service import Service
from app.models.job import Job

router = APIRouter()


@router.get("/events")
async def event_stream(request: Request):
    """
    Server-Sent Events (SSE) stream for real-time updates.

    Usage:
        const eventSource = new EventSource('/api/events');
        eventSource.addEventListener('job_created', (e) => {
            console.log(JSON.parse(e.data));
        });
    """
    async def generate():
        async for event in event_bus.subscribe():
            # Check if client disconnected
            if await request.is_disconnected():
                break

            # Send event to client
            yield {
                "event": event["type"],
                "data": json.dumps(event["data"])
            }

    return EventSourceResponse(generate())


@router.get("/stats")
async def get_platform_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Get platform-wide statistics.
    """
    # Total agents
    total_agents_query = select(func.count()).select_from(Agent)
    total_agents_result = await db.execute(total_agents_query)
    total_agents = total_agents_result.scalar()

    # Active agents (available status)
    active_agents_query = select(func.count()).where(Agent.status == 'available')
    active_agents_result = await db.execute(active_agents_query)
    active_agents = active_agents_result.scalar()

    # Total active services
    total_services_query = select(func.count()).where(Service.is_active == True)
    total_services_result = await db.execute(total_services_query)
    total_services = total_services_result.scalar()

    # Active jobs (pending, in_progress, delivered)
    active_jobs_query = select(func.count()).where(
        Job.status.in_(['pending', 'in_progress', 'delivered'])
    )
    active_jobs_result = await db.execute(active_jobs_query)
    active_jobs = active_jobs_result.scalar()

    # Completed jobs in last 24h
    yesterday = datetime.utcnow() - timedelta(days=1)
    completed_24h_query = select(func.count()).where(
        and_(
            Job.status == 'completed',
            Job.completed_at >= yesterday
        )
    )
    completed_24h_result = await db.execute(completed_24h_query)
    completed_jobs_24h = completed_24h_result.scalar()

    # Total volume (all completed jobs)
    total_volume_query = select(
        func.sum(func.coalesce(Job.settlement_amount_usd, Job.price_usd))
    ).where(Job.status == 'completed')
    total_volume_result = await db.execute(total_volume_query)
    total_volume_usd = total_volume_result.scalar() or 0

    # Volume last 24h
    volume_24h_query = select(func.sum(func.coalesce(Job.settlement_amount_usd, Job.price_usd))).where(
        and_(
            Job.status == 'completed',
            Job.completed_at >= yesterday
        )
    )
    volume_24h_result = await db.execute(volume_24h_query)
    volume_24h_usd = volume_24h_result.scalar() or 0

    return {
        "total_agents": total_agents,
        "active_agents": active_agents,
        "total_services": total_services,
        "active_jobs": active_jobs,
        "completed_jobs_24h": completed_jobs_24h,
        "total_volume_usd": float(total_volume_usd),
        "volume_24h_usd": float(volume_24h_usd),
    }


@router.get("/graph")
async def get_collaboration_graph(
    db: AsyncSession = Depends(get_db)
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get collaboration graph data (nodes and edges).

    Nodes: Agents
    Edges: Job relationships (client -> worker)
    """
    # Get all agents as nodes
    agents_query = select(Agent)
    agents_result = await db.execute(agents_query)
    agents = agents_result.scalars().all()

    nodes = [
        {
            "id": str(agent.id),
            "name": agent.name,
            "type": "agent",
            "reputation": float(agent.reputation_score),
            "jobs": agent.jobs_completed + agent.jobs_hired,
        }
        for agent in agents
    ]

    # Get job relationships as edges
    # Group by client-worker pairs and count jobs + total value
    from sqlalchemy import distinct, literal
    edges_query = select(
        Job.client_agent_id,
        Job.worker_agent_id,
        func.count(Job.id).label('jobs_count'),
        func.sum(func.coalesce(Job.settlement_amount_usd, Job.price_usd)).label('total_value')
    ).where(
        Job.status == 'completed'
    ).group_by(
        Job.client_agent_id,
        Job.worker_agent_id
    )

    edges_result = await db.execute(edges_query)
    edges_data = edges_result.all()

    edges = [
        {
            "source": str(row.client_agent_id),
            "target": str(row.worker_agent_id),
            "jobs_count": row.jobs_count,
            "total_value": float(row.total_value or 0),
        }
        for row in edges_data
    ]

    return {
        "nodes": nodes,
        "edges": edges,
    }
