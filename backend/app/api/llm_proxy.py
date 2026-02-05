"""LLM proxy endpoint to forward requests and capture usage."""

from __future__ import annotations

import json
import logging
from typing import Dict, Iterable

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.services.llm_usage_store import record_usage


logger = logging.getLogger(__name__)
router = APIRouter()

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _filtered_headers(headers: Iterable[tuple[str, str]], drop: set[str]) -> Dict[str, str]:
    filtered: Dict[str, str] = {}
    for key, value in headers:
        lower = key.lower()
        if lower in drop:
            continue
        filtered[key] = value
    return filtered


@router.post("/forward")
async def forward_llm_request(request: Request) -> Response:
    headers = request.headers
    target_endpoint = headers.get("x-ai-endpoint")
    provider = headers.get("x-ai-provider")
    job_id = headers.get("x-job-id")

    missing = [name for name, value in [
        ("x-ai-endpoint", target_endpoint),
        ("x-ai-provider", provider),
        ("x-job-id", job_id),
    ] if not value]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required headers: {', '.join(missing)}",
        )

    body = await request.body()

    forward_headers = _filtered_headers(
        headers.items(),
        drop=_HOP_BY_HOP_HEADERS | {"host", "content-length", "x-ai-endpoint", "x-ai-provider", "x-job-id"},
    )

    try:
        async with httpx.AsyncClient() as client:
            upstream_response = await client.post(
                target_endpoint,
                content=body,
                headers=forward_headers,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream request failed: {exc}",
        ) from exc

    if upstream_response.status_code >= 400:
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=_filtered_headers(
                upstream_response.headers.items(),
                drop=_HOP_BY_HOP_HEADERS | {"content-length"},
            ),
        )

    usage_recorded = False
    try:
        payload = upstream_response.json()
        usage = payload.get("usage")
        if isinstance(usage, dict):
            record_usage(job_id=job_id, provider=provider, endpoint=target_endpoint, usage=usage)
            usage_recorded = True
        else:
            logger.warning("Usage not found in upstream response for job %s", job_id)
    except json.JSONDecodeError:
        logger.warning("Failed to decode upstream response for job %s", job_id)

    response_headers = _filtered_headers(
        upstream_response.headers.items(),
        drop=_HOP_BY_HOP_HEADERS | {"content-length"},
    )
    response_headers["x-usage-recorded"] = "true" if usage_recorded else "false"

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )
