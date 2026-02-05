"""Internal ledger transactions for escrow movements."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
import uuid

from sqlalchemy import String, Numeric, TIMESTAMP, Enum as SQLEnum, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LedgerTransactionType(str, Enum):
    """Internal ledger transaction types."""
    ESCROW_LOCK = "escrow_lock"
    ESCROW_RELEASE = "escrow_release"
    ESCROW_REFUND = "escrow_refund"


class LedgerTransaction(Base):
    """Internal ledger transaction record."""

    __tablename__ = "ledger_transactions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    job_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True
    )

    agent_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True
    )

    counterparty_agent_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USDC"
    )

    transaction_type: Mapped[LedgerTransactionType] = mapped_column(
        SQLEnum(LedgerTransactionType),
        nullable=False,
        index=True
    )

    transaction_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow,
        index=True
    )

    def __repr__(self) -> str:
        return f"<LedgerTransaction(id={self.id}, type={self.transaction_type}, amount={self.amount})>"
