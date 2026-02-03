"""Application configuration management using Pydantic Settings."""

from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str

    # API
    API_V1_PREFIX: str = "/api"

    # CORS
    CORS_ORIGINS: List[str] = ['http://localhost:3000']

    # Environment
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v) -> List[str]:
        """Parse CORS_ORIGINS from JSON string to list."""
        if isinstance(v, str):
            return json.loads(v)
        return v


# Global settings instance
settings = Settings()
