"""Payment transaction model for tracking verified on-chain payments."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
import uuid

from sqlalchemy import String, Text, Numeric, TIMESTAMP, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TransactionStatus(str, Enum):
    """Payment transaction status enum."""
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    CREDITED = "credited"


class TransactionType(str, Enum):
    """Payment transaction type enum."""
    TOP_UP = "top_up"  # Agent depositing to platform
    P2P = "p2p"  # Peer-to-peer payment between agents
    REFUND = "refund"  # Refund transaction


class PaymentTransaction(Base):
    """Model for tracking all payment transactions."""

    __tablename__ = "payment_transactions"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Transaction Details
    tx_hash: Mapped[str] = mapped_column(
        String(66),  # 0x + 64 hex chars
        unique=True,
        nullable=False,
        index=True
    )

    # Amount and Currency
    amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USDC"
    )

    # Transaction Type
    transaction_type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType),
        nullable=False,
        default=TransactionType.TOP_UP
    )

    # Status
    status: Mapped[TransactionStatus] = mapped_column(
        SQLEnum(TransactionStatus),
        nullable=False,
        default=TransactionStatus.PENDING,
        index=True
    )

    # Agent References
    initiator_agent_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True
    )  # Agent who initiated the verification

    recipient_agent_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True
    )  # For P2P payments

    # Blockchain Details
    from_address: Mapped[str | None] = mapped_column(String(42), nullable=True)
    to_address: Mapped[str] = mapped_column(String(42), nullable=False)
    token_address: Mapped[str] = mapped_column(String(42), nullable=False)
    block_number: Mapped[int | None] = mapped_column(nullable=True)

    # Additional Info
    transaction_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string for additional info
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow,
        index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP,
        nullable=True
    )
    credited_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP,
        nullable=True
    )

    def __repr__(self) -> str:
        return f"<PaymentTransaction(id={self.id}, tx_hash={self.tx_hash[:10]}..., amount={self.amount}, status={self.status})>"
