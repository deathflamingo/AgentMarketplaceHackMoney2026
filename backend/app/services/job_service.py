"""Job service for complex job workflow business logic."""

from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.job import Job
from app.models.service import Service
from app.models.deliverable import Deliverable
from app.models.activity_log import ActivityLog
from app.schemas.job import JobCreate, JobDeliver
from app.services.escrow_service import lock_escrow, refund_escrow, release_escrow
from app.services.llm_usage_service import get_usage_summary
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
    job_data: JobCreate
) -> Job:
    """
    Create a new job (direct purchase of a service).

    Args:
        db: Database session
        client_agent_id: Client agent UUID
        job_data: Job creation data

    Returns:
        Created job

    Raises:
        ValueError: If service not found or not active
    """
    # Fetch service
    result = await db.execute(
        select(Service).where(Service.id == job_data.service_id)
    )
    service = result.scalar_one_or_none()

    if not service:
        raise ValueError("Service not found")

    if not service.is_active:
        raise ValueError("Service is not available")

    if service.price_per_1k_tokens_usd <= 0:
        raise ValueError("Service pricing not configured")

    if job_data.client_max_budget_usd < service.worker_min_payout_usd:
        raise ValueError("Client budget is below worker minimum payout")

    # Create job with price and token pricing locked from service
    title = job_data.title or f"Hire: {service.name}"
    estimated_price = service.price_usd
    if estimated_price == 0:
        estimated_price = (service.price_per_1k_tokens_usd * Decimal(service.avg_tokens_per_job or 0)) / Decimal(1000)

    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        service_id=service.id,
        client_agent_id=client_agent_id,
        worker_agent_id=service.agent_id,  # Worker is service owner
        parent_job_id=job_data.parent_job_id,
        title=title,
        input_data=job_data.input_data,
        price_usd=estimated_price,  # Locked estimate for legacy reporting
        price_per_1k_tokens_usd=service.price_per_1k_tokens_usd,
        worker_min_payout_usd=service.worker_min_payout_usd,
        client_max_budget_usd=job_data.client_max_budget_usd,
        avg_tokens_per_job=service.avg_tokens_per_job,
        escrow_status="funded",
        escrow_amount_usd=job_data.client_max_budget_usd,
        escrowed_at=datetime.utcnow(),
        status='pending',
    )

    db.add(job)

    # Lock escrow funds before finalizing job
    await lock_escrow(
        db,
        client_agent_id=client_agent_id,
        job_id=job_id,
        amount=job_data.client_max_budget_usd,
        commit=False
    )

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
            "price_usd": str(job.price_usd),
            "client_max_budget_usd": str(job.client_max_budget_usd),
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
            "price_usd": str(job.price_usd),
            "client_max_budget_usd": str(job.client_max_budget_usd),
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
        "client_max_budget_usd": str(job.client_max_budget_usd),
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

    # Compute usage summary and settlement
    usage_summary = await get_usage_summary(db, str(job.id))
    job.usage_prompt_tokens = usage_summary["prompt_tokens"]
    job.usage_completion_tokens = usage_summary["completion_tokens"]
    job.usage_total_tokens = usage_summary["total_tokens"]
    job.usage_cost_usd = usage_summary["cost_usd"]

    # Settlement amount within bounds
    payout = job.usage_cost_usd
    if payout < job.worker_min_payout_usd:
        payout = job.worker_min_payout_usd
    if payout > job.client_max_budget_usd:
        payout = job.client_max_budget_usd

    job.settlement_amount_usd = payout
    job.escrow_status = "released"
    job.released_at = datetime.utcnow()

    # Release escrow (payout to worker, refund remainder to client)
    await release_escrow(
        db,
        client_agent_id=str(job.client_agent_id),
        worker_agent_id=str(job.worker_agent_id),
        job_id=str(job.id),
        payout_amount=payout,
        escrow_total=job.escrow_amount_usd,
        commit=False
    )

    await db.commit()

    # Update worker reputation
    await update_reputation(db, str(job.worker_agent_id), rating)

    # Update statistics
    from app.models.agent import Agent
    # Worker stats
    result = await db.execute(
        select(Agent).where(Agent.id == job.worker_agent_id)
    )
    worker = result.scalar_one()
    worker.jobs_completed += 1
    worker.total_earned += job.settlement_amount_usd

    # Client stats
    result = await db.execute(
        select(Agent).where(Agent.id == client_agent_id)
    )
    client = result.scalar_one()
    client.jobs_hired += 1
    client.total_spent += job.settlement_amount_usd

    await db.commit()
    await db.refresh(job)

    # Update service avg_tokens_per_job (simple moving average)
    result = await db.execute(
        select(Service).where(Service.id == job.service_id)
    )
    service = result.scalar_one_or_none()
    if service:
        previous_avg = service.avg_tokens_per_job or 0
        completed_count = max(worker.jobs_completed, 1)
        # basic smoothing: new_avg = (prev_avg * (n-1) + latest) / n
        service.avg_tokens_per_job = int((previous_avg * (completed_count - 1) + job.usage_total_tokens) / completed_count)
        await db.commit()

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
    job.escrow_status = "refunded"
    job.refunded_at = datetime.utcnow()

    # Refund escrow to client
    await refund_escrow(
        db,
        client_agent_id=str(job.client_agent_id),
        job_id=str(job.id),
        amount=job.escrow_amount_usd,
        commit=False
    )

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


async def update_job_usage_totals(db: AsyncSession, job_id: str) -> Job:
    """Recompute and store usage totals on the job."""
    job = await get_job_by_id(db, job_id)
    if not job:
        raise ValueError("Job not found")

    summary = await get_usage_summary(db, job_id)
    job.usage_prompt_tokens = summary["prompt_tokens"]
    job.usage_completion_tokens = summary["completion_tokens"]
    job.usage_total_tokens = summary["total_tokens"]
    job.usage_cost_usd = summary["cost_usd"]

    await db.commit()
    await db.refresh(job)
    return job
