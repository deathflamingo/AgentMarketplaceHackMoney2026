"""
Negotiation models for peer-to-peer price negotiation between agents.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List

from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, TIMESTAMP, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Negotiation(Base):
    """P2P negotiation between client and worker agents."""

    __tablename__ = "negotiations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Participants
    service_id: Mapped[str] = mapped_column(String(36), ForeignKey("services.id"))
    client_agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"))
    worker_agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"))

    # Job context
    job_description: Mapped[str] = mapped_column(Text)

    # Current state
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active | agreed | rejected | expired

    current_price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    # The last proposed price

    current_proposer: Mapped[str] = mapped_column(String(10))
    # "client" | "worker" - who made the last proposal

    # Constraints
    service_min_price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    service_max_price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    client_max_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    # Tracking
    round_count: Mapped[int] = mapped_column(Integer, default=0)
    max_rounds: Mapped[int] = mapped_column(Integer, default=5)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP)
    agreed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)

    # Relationships
    offers: Mapped[List["NegotiationOffer"]] = relationship(
        "NegotiationOffer",
        back_populates="negotiation",
        order_by="NegotiationOffer.created_at"
    )
    service: Mapped["Service"] = relationship("Service")
    client_agent: Mapped["Agent"] = relationship("Agent", foreign_keys=[client_agent_id])
    worker_agent: Mapped["Agent"] = relationship("Agent", foreign_keys=[worker_agent_id])


class NegotiationOffer(Base):
    """Individual offers in a negotiation."""

    __tablename__ = "negotiation_offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    negotiation_id: Mapped[str] = mapped_column(String(36), ForeignKey("negotiations.id"))

    # Offer details
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"))
    agent_role: Mapped[str] = mapped_column(String(10))  # "client" | "worker"

    action: Mapped[str] = mapped_column(String(20))
    # "offer" | "counter" | "accept" | "reject"

    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)

    # Relationships
    negotiation: Mapped["Negotiation"] = relationship("Negotiation", back_populates="offers")
    agent: Mapped["Agent"] = relationship("Agent")
