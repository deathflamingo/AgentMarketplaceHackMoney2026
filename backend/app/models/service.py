"""Service database model."""

from datetime import datetime
from decimal import Decimal
from typing import List
import uuid

from sqlalchemy import String, Text, Integer, Numeric, Boolean, ForeignKey, TIMESTAMP
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Service(Base):
    """Service model representing a fixed-price offering by an agent."""

    __tablename__ = "services"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Foreign Key
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Service Details
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Input/Output Specification
    required_inputs: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=list
    )  # List of input specifications
    output_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )  # text|code|image_url|json|file
    output_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Pricing & Capacity
    # Legacy USD pricing
    price_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    # AGNT pricing (new)
    min_price_agnt: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True
    )
    max_price_agnt: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True
    )
    allow_negotiation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )

    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5
    )

    # Requirements
    capabilities_required: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=list
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True
    )

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

    # Relationships
    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="services"
    )
    jobs: Mapped[List["Job"]] = relationship(
        "Job",
        back_populates="service",
        cascade="all, delete-orphan"
    )
    price_quotes: Mapped[List["PriceQuote"]] = relationship(
        "PriceQuote",
        back_populates="service",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Service(id={self.id}, name={self.name}, price=${self.price_usd})>"
