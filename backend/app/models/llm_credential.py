"""LLM provider credential model for BYOK access."""

from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy import String, TIMESTAMP, Enum as SQLEnum, Boolean, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMProviderCredential(Base):
    """Encrypted API key stored for an agent per provider."""

    __tablename__ = "llm_provider_credentials"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    provider: Mapped[LLMProvider] = mapped_column(
        SQLEnum(LLMProvider),
        nullable=False,
        index=True
    )

    encrypted_api_key: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP,
        nullable=True
    )

    def __repr__(self) -> str:
        return f"<LLMProviderCredential(id={self.id}, provider={self.provider}, agent_id={self.agent_id})>"
