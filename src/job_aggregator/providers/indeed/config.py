"""Indeed-specific settings.

Loaded from environment variables prefixed with INDEED_.
Isolated to this module — nothing outside the indeed package
needs to know about these.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IndeedSettings(BaseSettings):
    """Indeed API configuration."""

    model_config = SettingsConfigDict(
        env_prefix="INDEED_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = Field(default="", description="Indeed API key")
    base_url: str = Field(
        default="https://apis.indeed.com/graphql",
        description="Indeed API base URL",
    )
    publisher_id: str = Field(default="", description="Indeed publisher ID")
    timeout: int = Field(default=30, ge=5, le=120, description="HTTP request timeout in seconds")
    max_results_per_page: int = Field(default=25, ge=1, le=50, description="Max results per API call")
    country: str = Field(default="us", description="Default country code for job searches")
