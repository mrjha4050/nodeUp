"""Browser lifecycle manager using Patchright (stealth Playwright).

Manages a singleton Chromium instance with a persistent profile
so LinkedIn session cookies survive between runs. The browser is
shared across all tool calls and protected by an asyncio lock.
"""

import asyncio
from pathlib import Path

from patchright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from src.job_aggregator.core import get_logger
from src.job_aggregator.providers.linkedin_browser.config import LinkedInBrowserSettings
from src.job_aggregator.providers.linkedin_browser.exceptions import LinkedInAuthRequiredError

logger = get_logger(__name__)

# Auth barrier indicators in the page URL
_AUTH_WALL_PATTERNS = (
    "/login",
    "/checkpoint",
    "/authwall",
    "/uas/login",
)


class BrowserManager:
    """Singleton manager for a Patchright Chromium browser.

    Uses a persistent browser context so cookies and localStorage
    survive between server restarts.
    """

    def __init__(self, settings: LinkedInBrowserSettings) -> None:
        self._settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._lock = asyncio.Lock()
        self._authenticated = False

    @property
    def page(self) -> Page | None:
        return self._page

    async def ensure_ready(self) -> Page:
        """Return an authenticated page, launching the browser if needed."""
        async with self._lock:
            if self._page is None or self._page.is_closed():
                await self._launch()

            if not self._authenticated:
                self._authenticated = await self._check_auth()
                if not self._authenticated:
                    raise LinkedInAuthRequiredError()

            return self._page

    async def _launch(self) -> None:
        """Start Patchright and create a persistent browser context."""
        profile_path = Path(self._settings.profile_dir)
        profile_path.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=self._settings.headless,
            slow_mo=self._settings.slow_mo,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        # Reuse existing tab or open a new one
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()

        logger.info("browser_launched", headless=self._settings.headless)

    async def _check_auth(self) -> bool:
        """Navigate to LinkedIn feed and verify session is valid."""
        try:
            await self._page.goto(
                "https://www.linkedin.com/feed/",
                wait_until="domcontentloaded",
                timeout=self._settings.navigation_timeout,
            )
            current_url = self._page.url

            for pattern in _AUTH_WALL_PATTERNS:
                if pattern in current_url:
                    logger.warning("browser_auth_wall_detected", url=current_url)
                    return False

            logger.info("browser_session_valid")
            return True
        except Exception:
            logger.exception("browser_auth_check_failed")
            return False

    async def login_interactive(self) -> bool:
        """Open a headed browser for the user to log in manually.

        This is called via the --login CLI flag. It waits for the user
        to complete login (including 2FA) and then verifies the session.
        """
        # Force headed mode for login
        original_headless = self._settings.headless
        self._settings.headless = False

        try:
            await self.close()
            await self._launch()

            await self._page.goto(
                "https://www.linkedin.com/login",
                wait_until="domcontentloaded",
                timeout=self._settings.navigation_timeout,
            )

            logger.info("browser_login_waiting", message="Complete login in the browser window")
            print("\n" + "=" * 60)
            print("  LinkedIn Login Required")
            print("  Please log in to LinkedIn in the browser window.")
            print("  The server will continue once login is detected.")
            print("=" * 60 + "\n")

            # Poll until we land on the feed (login complete)
            for _ in range(120):  # 2 minutes max
                await asyncio.sleep(1)
                current_url = self._page.url
                if "/feed" in current_url or "/mynetwork" in current_url:
                    self._authenticated = True
                    logger.info("browser_login_success")
                    print("  Login successful!\n")
                    return True

            logger.warning("browser_login_timeout")
            print("  Login timed out. Please try again.\n")
            return False

        finally:
            self._settings.headless = original_headless

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

        self._authenticated = False
        logger.info("browser_closed")
