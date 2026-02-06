"""Job database model."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import uuid

from sqlalchemy import String, Text, Integer, Numeric, ForeignKey, TIMESTAMP
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Job(Base):
    """Job model representing a hired service instance."""

    __tablename__ = "jobs"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Foreign Keys
    service_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False
    )
    client_agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    worker_agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Parent-Child Relationship for Task Decomposition
    parent_job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Job Details
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    input_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False
    )  # The actual inputs for this job

    # Pricing (AGNT)
    price_agnt: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # Final price locked at purchase time (in AGNT)

    # Legacy USD pricing (for backward compatibility with database)
    price_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )

    # Negotiation tracking
    initial_price_offer: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True
    )  # First price offered
    final_price_agreed: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # Final agreed price (same as price_agnt)
    negotiated_by: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )  # "agent" | "llm" | "p2p"
    quote_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True
    )  # Reference to LLM price quote (if used)
    negotiation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("negotiations.id"),
        nullable=True,
        index=True
    )  # Reference to P2P negotiation (if used)

    # Status & State
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True
    )  # pending|in_progress|delivered|completed|cancelled|failed|revision_requested

    # Review
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    review: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)

    # Relationships
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="jobs"
    )
    client: Mapped["Agent"] = relationship(
        "Agent",
        foreign_keys=[client_agent_id],
        back_populates="jobs_as_client"
    )
    worker: Mapped["Agent"] = relationship(
        "Agent",
        foreign_keys=[worker_agent_id],
        back_populates="jobs_as_worker"
    )

    # Self-referential relationship for task decomposition
    parent_job: Mapped[Optional["Job"]] = relationship(
        "Job",
        remote_side=[id],
        foreign_keys=[parent_job_id],
        back_populates="sub_jobs"
    )
    sub_jobs: Mapped[List["Job"]] = relationship(
        "Job",
        back_populates="parent_job",
        cascade="all, delete-orphan"
    )

    deliverables: Mapped[List["Deliverable"]] = relationship(
        "Deliverable",
        back_populates="job",
        cascade="all, delete-orphan"
    )
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="job",
        cascade="all, delete-orphan"
    )
    negotiation: Mapped[Optional["Negotiation"]] = relationship(
        "Negotiation",
        foreign_keys=[negotiation_id]
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title={self.title}, status={self.status})>"
