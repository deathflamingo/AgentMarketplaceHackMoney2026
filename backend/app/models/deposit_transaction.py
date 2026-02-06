"""Deposit transaction database model."""

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import String, Numeric, ForeignKey, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DepositTransaction(Base):
    """Deposit transaction model for tracking USDC→AGNT swaps."""

    __tablename__ = "deposit_transactions"

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

    # Transaction Details
    swap_tx_hash: Mapped[str] = mapped_column(
        String(66),
        unique=True,
        nullable=False,
        index=True
    )  # Unique transaction hash prevents replay attacks

    # Amounts
    usdc_amount_in: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # USDC amount swapped
    agnt_amount_out: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # AGNT amount received
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # Actual rate at time of swap (AGNT per USDC)

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True
    )  # pending|verified|failed

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP,
        nullable=True
    )

    # Relationships
    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="deposit_transactions"
    )

    def __repr__(self) -> str:
        return f"<DepositTransaction(id={self.id}, agent_id={self.agent_id}, status={self.status})>"
