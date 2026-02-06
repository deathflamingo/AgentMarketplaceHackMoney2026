"""Withdrawal API endpoints."""

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_agent
from app.models.agent import Agent
from app.models.withdrawal_transaction import WithdrawalTransaction
from app.schemas.withdrawal import WithdrawalRequest, WithdrawalResponse, WithdrawalRequestResponse
from app.services.withdrawal_service import withdrawal_service
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])


@router.post("/request", response_model=WithdrawalRequestResponse, status_code=status.HTTP_201_CREATED)
async def request_withdrawal(
    request: WithdrawalRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Request a withdrawal of AGNT to USDC.

    Flow:
    1. Validate withdrawal request (balance, minimum, rate limit)
    2. Calculate fee (default 0.5%)
    3. Deduct AGNT from agent balance immediately
    4. Create withdrawal record with status "pending"
    5. Queue withdrawal execution in background
    6. Platform executes swap and transfer asynchronously

    Args:
        request: Withdrawal request with amount and recipient address
        background_tasks: FastAPI background tasks
        db: Database session
        current_agent: Authenticated agent

    Returns:
        Withdrawal request response with estimated USDC amount

    Raises:
        400: Validation failed (insufficient balance, rate limit, etc.)
        500: Internal error
    """
    try:
        logger.info(
            f"Agent {current_agent.id} requesting withdrawal: "
            f"{request.agnt_amount} AGNT to {request.recipient_address}"
        )

        # Create withdrawal request (this validates and deducts balance)
        try:
            withdrawal = await withdrawal_service.create_withdrawal_request(
                agent=current_agent,
                agnt_amount=request.agnt_amount,
                recipient_address=request.recipient_address,
                db=db
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

        # Refresh agent to get updated balance
        await db.refresh(current_agent)

        # Execute withdrawal synchronously so the response includes the tx hash
        success = await withdrawal_service.execute_withdrawal(withdrawal, db)
        await db.refresh(withdrawal)

        if success:
            message = f"Withdrawal completed. Sent USDC to {request.recipient_address}"
        else:
            message = f"Withdrawal failed: {withdrawal.error_message or 'unknown error'}"

        logger.info(
            f"Withdrawal {withdrawal.id}: status={withdrawal.status}, "
            f"tx={withdrawal.transfer_tx_hash}"
        )

        return WithdrawalRequestResponse(
            success=success,
            message=message,
            withdrawal=WithdrawalResponse.model_validate(withdrawal),
            agent_new_balance=current_agent.balance,
            estimated_usdc=withdrawal.usdc_amount_out,
            fee_agnt=withdrawal.fee_agnt
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating withdrawal request: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error creating withdrawal request"
        )


@router.get("/history", response_model=list[WithdrawalResponse])
async def get_withdrawal_history(
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
    limit: int = 50,
    offset: int = 0
):
    """
    Get withdrawal transaction history for the current agent.

    Args:
        db: Database session
        current_agent: Authenticated agent
        limit: Maximum number of withdrawals to return
        offset: Number of withdrawals to skip

    Returns:
        List of withdrawal transactions
    """
    result = await db.execute(
        select(WithdrawalTransaction)
        .where(WithdrawalTransaction.agent_id == current_agent.id)
        .order_by(WithdrawalTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    withdrawals = result.scalars().all()

    return [WithdrawalResponse.model_validate(w) for w in withdrawals]


@router.get("/{withdrawal_id}", response_model=WithdrawalResponse)
async def get_withdrawal(
    withdrawal_id: str,
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Get details of a specific withdrawal transaction.

    Args:
        withdrawal_id: Withdrawal transaction ID
        db: Database session
        current_agent: Authenticated agent

    Returns:
        Withdrawal transaction details

    Raises:
        404: Withdrawal not found
    """
    result = await db.execute(
        select(WithdrawalTransaction).where(
            WithdrawalTransaction.id == withdrawal_id,
            WithdrawalTransaction.agent_id == current_agent.id
        )
    )
    withdrawal = result.scalar_one_or_none()

    if not withdrawal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Withdrawal {withdrawal_id} not found"
        )

    return WithdrawalResponse.model_validate(withdrawal)


@router.get("/limits/current", response_model=dict)
async def get_withdrawal_limits(
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Get current withdrawal limits and available quota for the agent.

    Returns:
        Dictionary with limit information
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func

    # Check recent withdrawals (last hour)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    result = await db.execute(
        select(func.count(WithdrawalTransaction.id))
        .where(
            WithdrawalTransaction.agent_id == current_agent.id,
            WithdrawalTransaction.created_at >= one_hour_ago
        )
    )
    recent_withdrawals = result.scalar()

    return {
        "min_withdrawal_amount": float(settings.WITHDRAWAL_MIN_AMOUNT),
        "fee_percent": float(settings.WITHDRAWAL_FEE_PERCENT),
        "rate_limit_per_hour": settings.WITHDRAWAL_RATE_LIMIT_PER_HOUR,
        "withdrawals_used_this_hour": recent_withdrawals,
        "withdrawals_remaining_this_hour": max(0, settings.WITHDRAWAL_RATE_LIMIT_PER_HOUR - recent_withdrawals),
        "current_balance": float(current_agent.balance)
    }


async def execute_withdrawal_task(withdrawal_id: str, db: AsyncSession):
    """
    Background task to execute withdrawal.

    Args:
        withdrawal_id: ID of withdrawal to execute
        db: Database session
    """
    try:
        # Fetch withdrawal
        result = await db.execute(
            select(WithdrawalTransaction).where(
                WithdrawalTransaction.id == withdrawal_id
            )
        )
        withdrawal = result.scalar_one_or_none()

        if not withdrawal:
            logger.error(f"Withdrawal {withdrawal_id} not found for execution")
            return

        if withdrawal.status != "pending":
            logger.warning(f"Withdrawal {withdrawal_id} already processed (status: {withdrawal.status})")
            return

        # Execute withdrawal
        success = await withdrawal_service.execute_withdrawal(withdrawal, db)

        if success:
            logger.info(f"✅ Withdrawal {withdrawal_id} executed successfully")
        else:
            logger.error(f"❌ Withdrawal {withdrawal_id} execution failed")

    except Exception as e:
        logger.error(f"Error in withdrawal execution task: {e}", exc_info=True)
