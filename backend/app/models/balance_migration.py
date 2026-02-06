"""Balance migration database model."""

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import String, Numeric, ForeignKey, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BalanceMigration(Base):
    """Balance migration model for tracking USDC→AGNT conversion."""

    __tablename__ = "balance_migrations"

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

    # Old Balance (USDC)
    old_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )
    old_currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USDC"
    )
    old_total_earned: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )
    old_total_spent: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )

    # New Balance (AGNT)
    new_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )
    new_currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="AGNT"
    )
    new_total_earned: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )
    new_total_spent: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )

    # Conversion
    conversion_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False
    )  # AGNT per USDC (e.g., 10000)

    # Timestamp
    migrated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow
    )

    # Migration Metadata
    migration_batch: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )  # Group migrations by batch ID

    # Relationships
    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="balance_migrations"
    )

    def __repr__(self) -> str:
        return f"<BalanceMigration(id={self.id}, agent_id={self.agent_id}, {self.old_currency}→{self.new_currency})>"
