"""Browser lifecycle manager for Indeed scraping.

Unlike LinkedIn, Indeed doesn't require login — job listings are public.
We still use Patchright (stealth Playwright) to avoid bot detection.
A fresh context is created per session (no persistent profile needed).
"""

import asyncio

from patchright.async_api import async_playwright, BrowserContext, Page, Playwright

from src.job_aggregator.core import get_logger
from src.job_aggregator.providers.indeed_browser.config import IndeedBrowserSettings

logger = get_logger(__name__)


class IndeedBrowserManager:
    """Manages a Patchright Chromium browser for Indeed scraping.

    No persistent profile needed since Indeed is publicly accessible.
    """

    def __init__(self, settings: IndeedBrowserSettings) -> None:
        self._settings = settings
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._lock = asyncio.Lock()

    async def ensure_ready(self) -> Page:
        """Return a ready page, launching the browser if needed."""
        async with self._lock:
            if self._page is None or self._page.is_closed():
                await self._launch()
            return self._page

    async def _launch(self) -> None:
        """Start Patchright and create a browser context."""
        self._playwright = await async_playwright().start()

        browser = await self._playwright.chromium.launch(
            headless=self._settings.headless,
            slow_mo=self._settings.slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        self._context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()

        logger.info("indeed_browser_launched", headless=self._settings.headless)

    async def close(self) -> None:
        """Shut down the browser and release all resources."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        logger.info("indeed_browser_closed")
