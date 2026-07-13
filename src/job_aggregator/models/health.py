"""Health check response models."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    """Response model for the health check tool."""

    status: str = Field(description="Server status")
    server_name: str = Field(description="Name of the MCP server")
    version: str = Field(description="Server version")
    environment: str = Field(description="Current environment")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    providers: dict[str, str] = Field(
        default_factory=dict,
        description="Registered provider statuses",
    )
