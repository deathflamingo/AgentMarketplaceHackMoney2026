"""Message database model."""

from datetime import datetime
import uuid

from sqlalchemy import String, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Message(Base):
    """Message model representing communications between agents."""

    __tablename__ = "messages"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Foreign Keys
    from_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False
    )
    to_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Message Details
    message_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )  # job_created|job_started|work_delivered|revision_requested|job_completed|rating_received
    content: Mapped[dict] = mapped_column(
        JSON,
        nullable=False
    )

    # Read Status
    read_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP,
        nullable=True,
        index=True
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow
    )

    # Relationships
    from_agent: Mapped["Agent"] = relationship(
        "Agent",
        foreign_keys=[from_agent_id]
    )
    to_agent: Mapped["Agent"] = relationship(
        "Agent",
        foreign_keys=[to_agent_id]
    )
    job: Mapped["Job"] = relationship(
        "Job",
        back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, type={self.message_type}, from={self.from_agent_id}, to={self.to_agent_id})>"
