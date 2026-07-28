"""Indeed browser scraping settings.

Loaded from environment variables prefixed with INDEED_BROWSER_.
Controls browser behavior and timeouts.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IndeedBrowserSettings(BaseSettings):
    """Configuration for the browser-based Indeed provider."""

    model_config = SettingsConfigDict(
        env_prefix="INDEED_BROWSER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    headless: bool = Field(
        default=True,
        description="Run browser in headless mode",
    )
    navigation_timeout: int = Field(
        default=30000,
        ge=5000,
        le=120000,
        description="Page navigation timeout in milliseconds",
    )
    max_results_per_page: int = Field(
        default=15,
        ge=1,
        le=50,
        description="Max job results to scrape per search",
    )
    slow_mo: int = Field(
        default=150,
        ge=0,
        le=2000,
        description="Slow down browser actions by this many ms (anti-detection)",
    )
    country: str = Field(
        default="",
        description="Country domain suffix (e.g., 'co.uk' for indeed.co.uk). Empty = indeed.com",
    )
