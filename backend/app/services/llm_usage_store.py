"""In-memory usage store for LLM proxy requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List


@dataclass(frozen=True)
class LLMUsageRecord:
    job_id: str
    provider: str
    endpoint: str
    usage: Dict[str, Any]
    recorded_at: str


_lock = Lock()
_records: Dict[str, List[LLMUsageRecord]] = {}


def record_usage(job_id: str, provider: str, endpoint: str, usage: Dict[str, Any]) -> None:
    """Store usage for a job in memory."""
    record = LLMUsageRecord(
        job_id=job_id,
        provider=provider,
        endpoint=endpoint,
        usage=usage,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    with _lock:
        _records.setdefault(job_id, []).append(record)


def get_usage(job_id: str) -> List[LLMUsageRecord]:
    """Retrieve usage records for a job."""
    with _lock:
        return list(_records.get(job_id, []))
