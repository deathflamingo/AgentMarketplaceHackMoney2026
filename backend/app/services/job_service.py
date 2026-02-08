"""Job service for complex job workflow business logic."""

from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.job import Job
from app.models.service import Service
from app.models.deliverable import Deliverable
from app.models.activity_log import ActivityLog
from app.schemas.job import JobCreate, JobDeliver
from app.core.events import event_bus
from app.services.message_service import create_auto_message
from app.services.reputation_service import update_reputation


# Valid state transitions
VALID_TRANSITIONS = {
    'pending': ['in_progress', 'cancelled'],
    'in_progress': ['delivered', 'failed'],
    'delivered': ['completed', 'revision_requested'],
    'revision_requested': ['delivered'],
}


async def create_job(
    db: AsyncSession,
    client_agent_id: str,
    job_data: JobCreate,
    price_agnt: Optional[Any] = None,
    quote_id: Optional[str] = None,
    negotiation_id: Optional[str] = None,
    negotiated_by: str = "agent"
) -> Job:
    """
    Create a new job (direct purchase of a service).

    Args:
        db: Database session
        client_agent_id: Client agent UUID
        job_data: Job creation data
        price_agnt: Agreed price in AGNT (if None, uses service midpoint)
        quote_id: Optional quote ID for LLM-negotiated pricing
        negotiation_id: Optional negotiation ID for P2P-negotiated pricing
        negotiated_by: "agent", "llm", or "p2p"

    Returns:
        Created job

    Raises:
        ValueError: If service not found or not active
    """
    from decimal import Decimal

    # Fetch service
    result = await db.execute(
        select(Service).where(Service.id == job_data.service_id)
    )
    service = result.scalar_one_or_none()

    if not service:
        raise ValueError("Service not found")

    if not service.is_active:
        raise ValueError("Service is not available")

    # Determine price
    if price_agnt is None:
        # Use service midpoint price
        price_agnt = (service.min_price_agnt + service.max_price_agnt) / Decimal("2")

    # Calculate USD price for backward compatibility
    from app.config import settings
    price_usd = price_agnt / settings.USDC_TO_AGNT_RATE

    # Create job with price locked
    title = job_data.title or f"Hire: {service.name}"

    # Convert input_data to dict if it's a string
    input_data = job_data.input_data
    if isinstance(input_data, str):
        input_data = {"input": input_data}

    job = Job(
        service_id=service.id,
        client_agent_id=client_agent_id,
        worker_agent_id=service.agent_id,  # Worker is service owner
        parent_job_id=job_data.parent_job_id,
        title=title,
        input_data=input_data,
        price_agnt=price_agnt,  # Lock AGNT price
        price_usd=price_usd,  # Legacy field for backward compatibility
        final_price_agreed=price_agnt,
        initial_price_offer=(service.min_price_agnt + service.max_price_agnt) / Decimal("2"),
        negotiated_by=negotiated_by,
        quote_id=quote_id,
        negotiation_id=negotiation_id,
        status='pending',
    )

    db.add(job)
    await db.commit()
    await db.refresh(job, ["deliverables"])

    # Create message to worker
    await create_auto_message(
        db=db,
        message_type="job_created",
        from_agent_id=client_agent_id,
        to_agent_id=str(service.agent_id),
        job_id=str(job.id),
        content_data={
            "message": "You've been hired!",
            "job_id": str(job.id),
            "title": title,
            "price_agnt": str(price_agnt),
            "negotiated": negotiated_by == "llm",
        }
    )

    # Log activity
    activity = ActivityLog(
        event_type="job_created",
        agent_id=client_agent_id,
        job_id=job.id,
        service_id=service.id,
        data={
            "client_id": str(client_agent_id),
            "worker_id": str(service.agent_id),
            "price_agnt": str(price_agnt),
            "negotiated_by": negotiated_by,
            "quote_id": quote_id,
        }
    )
    db.add(activity)
    await db.commit()

    # Emit event
    await event_bus.publish("job_created", {
        "job_id": str(job.id),
        "client_id": str(client_agent_id),
        "worker_id": str(service.agent_id),
        "service_name": service.name,
        "price_usd": str(job.price_usd),
    })

    return job


async def start_job(
    db: AsyncSession,
    job_id: str,
    worker_agent_id: str
) -> Job:
    """
    Start a job (worker accepts and begins work).

    Args:
        db: Database session
        job_id: Job UUID
        worker_agent_id: Worker agent UUID

    Returns:
        Updated job

    Raises:
        ValueError: If job not found, not owned by worker, or invalid state
    """
    job = await get_job_by_id(db, job_id)

    if not job:
        raise ValueError("Job not found")

    if str(job.worker_agent_id) != str(worker_agent_id):
        raise ValueError("Not authorized - you are not the worker for this job")

    if job.status != 'pending':
        raise ValueError(f"Cannot start job with status '{job.status}'")

    # Update status
    job.status = 'in_progress'
    job.started_at = datetime.utcnow()

    await db.commit()
    await db.refresh(job)

    # Create message to client
    await create_auto_message(
        db=db,
        message_type="job_started",
        from_agent_id=worker_agent_id,
        to_agent_id=str(job.client_agent_id),
        job_id=str(job.id),
        content_data={
            "message": "Work has started on your job",
            "job_id": str(job.id),
        }
    )

    # Log activity
    activity = ActivityLog(
        event_type="job_started",
        agent_id=worker_agent_id,
        job_id=job.id,
        data={"worker_id": str(worker_agent_id)}
    )
    db.add(activity)
    await db.commit()

    # Emit event
    await event_bus.publish("job_started", {
        "job_id": str(job.id),
        "worker_id": str(worker_agent_id),
    })

    return job


async def deliver_job(
    db: AsyncSession,
    job_id: str,
    worker_agent_id: str,
    deliverable_data: JobDeliver
) -> Job:
    """
    Deliver work for a job.

    Args:
        db: Database session
        job_id: Job UUID
        worker_agent_id: Worker agent UUID
        deliverable_data: Deliverable data

    Returns:
        Updated job

    Raises:
        ValueError: If job not found, not owned by worker, or invalid state
    """
    job = await get_job_by_id(db, job_id)

    if not job:
        raise ValueError("Job not found")

    if str(job.worker_agent_id) != str(worker_agent_id):
        raise ValueError("Not authorized - you are not the worker for this job")

    if job.status not in ['in_progress', 'revision_requested']:
        raise ValueError(f"Cannot deliver job with status '{job.status}'")

    # Determine version (increment if revision)
    existing_deliverables = await db.execute(
        select(Deliverable).where(Deliverable.job_id == job.id)
    )
    version = len(list(existing_deliverables.scalars().all())) + 1

    # Create deliverable
    deliverable = Deliverable(
        job_id=job.id,
        artifact_type=deliverable_data.artifact_type,
        content=deliverable_data.content,
        artifact_metadata=deliverable_data.artifact_metadata,
        version=version,
    )
    db.add(deliverable)

    # Update job status
    job.status = 'delivered'
    job.delivered_at = datetime.utcnow()

    await db.commit()
    await db.refresh(job)

    # Create message to client
    await create_auto_message(
        db=db,
        message_type="work_delivered",
        from_agent_id=worker_agent_id,
        to_agent_id=str(job.client_agent_id),
        job_id=str(job.id),
        content_data={
            "message": "Work has been delivered",
            "job_id": str(job.id),
            "version": version,
        }
    )

    # Log activity
    activity = ActivityLog(
        event_type="job_delivered",
        agent_id=worker_agent_id,
        job_id=job.id,
        data={
            "worker_id": str(worker_agent_id),
            "version": version,
        }
    )
    db.add(activity)
    await db.commit()

    # Emit event
    await event_bus.publish("job_delivered", {
        "job_id": str(job.id),
        "worker_id": str(worker_agent_id),
        "version": version,
    })

    return job


async def request_revision(
    db: AsyncSession,
    job_id: str,
    client_agent_id: str,
    feedback: str
) -> Job:
    """
    Request a revision for delivered work.

    Args:
        db: Database session
        job_id: Job UUID
        client_agent_id: Client agent UUID
        feedback: Revision feedback

    Returns:
        Updated job

    Raises:
        ValueError: If job not found, not owned by client, or invalid state
    """
    job = await get_job_by_id(db, job_id)

    if not job:
        raise ValueError("Job not found")

    if str(job.client_agent_id) != str(client_agent_id):
        raise ValueError("Not authorized - you are not the client for this job")

    if job.status != 'delivered':
        raise ValueError(f"Cannot request revision for job with status '{job.status}'")

    # Update status
    job.status = 'revision_requested'

    await db.commit()
    await db.refresh(job)

    # Create message to worker
    await create_auto_message(
        db=db,
        message_type="revision_requested",
        from_agent_id=client_agent_id,
        to_agent_id=str(job.worker_agent_id),
        job_id=str(job.id),
        content_data={
            "message": "Revision needed",
            "job_id": str(job.id),
            "feedback": feedback,
        }
    )

    # Log activity
    activity = ActivityLog(
        event_type="job_revision_requested",
        agent_id=client_agent_id,
        job_id=job.id,
        data={"feedback": feedback}
    )
    db.add(activity)
    await db.commit()

    return job


async def complete_job(
    db: AsyncSession,
    job_id: str,
    client_agent_id: str,
    rating: int,
    review: Optional[str] = None
) -> Job:
    """
    Complete a job with rating.

    Args:
        db: Database session
        job_id: Job UUID
        client_agent_id: Client agent UUID
        rating: Rating 1-5
        review: Optional review text

    Returns:
        Updated job

    Raises:
        ValueError: If job not found, not owned by client, or invalid state
    """
    job = await get_job_by_id(db, job_id)

    if not job:
        raise ValueError("Job not found")

    if str(job.client_agent_id) != str(client_agent_id):
        raise ValueError("Not authorized - you are not the client for this job")

    if job.status != 'delivered':
        raise ValueError(f"Cannot complete job with status '{job.status}'. Job must be delivered first.")

    if not 1 <= rating <= 5:
        raise ValueError("Rating must be between 1 and 5")

    # Update job
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    job.rating = rating
    job.review = review

    await db.commit()

    # Update worker reputation
    await update_reputation(db, str(job.worker_agent_id), rating)

    # Transfer payment to worker (AGNT balance)
    from app.services.agent_service import update_balance
    await update_balance(db, str(job.worker_agent_id), job.price_agnt)

    # Update statistics
    from app.models.agent import Agent
    # Worker stats
    result = await db.execute(
        select(Agent).where(Agent.id == job.worker_agent_id)
    )
    worker = result.scalar_one()
    worker.jobs_completed += 1
    worker.total_earned += job.price_agnt  # Use AGNT, not USD

    # Client stats
    result = await db.execute(
        select(Agent).where(Agent.id == client_agent_id)
    )
    client = result.scalar_one()
    client.jobs_hired += 1
    client.total_spent += job.price_agnt  # Use AGNT, not USD

    await db.commit()
    await db.refresh(job)

    # Create message to worker
    await create_auto_message(
        db=db,
        message_type="job_completed",
        from_agent_id=client_agent_id,
        to_agent_id=str(job.worker_agent_id),
        job_id=str(job.id),
        content_data={
            "message": f"Job completed - Rating: {rating}/5",
            "job_id": str(job.id),
            "rating": rating,
            "review": review,
        }
    )

    # Log activity
    activity = ActivityLog(
        event_type="job_completed",
        agent_id=client_agent_id,
        job_id=job.id,
        data={
            "rating": rating,
            "review": review,
        }
    )
    db.add(activity)
    await db.commit()

    # Emit event
    await event_bus.publish("job_completed", {
        "job_id": str(job.id),
        "rating": rating,
        "worker_id": str(job.worker_agent_id),
    })

    return job


async def cancel_job(
    db: AsyncSession,
    job_id: str,
    client_agent_id: str
) -> Job:
    """
    Cancel a pending job.

    Args:
        db: Database session
        job_id: Job UUID
        client_agent_id: Client agent UUID

    Returns:
        Cancelled job

    Raises:
        ValueError: If job not found, not owned by client, or not pending
    """
    job = await get_job_by_id(db, job_id)

    if not job:
        raise ValueError("Job not found")

    if str(job.client_agent_id) != str(client_agent_id):
        raise ValueError("Not authorized - you are not the client for this job")

    if job.status != 'pending':
        raise ValueError(f"Cannot cancel job with status '{job.status}'. Only pending jobs can be cancelled.")

    # Update status
    job.status = 'cancelled'

    await db.commit()
    await db.refresh(job)

    # Create message to worker
    await create_auto_message(
        db=db,
        message_type="job_cancelled",
        from_agent_id=client_agent_id,
        to_agent_id=str(job.worker_agent_id),
        job_id=str(job.id),
        content_data={
            "message": "Job has been cancelled",
            "job_id": str(job.id),
        }
    )

    # Log activity
    activity = ActivityLog(
        event_type="job_cancelled",
        agent_id=client_agent_id,
        job_id=job.id,
        data={}
    )
    db.add(activity)
    await db.commit()

    # Emit event
    await event_bus.publish("job_cancelled", {
        "job_id": str(job.id),
        "client_id": str(client_agent_id),
    })

    return job


async def get_job_by_id(db: AsyncSession, job_id: str) -> Optional[Job]:
    """
    Get a job by ID with relationships loaded.

    Args:
        db: Database session
        job_id: Job UUID

    Returns:
        Job or None if not found
    """
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.deliverables))
    )
    return result.scalar_one_or_none()


async def get_job_tree(db: AsyncSession, job_id: str) -> Dict[str, Any]:
    """
    Get job with parent and sub-jobs (hierarchical structure).

    Args:
        db: Database session
        job_id: Job UUID

    Returns:
        Hierarchical job structure

    Raises:
        ValueError: If job not found
    """
    job = await get_job_by_id(db, job_id)

    if not job:
        raise ValueError("Job not found")

    # Fetch sub-jobs
    result = await db.execute(
        select(Job).where(Job.parent_job_id == job_id)
    )
    sub_jobs = list(result.scalars().all())

    # Fetch parent job if exists
    parent_job = None
    if job.parent_job_id:
        parent_job = await get_job_by_id(db, str(job.parent_job_id))

    return {
        "job": job,
        "parent": parent_job,
        "sub_jobs": sub_jobs,
    }
