"""Withdrawal transaction database model."""

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import String, Numeric, ForeignKey, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WithdrawalTransaction(Base):
    """Withdrawal transaction model for tracking AGNT→USDC conversions."""

    __tablename__ = "withdrawal_transactions"

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

    # Amounts
    agnt_amount_in: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # AGNT amount to withdraw (before fees)
    usdc_amount_out: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # USDC amount sent to agent
    fee_agnt: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # Fee charged in AGNT
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # Actual rate at time of swap (USDC per AGNT)

    # Recipient
    recipient_address: Mapped[str] = mapped_column(
        String(42),
        nullable=False
    )  # Wallet address to receive USDC

    # Transaction Hashes
    swap_tx_hash: Mapped[str | None] = mapped_column(
        String(66),
        nullable=True
    )  # Hash of Uniswap swap transaction
    transfer_tx_hash: Mapped[str | None] = mapped_column(
        String(66),
        nullable=True
    )  # Hash of USDC transfer to recipient

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True
    )  # pending|processing|completed|failed|refunded

    # Error Tracking
    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP,
        nullable=True
    )

    # Relationships
    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="withdrawal_transactions"
    )

    def __repr__(self) -> str:
        return f"<WithdrawalTransaction(id={self.id}, agent_id={self.agent_id}, status={self.status})>"
