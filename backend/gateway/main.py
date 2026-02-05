"""LLM Gateway service for metered model access."""

import time
from decimal import Decimal
from typing import Any

import httpx
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.api.deps import get_current_agent
from app.models.agent import Agent
from app.models.job import Job
from app.models.llm_credential import LLMProvider
from app.schemas.llm import LLMChatRequest, LLMChatResponse
from app.services.llm_credential_service import get_decrypted_api_key
from app.services.llm_usage_service import record_usage_event, get_usage_summary
from app.services.job_service import update_job_usage_totals


app = FastAPI(
    title="AgentMarket LLM Gateway",
    version="1.0.0",
    description="Metered LLM access for AgentMarket jobs"
)


def _extract_message_text(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
        else:
            parts.append(str(content))
    return " ".join(parts)


def _estimate_prompt_tokens(messages: list[dict[str, Any]]) -> int:
    # Rough heuristic: 1 token ~ 4 chars
    text = _extract_message_text(messages)
    return max(1, int(len(text) / 4))


async def _call_openai(api_key: str, payload: dict) -> tuple[str, dict, str | None]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=resp.text)
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {}) or {}
        request_id = data.get("id") or resp.headers.get("x-request-id")
        return content, usage, request_id


async def _call_anthropic(api_key: str, payload: dict) -> tuple[str, dict, str | None]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=resp.text)
        data = resp.json()
        blocks = data.get("content", [])
        content = "".join([b.get("text", "") for b in blocks if isinstance(b, dict)])
        usage = data.get("usage", {}) or {}
        request_id = data.get("id") or resp.headers.get("request-id")
        return content, usage, request_id


@app.post("/v1/llm/chat", response_model=LLMChatResponse)
async def chat(
    payload: LLMChatRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    # Load job and verify access
    result = await db.execute(select(Job).where(Job.id == payload.job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if str(job.worker_agent_id) != str(current_agent.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not job worker")

    if job.status not in ["in_progress", "revision_requested"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job not in progress")

    if job.escrow_status != "funded":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job escrow not funded")

    if job.price_per_1k_tokens_usd <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job pricing not configured")

    provider = LLMProvider(payload.provider)
    api_key = await get_decrypted_api_key(db, agent_id=str(current_agent.id), provider=provider)

    # Budget enforcement
    usage_summary = await get_usage_summary(db, str(job.id))
    spent = usage_summary["cost_usd"]
    remaining = job.client_max_budget_usd - spent

    if remaining <= 0:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Job budget exhausted")

    est_prompt_tokens = _estimate_prompt_tokens(payload.messages)
    rate = job.price_per_1k_tokens_usd
    max_tokens_allowed = int((Decimal(remaining) * Decimal(1000) / rate) - Decimal(est_prompt_tokens))

    if max_tokens_allowed <= 0:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Job budget too low for request")

    max_tokens = min(payload.max_tokens, max_tokens_allowed)

    start = time.time()
    try:
        if provider == LLMProvider.OPENAI:
            content, usage, request_id = await _call_openai(
                api_key,
                {
                    "model": payload.model,
                    "messages": payload.messages,
                    "max_tokens": max_tokens,
                    "temperature": payload.temperature,
                }
            )
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
            total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
        elif provider == LLMProvider.ANTHROPIC:
            content, usage, request_id = await _call_anthropic(
                api_key,
                {
                    "model": payload.model,
                    "messages": payload.messages,
                    "max_tokens": max_tokens,
                    "temperature": payload.temperature,
                }
            )
            prompt_tokens = int(usage.get("input_tokens", 0))
            completion_tokens = int(usage.get("output_tokens", 0))
            total_tokens = prompt_tokens + completion_tokens
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported provider")

        cost = (Decimal(total_tokens) * rate) / Decimal(1000)

        await record_usage_event(
            db,
            job_id=str(job.id),
            worker_agent_id=str(current_agent.id),
            provider=provider.value,
            model=payload.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            status="success",
            provider_request_id=request_id,
            latency_ms=int((time.time() - start) * 1000),
        )

        await update_job_usage_totals(db, str(job.id))

        return LLMChatResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=str(cost),
        )

    except HTTPException:
        raise
    except Exception as e:
        await record_usage_event(
            db,
            job_id=str(job.id),
            worker_agent_id=str(current_agent.id),
            provider=provider.value,
            model=payload.model,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=Decimal("0.0"),
            status="error",
            error_message=str(e),
            latency_ms=int((time.time() - start) * 1000),
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="LLM call failed")
