

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    """Core application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="job-aggregator-mcp")
    app_env: Environment = Field(default=Environment.DEVELOPMENT)
    log_level: str = Field(default="INFO")
    version: str = Field(default="0.1.0")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/job_aggregator",
        description="Async PostgreSQL connection string",
    )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings singleton."""
    return AppSettings()
