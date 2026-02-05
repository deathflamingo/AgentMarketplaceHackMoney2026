"""LLM usage event model for metering."""

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import String, Integer, Numeric, TIMESTAMP, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.llm_credential import LLMProvider


class LLMUsageEvent(Base):
    """Per-request usage event for a job."""

    __tablename__ = "llm_usage_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    worker_agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    provider: Mapped[LLMProvider] = mapped_column(
        SQLEnum(LLMProvider),
        nullable=False,
        index=True
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0.0000"))

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow,
        index=True
    )

    def __repr__(self) -> str:
        return f"<LLMUsageEvent(id={self.id}, job_id={self.job_id}, tokens={self.total_tokens})>"
