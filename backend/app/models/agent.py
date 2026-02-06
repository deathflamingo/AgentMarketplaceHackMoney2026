"""Agent database model."""

from datetime import datetime
from decimal import Decimal
from typing import List
import uuid

from sqlalchemy import String, Text, Integer, Numeric, TIMESTAMP
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Agent(Base):
    """Agent model representing an AI agent in the marketplace."""

    __tablename__ = "agents"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Basic Info
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    api_key_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    wallet_address: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Capabilities
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)

    # Reputation & Statistics
    reputation_score: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
        nullable=False,
        default=Decimal("0.00")
    )
    jobs_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_hired: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_earned: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00")
    )
    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00")
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0.00")
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="available",
        index=True
    )  # available|busy|offline

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow
    )

    # Relationships
    services: Mapped[List["Service"]] = relationship(
        "Service",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    jobs_as_client: Mapped[List["Job"]] = relationship(
        "Job",
        foreign_keys="Job.client_agent_id",
        back_populates="client"
    )
    jobs_as_worker: Mapped[List["Job"]] = relationship(
        "Job",
        foreign_keys="Job.worker_agent_id",
        back_populates="worker"
    )
    deposit_transactions: Mapped[List["DepositTransaction"]] = relationship(
        "DepositTransaction",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    withdrawal_transactions: Mapped[List["WithdrawalTransaction"]] = relationship(
        "WithdrawalTransaction",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    price_quotes: Mapped[List["PriceQuote"]] = relationship(
        "PriceQuote",
        foreign_keys="PriceQuote.client_agent_id",
        back_populates="client",
        cascade="all, delete-orphan"
    )
    balance_migrations: Mapped[List["BalanceMigration"]] = relationship(
        "BalanceMigration",
        back_populates="agent",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, name={self.name}, status={self.status})>"
