"""Activity log database model."""

from datetime import datetime
import uuid

from sqlalchemy import String, Integer, ForeignKey, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActivityLog(Base):
    """Activity log model for tracking all platform events."""

    __tablename__ = "activity_log"

    # Primary Key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    # Event Details
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )

    # Foreign Keys (nullable for system events)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="SET NULL"),
        nullable=True
    )

    # Event Data
    data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow,
        index=True
    )

    # Additional indexes for performance
    __table_args__ = (
        Index('idx_activity_created', 'created_at'),
        Index('idx_activity_type', 'event_type'),
    )

    def __repr__(self) -> str:
        return f"<ActivityLog(id={self.id}, type={self.event_type}, created_at={self.created_at})>"
