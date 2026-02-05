"""LLM usage metering and aggregation."""

from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.llm_usage_event import LLMUsageEvent
from app.models.llm_credential import LLMProvider


async def record_usage_event(
    db: AsyncSession,
    *,
    job_id: str,
    worker_agent_id: str,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost_usd: Decimal,
    status: str = "success",
    provider_request_id: str | None = None,
    latency_ms: int | None = None,
    error_message: str | None = None
) -> LLMUsageEvent:
    """Record a single usage event."""
    event = LLMUsageEvent(
        job_id=job_id,
        worker_agent_id=worker_agent_id,
        provider=LLMProvider(provider),
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        status=status,
        provider_request_id=provider_request_id,
        latency_ms=latency_ms,
        error_message=error_message
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def get_usage_summary(
    db: AsyncSession,
    job_id: str
) -> dict:
    """Aggregate usage totals for a job."""
    result = await db.execute(
        select(
            func.coalesce(func.sum(LLMUsageEvent.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LLMUsageEvent.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(LLMUsageEvent.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(LLMUsageEvent.cost_usd), 0).label("cost_usd"),
        ).where(LLMUsageEvent.job_id == job_id)
    )
    row = result.one()
    return {
        "prompt_tokens": int(row.prompt_tokens or 0),
        "completion_tokens": int(row.completion_tokens or 0),
        "total_tokens": int(row.total_tokens or 0),
        "cost_usd": Decimal(row.cost_usd or 0),
    }
