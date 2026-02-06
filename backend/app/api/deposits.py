"""Deposit verification API endpoints."""

import logging
from datetime import datetime
from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_agent
from app.models.agent import Agent
from app.models.deposit_transaction import DepositTransaction
from app.schemas.deposit import DepositVerifyRequest, DepositVerifyResponse, DepositResponse
from app.services.uniswap_service import uniswap_service
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deposits", tags=["deposits"])


@router.post("/verify", response_model=DepositVerifyResponse, status_code=status.HTTP_200_OK)
async def verify_deposit(
    request: DepositVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Verify a Uniswap swap transaction and credit AGNT to agent balance.

    Flow:
    1. Check if transaction already processed (replay protection)
    2. Verify swap transaction on-chain via UniswapV4Service
    3. Ensure AGNT was received (not sent)
    4. Credit AGNT amount to agent's balance
    5. Record deposit transaction

    Args:
        request: Deposit verification request with tx_hash
        db: Database session
        current_agent: Authenticated agent

    Returns:
        Deposit verification response with updated balance

    Raises:
        400: Invalid transaction or already processed
        500: Internal error during verification
    """
    try:
        logger.info(
            f"Agent {current_agent.id} requesting deposit verification for tx: {request.tx_hash}"
        )

        # 1. Check for replay (transaction already processed)
        existing_deposit = await db.execute(
            select(DepositTransaction).where(
                DepositTransaction.swap_tx_hash == request.tx_hash
            )
        )
        existing = existing_deposit.scalar_one_or_none()

        if existing:
            if existing.status == "verified":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Transaction {request.tx_hash} already processed"
                )
            elif existing.status == "failed":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Transaction {request.tx_hash} previously failed verification"
                )

        # 2. Verify token transfer to platform wallet on-chain (USDC or AGNT)
        try:
            deposit_details = await uniswap_service.verify_deposit(
                tx_hash=request.tx_hash,
                platform_address=settings.PLATFORM_WALLET_ADDRESS
            )
        except ValueError as e:
            logger.warning(f"Deposit verification failed for {request.tx_hash}: {e}")

            # Record failed deposit
            failed_deposit = DepositTransaction(
                id=str(uuid.uuid4()),
                agent_id=current_agent.id,
                swap_tx_hash=request.tx_hash,
                usdc_amount_in=Decimal("0"),
                agnt_amount_out=Decimal("0"),
                exchange_rate=Decimal("0"),
                status="failed",
                created_at=datetime.utcnow()
            )
            db.add(failed_deposit)
            await db.commit()

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Deposit verification failed: {str(e)}"
            )

        # 3. Extract deposit details
        usdc_spent = deposit_details['usdc_amount']
        agnt_received = deposit_details['agnt_credit']
        exchange_rate = deposit_details['exchange_rate']

        # Validate minimum expected amount
        if agnt_received < request.expected_agnt_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"AGNT credit {agnt_received} below expected minimum {request.expected_agnt_amount}"
            )

        logger.info(
            f"Deposit verified: {usdc_spent} USDC → {agnt_received} AGNT "
            f"(rate: {exchange_rate} AGNT/USDC)"
        )

        # 4. Credit agent balance
        current_agent.balance += agnt_received
        current_agent.total_earned += agnt_received  # Consider deposits as "earned"

        # 5. Record deposit transaction
        deposit = DepositTransaction(
            id=str(uuid.uuid4()),
            agent_id=current_agent.id,
            swap_tx_hash=request.tx_hash,
            usdc_amount_in=usdc_spent,
            agnt_amount_out=agnt_received,
            exchange_rate=exchange_rate,
            status="verified",
            created_at=datetime.utcnow(),
            verified_at=datetime.utcnow()
        )

        db.add(deposit)
        await db.commit()
        await db.refresh(deposit)
        await db.refresh(current_agent)

        logger.info(
            f"✅ Deposit verified for agent {current_agent.id}: "
            f"+{agnt_received} AGNT (new balance: {current_agent.balance})"
        )

        return DepositVerifyResponse(
            success=True,
            message=f"Successfully deposited {agnt_received} AGNT",
            deposit=DepositResponse.model_validate(deposit),
            agent_new_balance=current_agent.balance
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying deposit: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error during deposit verification"
        )


@router.get("/history", response_model=list[DepositResponse])
async def get_deposit_history(
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
    limit: int = 50,
    offset: int = 0
):
    """
    Get deposit transaction history for the current agent.

    Args:
        db: Database session
        current_agent: Authenticated agent
        limit: Maximum number of deposits to return
        offset: Number of deposits to skip

    Returns:
        List of deposit transactions
    """
    result = await db.execute(
        select(DepositTransaction)
        .where(DepositTransaction.agent_id == current_agent.id)
        .order_by(DepositTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    deposits = result.scalars().all()

    return [DepositResponse.model_validate(d) for d in deposits]


@router.get("/{deposit_id}", response_model=DepositResponse)
async def get_deposit(
    deposit_id: str,
    db: AsyncSession = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Get details of a specific deposit transaction.

    Args:
        deposit_id: Deposit transaction ID
        db: Database session
        current_agent: Authenticated agent

    Returns:
        Deposit transaction details

    Raises:
        404: Deposit not found
    """
    result = await db.execute(
        select(DepositTransaction).where(
            DepositTransaction.id == deposit_id,
            DepositTransaction.agent_id == current_agent.id
        )
    )
    deposit = result.scalar_one_or_none()

    if not deposit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deposit {deposit_id} not found"
        )

    return DepositResponse.model_validate(deposit)
