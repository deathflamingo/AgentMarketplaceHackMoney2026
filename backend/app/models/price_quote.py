"""Price quote database model."""

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import String, Text, Numeric, ForeignKey, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PriceQuote(Base):
    """Price quote model for LLM-negotiated service pricing."""

    __tablename__ = "price_quotes"

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
        nullable=False,
        index=True
    )
    client_agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Job Details (for negotiation context)
    job_description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    # Price Information
    max_price_willing: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # Client's maximum budget in AGNT
    quoted_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # LLM-negotiated price in AGNT

    # Negotiation Metadata
    service_min_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # Service min at time of quote
    service_max_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # Service max at time of quote
    negotiation_factors: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )  # JSON string of factors considered (complexity, reputation, etc.)

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True
    )  # pending|accepted|expired|rejected

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow
    )
    valid_until: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False
    )  # Quote expiration time
    accepted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP,
        nullable=True
    )

    # Relationships
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="price_quotes"
    )
    client: Mapped["Agent"] = relationship(
        "Agent",
        foreign_keys=[client_agent_id],
        back_populates="price_quotes"
    )

    def __repr__(self) -> str:
        return f"<PriceQuote(id={self.id}, service_id={self.service_id}, quoted_price={self.quoted_price})>"
