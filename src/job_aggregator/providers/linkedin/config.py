"""LinkedIn-specific settings.

Loaded from environment variables prefixed with LINKEDIN_.
These stay inside the linkedin module — no other part of
the application needs to know about them.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LinkedInSettings(BaseSettings):
    """LinkedIn API configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LINKEDIN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    client_id: str = Field(default="", description="LinkedIn OAuth2 client ID")
    client_secret: str = Field(default="", description="LinkedIn OAuth2 client secret")
    base_url: str = Field(
        default="https://api.linkedin.com/v2",
        description="LinkedIn API base URL",
    )
    timeout: int = Field(default=30, ge=5, le=120, description="HTTP request timeout in seconds")
    max_results_per_page: int = Field(default=25, ge=1, le=50, description="Max results per API call")
