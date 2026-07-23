"""IndeedBrowserProvider — browser-based JobProvider implementation.

Uses Patchright (stealth Playwright) to scrape Indeed pages directly.
No API keys required — Indeed job listings are publicly accessible.
"""

from src.job_aggregator.core import get_logger
from src.job_aggregator.models.job import Job
from src.job_aggregator.models.search import SearchRequest, ProviderResponse
from src.job_aggregator.providers.base import JobProvider
from src.job_aggregator.providers.indeed_browser.browser import IndeedBrowserManager
from src.job_aggregator.providers.indeed_browser.config import IndeedBrowserSettings
from src.job_aggregator.providers.indeed_browser.exceptions import IndeedBrowserError
from src.job_aggregator.providers.indeed_browser.parser import parse_job_card, parse_job_detail
from src.job_aggregator.providers.indeed_browser.scraper import IndeedScraper

logger = get_logger(__name__)


class IndeedBrowserProvider(JobProvider):
    """Concrete Indeed implementation using browser scraping."""

    def __init__(
        self,
        settings: IndeedBrowserSettings | None = None,
        browser_manager: IndeedBrowserManager | None = None,
    ) -> None:
        self._settings = settings or IndeedBrowserSettings()
        self._browser = browser_manager or IndeedBrowserManager(self._settings)

    @property
    def provider_name(self) -> str:
        return "indeed_browser"

    async def search_jobs(self, search_request: SearchRequest) -> ProviderResponse:
        """Scrape Indeed job search results.

        Navigates to the search page, extracts job cards, and parses
        them into domain Job models. Returns partial results if some
        cards fail to parse.
        """
        try:
            page = await self._browser.ensure_ready()
            scraper = IndeedScraper(
                page,
                self._settings.navigation_timeout,
                self._settings.country,
            )

            raw = await scraper.scrape_job_search(
                keywords=search_request.query,
                location=search_request.location,
                job_type=search_request.job_type.value if search_request.job_type else None,
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
                "indeed_browser_search_complete",
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

        except IndeedBrowserError as exc:
            logger.error(
                "indeed_browser_search_failed",
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
                "indeed_browser_search_unexpected_error",
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
        """Scrape a single job's detail page from Indeed."""
        try:
            page = await self._browser.ensure_ready()
            scraper = IndeedScraper(
                page,
                self._settings.navigation_timeout,
                self._settings.country,
            )

            raw = await scraper.scrape_job_details(job_id)
            job = parse_job_detail(raw, job_id)

            if job:
                logger.info("indeed_browser_job_detail_ok", job_id=job_id)
            else:
                logger.warning("indeed_browser_job_detail_parse_failed", job_id=job_id)

            return job

        except IndeedBrowserError as exc:
            logger.error(
                "indeed_browser_job_detail_failed",
                job_id=job_id,
                error=str(exc),
            )
            return None
        except Exception:
            logger.exception("indeed_browser_job_detail_unexpected_error", job_id=job_id)
            return None

    async def health_check(self) -> bool:
        """Check if Indeed is reachable via browser."""
        try:
            page = await self._browser.ensure_ready()
            scraper = IndeedScraper(
                page,
                self._settings.navigation_timeout,
                self._settings.country,
            )
            return await scraper.check_connectivity()
        except Exception:
            logger.exception("indeed_browser_health_check_failed")
            return False

    async def close(self) -> None:
        """Shut down the browser and release resources."""
        await self._browser.close()
