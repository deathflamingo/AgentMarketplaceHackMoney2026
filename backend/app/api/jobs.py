"""Jobs API router."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database import get_db
from app.api.deps import get_current_agent
from app.models.agent import Agent
from app.models.job import Job
from app.schemas.job import (
    JobCreate,
    JobStart,
    JobDeliver,
    JobRequestRevision,
    JobComplete,
    JobStatusResponse,
    JobResponse,
)
from app.services.job_service import (
    create_job,
    start_job,
    deliver_job,
    request_revision,
    complete_job,
    cancel_job,
    get_job_by_id,
)

router = APIRouter()


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def hire_service(
    job_data: JobCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Hire a service (direct purchase).
    """
    try:
        job = await create_job(db, str(current_agent.id), job_data)
        return job
    except ValueError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "SERVICE_NOT_FOUND",
                    "message": str(e)
                }
            )
        elif "not available" in error_msg or "not active" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "SERVICE_NOT_AVAILABLE",
                    "message": str(e)
                }
            )
        raise


@router.get("", response_model=List[JobResponse])
async def list_jobs(
    status_filter: str = Query(None, alias="status"),
    as_role: str = Query(None, description="Filter by role: client or worker"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    List jobs for the current agent.
    """
    query = select(Job).where(
        or_(
            Job.client_agent_id == current_agent.id,
            Job.worker_agent_id == current_agent.id
        )
    )

    if as_role == "client":
        query = query.where(Job.client_agent_id == current_agent.id)
    elif as_role == "worker":
        query = query.where(Job.worker_agent_id == current_agent.id)

    if status_filter:
        query = query.where(Job.status == status_filter)

    query = query.order_by(Job.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    jobs = list(result.scalars().all())

    return jobs


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_details(
    job_id: str,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Get job details (client or worker only).
    """
    job = await get_job_by_id(db, job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": f"Job with ID {job_id} not found"
            }
        )

    # Verify access
    if str(job.client_agent_id) != str(current_agent.id) and \
       str(job.worker_agent_id) != str(current_agent.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "NOT_AUTHORIZED",
                "message": "You are not authorized to view this job"
            }
        )

    return job


@router.post("/{job_id}/start", response_model=JobStatusResponse)
async def start_job_work(
    job_id: str,
    start_data: JobStart,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Start working on a job (worker only).
    """
    try:
        job = await start_job(db, job_id, str(current_agent.id))
        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            updated_at=job.updated_at
        )
    except ValueError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "JOB_NOT_FOUND",
                    "message": str(e)
                }
            )
        elif "not authorized" in error_msg or "not the worker" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "NOT_JOB_WORKER",
                    "message": str(e)
                }
            )
        elif "cannot start" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "JOB_INVALID_STATE",
                    "message": str(e)
                }
            )
        raise


@router.post("/{job_id}/deliver", response_model=JobStatusResponse)
async def deliver_job_work(
    job_id: str,
    deliverable: JobDeliver,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit deliverable for a job (worker only).
    """
    try:
        job = await deliver_job(db, job_id, str(current_agent.id), deliverable)
        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            updated_at=job.updated_at
        )
    except ValueError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "JOB_NOT_FOUND",
                    "message": str(e)
                }
            )
        elif "not authorized" in error_msg or "not the worker" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "NOT_JOB_WORKER",
                    "message": str(e)
                }
            )
        elif "cannot deliver" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "JOB_INVALID_STATE",
                    "message": str(e)
                }
            )
        raise


@router.post("/{job_id}/request-revision", response_model=JobStatusResponse)
async def request_job_revision(
    job_id: str,
    revision_request: JobRequestRevision,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Request a revision for delivered work (client only).
    """
    try:
        job = await request_revision(
            db, job_id, str(current_agent.id), revision_request.feedback
        )
        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            updated_at=job.updated_at
        )
    except ValueError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "JOB_NOT_FOUND",
                    "message": str(e)
                }
            )
        elif "not authorized" in error_msg or "not the client" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "NOT_JOB_CLIENT",
                    "message": str(e)
                }
            )
        elif "cannot request" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "JOB_NOT_DELIVERED",
                    "message": str(e)
                }
            )
        raise


@router.post("/{job_id}/complete", response_model=JobResponse)
async def complete_job_with_rating(
    job_id: str,
    completion: JobComplete,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Complete a job with rating (client only).
    """
    try:
        job = await complete_job(
            db, job_id, str(current_agent.id), completion.rating, completion.review
        )
        return job
    except ValueError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "JOB_NOT_FOUND",
                    "message": str(e)
                }
            )
        elif "not authorized" in error_msg or "not the client" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "NOT_JOB_CLIENT",
                    "message": str(e)
                }
            )
        elif "rating must be" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_RATING",
                    "message": str(e)
                }
            )
        elif "cannot complete" in error_msg or "must be delivered" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "JOB_NOT_DELIVERED",
                    "message": str(e)
                }
            )
        raise


@router.post("/{job_id}/cancel", response_model=JobStatusResponse)
async def cancel_pending_job(
    job_id: str,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel a pending job (client only).
    """
    try:
        job = await cancel_job(db, job_id, str(current_agent.id))
        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            updated_at=job.updated_at
        )
    except ValueError as e:
        error_msg = str(e).lower()
        if "not found" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "JOB_NOT_FOUND",
                    "message": str(e)
                }
            )
        elif "not authorized" in error_msg or "not the client" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "NOT_JOB_CLIENT",
                    "message": str(e)
                }
            )
        elif "cannot cancel" in error_msg or "only pending" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "JOB_INVALID_STATE",
                    "message": str(e)
                }
            )
        raise
