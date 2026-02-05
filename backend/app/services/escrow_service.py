"""Escrow service for locking, releasing, and refunding internal balances."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.agent import Agent
from app.models.ledger_transaction import LedgerTransaction, LedgerTransactionType


async def lock_escrow(
    db: AsyncSession,
    client_agent_id: str,
    job_id: str,
    amount: Decimal,
    currency: str = "USDC",
    commit: bool = True
) -> None:
    """Move funds from client available balance to escrow balance."""
    result = await db.execute(
        select(Agent).where(Agent.id == client_agent_id).with_for_update()
    )
    client = result.scalar_one_or_none()

    if not client:
        raise ValueError("Client agent not found")

    if client.balance < amount:
        raise ValueError("Insufficient balance to fund escrow")

    client.balance -= amount
    client.escrow_balance += amount

    db.add(LedgerTransaction(
        job_id=job_id,
        agent_id=client_agent_id,
        counterparty_agent_id=None,
        amount=amount,
        currency=currency,
        transaction_type=LedgerTransactionType.ESCROW_LOCK,
        transaction_metadata=f'{{"job_id":"{job_id}"}}'
    ))

    if commit:
        await db.commit()


async def release_escrow(
    db: AsyncSession,
    client_agent_id: str,
    worker_agent_id: str,
    job_id: str,
    payout_amount: Decimal,
    escrow_total: Decimal,
    currency: str = "USDC",
    commit: bool = True
) -> None:
    """Release payout to worker and refund remainder to client."""
    result = await db.execute(
        select(Agent).where(Agent.id.in_([client_agent_id, worker_agent_id])).with_for_update()
    )
    agents = {agent.id: agent for agent in result.scalars().all()}
    client = agents.get(client_agent_id)
    worker = agents.get(worker_agent_id)

    if not client or not worker:
        raise ValueError("Client or worker agent not found")

    if client.escrow_balance < escrow_total:
        raise ValueError("Insufficient escrow balance to release")

    if payout_amount > escrow_total:
        payout_amount = escrow_total

    refund_amount = escrow_total - payout_amount

    client.escrow_balance -= escrow_total
    worker.balance += payout_amount
    if refund_amount > 0:
        client.balance += refund_amount

    db.add(LedgerTransaction(
        job_id=job_id,
        agent_id=client_agent_id,
        counterparty_agent_id=worker_agent_id,
        amount=payout_amount,
        currency=currency,
        transaction_type=LedgerTransactionType.ESCROW_RELEASE,
        transaction_metadata=f'{{"job_id":"{job_id}","refund":"{refund_amount}"}}'
    ))

    if refund_amount > 0:
        db.add(LedgerTransaction(
            job_id=job_id,
            agent_id=client_agent_id,
            counterparty_agent_id=None,
            amount=refund_amount,
            currency=currency,
            transaction_type=LedgerTransactionType.ESCROW_REFUND,
            transaction_metadata=f'{{"job_id":"{job_id}"}}'
        ))

    if commit:
        await db.commit()


async def refund_escrow(
    db: AsyncSession,
    client_agent_id: str,
    job_id: str,
    amount: Decimal,
    currency: str = "USDC",
    commit: bool = True
) -> None:
    """Refund escrowed funds back to client."""
    result = await db.execute(
        select(Agent).where(Agent.id == client_agent_id).with_for_update()
    )
    client = result.scalar_one_or_none()

    if not client:
        raise ValueError("Client agent not found")

    if client.escrow_balance < amount:
        raise ValueError("Insufficient escrow balance to refund")

    client.escrow_balance -= amount
    client.balance += amount

    db.add(LedgerTransaction(
        job_id=job_id,
        agent_id=client_agent_id,
        counterparty_agent_id=None,
        amount=amount,
        currency=currency,
        transaction_type=LedgerTransactionType.ESCROW_REFUND,
        transaction_metadata=f'{{"job_id":"{job_id}"}}'
    ))

    if commit:
        await db.commit()
