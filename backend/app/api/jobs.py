"""Jobs API router with x402 payment support."""

import logging
from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database import get_db
from app.api.deps import get_current_agent
from app.models.agent import Agent
from app.models.job import Job
from app.models.service import Service
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
from app.middleware.x402 import create_x402_response, verify_x402_payment
from app.services.agent_service import update_balance

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def hire_service(
    job_data: JobCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    x402_payment_proof: Optional[str] = Header(None, alias="x402-payment-proof"),
    payment_method: Optional[str] = Header("balance", alias="x-payment-method")  # "balance" (default) or "x402"
):
    """
    Hire a service with balance payment or negotiated quote.

    **Negotiated Pricing Flow:**
    1. Request quote: POST /api/quotes/request
    2. Receive negotiated price (valid 1 hour)
    3. Hire service with quote_id and agreed_price
    4. Payment deducted from AGNT balance

    **Fixed Pricing Flow:**
    1. Hire service without quote_id
    2. Uses service midpoint price
    3. Payment deducted from AGNT balance

    **x402 Flow (Direct Wallet Payment - Legacy):**
    1. Set x-payment-method: x402
    2. First request → Returns 402 with payment details
    3. Send USDC to worker's wallet
    4. Retry with x402-payment-proof header

    Headers:
        - x-payment-method: "balance" (default) or "x402"
        - x402-payment-proof: Transaction hash (for x402 payments)
    """
    try:
        from app.models.price_quote import PriceQuote
        from app.config import settings
        from datetime import datetime

        # Fetch service to check price and worker
        result = await db.execute(
            select(Service).where(Service.id == job_data.service_id)
        )
        service = result.scalar_one_or_none()

        if not service:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found"
            )

        if not service.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service is not available"
            )

        # Get worker's wallet address
        result = await db.execute(
            select(Agent).where(Agent.id == service.agent_id)
        )
        worker_agent = result.scalar_one_or_none()

        # Determine price (negotiated vs fixed)
        job_price = None
        quote = None
        negotiation = None
        negotiated_by = "agent"

        if job_data.negotiation_id:
            # P2P negotiation - validate and use agreed price
            from app.models.negotiation import Negotiation

            result = await db.execute(
                select(Negotiation).where(
                    Negotiation.id == job_data.negotiation_id,
                    Negotiation.client_agent_id == current_agent.id,
                    Negotiation.service_id == service.id
                )
            )
            negotiation = result.scalar_one_or_none()

            if not negotiation:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Negotiation not found or does not belong to you"
                )

            if negotiation.status != "agreed":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Negotiation status is '{negotiation.status}', not 'agreed'. Cannot create job."
                )

            # Use the agreed price from negotiation
            job_price = negotiation.current_price
            negotiated_by = "p2p"

            logger.info(f"Using P2P negotiated price: negotiation={negotiation.id}, price={job_price} AGNT")

        elif job_data.quote_id:
            # Validate quote
            result = await db.execute(
                select(PriceQuote).where(
                    PriceQuote.id == job_data.quote_id,
                    PriceQuote.client_agent_id == current_agent.id,
                    PriceQuote.service_id == service.id
                )
            )
            quote = result.scalar_one_or_none()

            if not quote:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Quote not found or does not belong to you"
                )

            if quote.status == "expired" or quote.valid_until < datetime.utcnow():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Quote has expired. Please request a new quote."
                )

            if quote.status != "pending":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Quote already {quote.status}"
                )

            # Validate agreed price matches quote
            if job_data.agreed_price and abs(job_data.agreed_price - quote.quoted_price) > Decimal("0.01"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Agreed price {job_data.agreed_price} does not match quote {quote.quoted_price}"
                )

            job_price = quote.quoted_price
            negotiated_by = "llm"

            # Mark quote as accepted
            quote.status = "accepted"
            quote.accepted_at = datetime.utcnow()

            logger.info(f"Using negotiated quote {quote.id}: price={job_price} AGNT")

        else:
            # Use service midpoint price
            job_price = (service.min_price_agnt + service.max_price_agnt) / Decimal("2")
            logger.info(f"Using service midpoint price: {job_price} AGNT")

        # Determine payment method
        if payment_method == "balance":
            # Use internal AGNT balance
            logger.info(f"Job payment using AGNT balance: client={current_agent.id}, amount={job_price}")

            # Check sufficient balance
            if current_agent.balance < job_price:
                usdc_required = job_price / settings.USDC_TO_AGNT_RATE
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "error": "insufficient_balance",
                        "message": f"Insufficient balance. Required: {job_price} AGNT (~${usdc_required:.2f}), Available: {current_agent.balance} AGNT",
                        "required_agnt": str(job_price),
                        "required_usd": str(usdc_required),
                        "available_agnt": str(current_agent.balance)
                    }
                )

            # Deduct from client
            await update_balance(db, str(current_agent.id), -job_price)

            # Create job with pricing metadata
            job = await create_job(
                db,
                str(current_agent.id),
                job_data,
                price_agnt=job_price,
                quote_id=job_data.quote_id,
                negotiation_id=job_data.negotiation_id,
                negotiated_by=negotiated_by
            )

            logger.info(f"Job created with AGNT balance payment: job_id={job.id}, price={job_price} AGNT")

            # Enrich response with USD equivalent
            job_response = JobResponse.model_validate(job)
            job_response.price_usd = job_price / settings.USDC_TO_AGNT_RATE

            return job_response

        else:
            # x402: Direct wallet payment (USDC)
            # Convert AGNT price to USDC for x402 payment
            usdc_price = job_price / settings.USDC_TO_AGNT_RATE

            if not x402_payment_proof:
                # No payment proof provided - return 402 with payment details
                logger.info(f"x402 payment required: service={service.id}, worker={worker_agent.id}, price={usdc_price} USDC")

                if not worker_agent.wallet_address:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Worker has no wallet address configured. Use x-payment-method: balance instead."
                    )

                return create_x402_response(
                    amount=usdc_price,
                    recipient_address=worker_agent.wallet_address,
                    message=f"Payment of {usdc_price:.2f} USDC required to hire this service ({job_price} AGNT equivalent)"
                )

            # Payment proof provided - verify it
            logger.info(f"Verifying x402 payment: tx_hash={x402_payment_proof}, amount={usdc_price} USDC")

            if not worker_agent.wallet_address:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Worker has no wallet address configured"
                )

            is_valid = await verify_x402_payment(
                tx_hash=x402_payment_proof,
                expected_amount=usdc_price,
                recipient_address=worker_agent.wallet_address
            )

            if not is_valid:
                logger.warning(f"Invalid x402 payment proof: tx_hash={x402_payment_proof}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid payment proof. Please verify the transaction hash and amount."
                )

            # Payment verified - create job
            job = await create_job(
                db,
                str(current_agent.id),
                job_data,
                price_agnt=job_price,
                quote_id=job_data.quote_id,
                negotiation_id=job_data.negotiation_id,
                negotiated_by=negotiated_by
            )

            # Store payment proof in job metadata
            if job.input_data is None:
                job.input_data = {}
            job.input_data["x402_payment_proof"] = x402_payment_proof
            job.input_data["x402_recipient"] = worker_agent.wallet_address
            job.input_data["x402_usdc_amount"] = str(usdc_price)
            job.input_data["x402_agnt_equivalent"] = str(job_price)
            await db.commit()

            logger.info(f"Job created with x402 payment: job_id={job.id}, tx_hash={x402_payment_proof}")

            # Enrich response with USD equivalent
            job_response = JobResponse.model_validate(job)
            job_response.price_usd = usdc_price

            return job_response

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
