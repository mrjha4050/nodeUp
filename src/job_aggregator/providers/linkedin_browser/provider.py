"""LinkedInBrowserProvider — browser-based JobProvider implementation.

Uses Patchright (stealth Playwright) to scrape LinkedIn pages directly.
This provider implements the same JobProvider ABC as the API-based one,
so it plugs into the existing registry and aggregator seamlessly.

No LinkedIn API keys required — uses real browser session cookies.
"""

from src.job_aggregator.core import get_logger
from src.job_aggregator.models.job import Job
from src.job_aggregator.models.search import SearchRequest, ProviderResponse
from src.job_aggregator.providers.base import JobProvider
from src.job_aggregator.providers.linkedin_browser.browser import BrowserManager
from src.job_aggregator.providers.linkedin_browser.config import LinkedInBrowserSettings
from src.job_aggregator.providers.linkedin_browser.exceptions import LinkedInBrowserError
from src.job_aggregator.providers.linkedin_browser.parser import parse_job_card, parse_job_detail
from src.job_aggregator.providers.linkedin_browser.scraper import LinkedInScraper

logger = get_logger(__name__)


class LinkedInBrowserProvider(JobProvider):
    """Concrete LinkedIn implementation using browser scraping."""

    def __init__(
        self,
        settings: LinkedInBrowserSettings | None = None,
        browser_manager: BrowserManager | None = None,
    ) -> None:
        self._settings = settings or LinkedInBrowserSettings()
        self._browser = browser_manager or BrowserManager(self._settings)

    @property
    def provider_name(self) -> str:
        return "linkedin_browser"

    @property
    def browser_manager(self) -> BrowserManager:
        """Expose browser manager for login flow and shutdown."""
        return self._browser

    async def search_jobs(self, search_request: SearchRequest) -> ProviderResponse:
        """Scrape LinkedIn job search results.

        Navigates to the search page, extracts job cards, and parses
        them into domain Job models. Returns partial results if some
        cards fail to parse.
        """
        try:
            page = await self._browser.ensure_ready()
            scraper = LinkedInScraper(page, self._settings.navigation_timeout)

            raw = await scraper.scrape_job_search(
                keywords=search_request.query,
                location=search_request.location,
                job_type=search_request.job_type.value if search_request.job_type else None,
                experience_level=(
                    search_request.experience_level.value
                    if search_request.experience_level
                    else None
                ),
                start=search_request.offset or 0,
                count=search_request.limited_results or self._settings.max_results_per_page,
            )

            jobs: list[Job] = []
            for card in raw.get("job_cards", []):
                job = parse_job_card(card)
                if job is not None:
                    jobs.append(job)

            jobs = self.apply_filters(jobs, search_request)

            logger.info(
                "linkedin_browser_search_complete",
                query=search_request.query,
                cards_scraped=len(raw.get("job_cards", [])),
                jobs_parsed=len(jobs),
            )

            return ProviderResponse(
                provider_name=self.provider_name,
                jobs=jobs,
                total_results=len(jobs),
                success=True,
            )

        except LinkedInBrowserError as exc:
            logger.error(
                "linkedin_browser_search_failed",
                query=search_request.query,
                error=str(exc),
                status_code=exc.status_code,
            )
            return ProviderResponse(
                provider_name=self.provider_name,
                jobs=[],
                total_results=0,
                success=False,
                error_message=str(exc),
            )
        except Exception as exc:
            logger.exception(
                "linkedin_browser_search_unexpected_error",
                query=search_request.query,
            )
            return ProviderResponse(
                provider_name=self.provider_name,
                jobs=[],
                total_results=0,
                success=False,
                error_message=f"Unexpected error: {exc}",
            )

    async def get_job_details(self, job_id: str) -> Job | None:
        """Scrape a single job's detail page from LinkedIn."""
        try:
            page = await self._browser.ensure_ready()
            scraper = LinkedInScraper(page, self._settings.navigation_timeout)

            raw = await scraper.scrape_job_details(job_id)
            job = parse_job_detail(raw, job_id)

            if job:
                logger.info("linkedin_browser_job_detail_ok", job_id=job_id)
            else:
                logger.warning("linkedin_browser_job_detail_parse_failed", job_id=job_id)

            return job

        except LinkedInBrowserError as exc:
            logger.error(
                "linkedin_browser_job_detail_failed",
                job_id=job_id,
                error=str(exc),
            )
            return None
        except Exception:
            logger.exception("linkedin_browser_job_detail_unexpected_error", job_id=job_id)
            return None

    async def health_check(self) -> bool:
        """Check if the browser is running and authenticated."""
        try:
            page = await self._browser.ensure_ready()
            scraper = LinkedInScraper(page, self._settings.navigation_timeout)
            return await scraper.check_connectivity()
        except Exception:
            logger.exception("linkedin_browser_health_check_failed")
            return False

    async def close(self) -> None:
        """Shut down the browser and release resources."""
        await self._browser.close()
