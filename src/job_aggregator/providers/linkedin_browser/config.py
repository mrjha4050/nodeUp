"""LinkedIn browser scraping settings.

Loaded from environment variables prefixed with LINKEDIN_BROWSER_.
Controls browser behavior, profile persistence, and timeouts.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LinkedInBrowserSettings(BaseSettings):
    """Configuration for the browser-based LinkedIn provider."""

    model_config = SettingsConfigDict(
        env_prefix="LINKEDIN_BROWSER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    profile_dir: str = Field(
        default=str(Path.home() / ".linkedin-mcp" / "profile"),
        description="Path to persistent browser profile (cookies/session)",
    )
    headless: bool = Field(
        default=True,
        description="Run browser in headless mode (False for login)",
    )
    navigation_timeout: int = Field(
        default=30000,
        ge=5000,
        le=120000,
        description="Page navigation timeout in milliseconds",
    )
    max_results_per_page: int = Field(
        default=25,
        ge=1,
        le=50,
        description="Max job results to scrape per search",
    )
    slow_mo: int = Field(
        default=100,
        ge=0,
        le=2000,
        description="Slow down browser actions by this many ms (anti-detection)",
    )
