"""Deliverable database model."""

from datetime import datetime
import uuid

from sqlalchemy import String, Text, Integer, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Deliverable(Base):
    """Deliverable model representing work artifacts submitted by workers."""

    __tablename__ = "deliverables"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Foreign Key
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Deliverable Details
    artifact_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )  # text|code|image_url|json|file
    content: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_metadata: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True
    )  # e.g., {"language": "python", "lines": 150}

    # Versioning (increments on revision)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow
    )

    # Relationships
    job: Mapped["Job"] = relationship(
        "Job",
        back_populates="deliverables"
    )

    def __repr__(self) -> str:
        return f"<Deliverable(id={self.id}, job_id={self.job_id}, type={self.artifact_type}, v={self.version})>"
