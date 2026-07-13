"""LinkedIn page scraper using innerText extraction.

Navigates to LinkedIn pages and extracts visible text content.
Uses innerText instead of DOM selectors for resilience against
LinkedIn's frequent layout changes.
"""

import re
from urllib.parse import quote_plus

from patchright.async_api import Page

from src.job_aggregator.core import get_logger
from src.job_aggregator.providers.linkedin_browser.exceptions import LinkedInPageLoadError

logger = get_logger(__name__)

# LinkedIn UI noise patterns to strip from extracted text
_NOISE_PATTERNS = [
    r"Skip to main content.*?\n",
    r"LinkedIn.*?Navigation\n",
    r"Messaging\n",
    r"Notifications\n",
    r"Try Premium.*?\n",
    r"Show more\n",
    r"Show fewer\n",
    r"People also viewed.*",
    r"Similar jobs.*",
    r"About the company\n",
]

_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE | re.DOTALL)


def _clean_text(text: str) -> str:
    """Strip LinkedIn UI chrome from extracted text."""
    text = _NOISE_RE.sub("", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class LinkedInScraper:
    """Scrapes LinkedIn pages by extracting visible text."""

    def __init__(self, page: Page, navigation_timeout: int = 30000) -> None:
        self._page = page
        self._timeout = navigation_timeout

    async def scrape_job_search(
        self,
        keywords: str,
        location: str | None = None,
        job_type: str | None = None,
        experience_level: str | None = None,
        start: int = 0,
        count: int = 25,
    ) -> dict:
        """Scrape LinkedIn job search results page.

        Returns a dict with:
            - url: the scraped URL
            - text: cleaned visible text of the results
            - job_cards: list of dicts with per-card text chunks
        """
        url = self._build_search_url(keywords, location, job_type, experience_level, start)

        logger.info("scraper_navigating", url=url)
        await self._navigate(url)

        # Wait for job cards to render
        try:
            await self._page.wait_for_selector(
                ".jobs-search-results-list, .jobs-search__results-list, main",
                timeout=10000,
            )
        except Exception:
            logger.warning("scraper_job_list_selector_timeout", url=url)

        # Scroll to load more results
        await self._scroll_page(scroll_count=3)

        # Extract main content text
        main_text = await self._extract_main_text()

        # Try to extract individual job card texts
        job_cards = await self._extract_job_cards(count)

        logger.info(
            "scraper_search_complete",
            keywords=keywords,
            cards_found=len(job_cards),
        )

        return {
            "url": url,
            "text": _clean_text(main_text),
            "job_cards": job_cards,
        }

    async def scrape_job_details(self, job_id: str) -> dict:
        """Scrape a single job posting's detail page.

        Returns a dict with:
            - url: the scraped URL
            - text: cleaned visible text of the job posting
        """
        clean_id = job_id.removeprefix("linkedin_browser_")
        url = f"https://www.linkedin.com/jobs/view/{clean_id}/"

        logger.info("scraper_job_detail_navigating", url=url)
        await self._navigate(url)

        # Wait for the job detail pane to load
        try:
            await self._page.wait_for_selector(
                ".jobs-description, .job-view-layout, main",
                timeout=10000,
            )
        except Exception:
            logger.warning("scraper_job_detail_selector_timeout", url=url)

        text = await self._extract_main_text()

        logger.info("scraper_job_detail_complete", job_id=job_id)

        return {
            "url": url,
            "text": _clean_text(text),
        }

    async def check_connectivity(self) -> bool:
        """Verify we can reach LinkedIn without hitting an auth wall."""
        try:
            await self._navigate("https://www.linkedin.com/feed/")
            current_url = self._page.url
            return "/feed" in current_url
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _navigate(self, url: str) -> None:
        """Navigate to a URL and verify the page loaded."""
        try:
            response = await self._page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self._timeout,
            )
            if response and response.status >= 400:
                raise LinkedInPageLoadError(url, f"HTTP {response.status}")
        except LinkedInPageLoadError:
            raise
        except Exception as exc:
            raise LinkedInPageLoadError(url, str(exc)) from exc

    async def _extract_main_text(self) -> str:
        """Extract visible text from the page's main content area."""
        text = await self._page.evaluate(
            "() => (document.querySelector('main') || document.body).innerText || ''"
        )
        return text

    async def _extract_job_cards(self, max_cards: int) -> list[dict]:
        """Extract text from individual job card elements.

        Tries multiple selectors since LinkedIn changes class names.
        Falls back to splitting main text if no cards found.
        """
        card_selectors = [
            ".jobs-search-results__list-item",
            ".job-card-container",
            ".jobs-search__results-list > li",
            "ul.scaffold-layout__list-container > li",
        ]

        for selector in card_selectors:
            cards = await self._page.query_selector_all(selector)
            if cards:
                results = []
                for card in cards[:max_cards]:
                    try:
                        text = await card.inner_text()
                        # Try to extract the job link for the ID
                        link = await card.query_selector("a[href*='/jobs/view/']")
                        href = await link.get_attribute("href") if link else None
                        job_id = self._extract_job_id_from_href(href) if href else None

                        results.append({
                            "text": text.strip(),
                            "job_id": job_id,
                            "href": href,
                        })
                    except Exception:
                        continue
                if results:
                    return results

        logger.info("scraper_no_card_selectors_matched")
        return []

    async def _scroll_page(self, scroll_count: int = 3) -> None:
        """Scroll the page to trigger lazy-loaded content."""
        for i in range(scroll_count):
            await self._page.evaluate(f"window.scrollBy(0, {400 * (i + 1)})")
            await self._page.wait_for_timeout(500)

    @staticmethod
    def _build_search_url(
        keywords: str,
        location: str | None = None,
        job_type: str | None = None,
        experience_level: str | None = None,
        start: int = 0,
    ) -> str:
        """Build a LinkedIn job search URL with query parameters."""
        base = "https://www.linkedin.com/jobs/search/?"
        params = [f"keywords={quote_plus(keywords)}"]

        if location:
            params.append(f"location={quote_plus(location)}")

        # LinkedIn f_JT codes: F=Full-time, P=Part-time, C=Contract, T=Temporary, I=Internship
        jt_map = {
            "full_time": "F", "part_time": "P", "contract": "C",
            "temporary": "T", "internship": "I",
        }
        if job_type and job_type in jt_map:
            params.append(f"f_JT={jt_map[job_type]}")

        # LinkedIn f_E codes: 1=Internship, 2=Entry, 3=Associate, 4=Mid-Senior, 5=Director, 6=Executive
        exp_map = {
            "entry": "2", "mid": "4", "senior": "4",
            "lead": "4", "director": "5", "executive": "6",
        }
        if experience_level and experience_level in exp_map:
            params.append(f"f_E={exp_map[experience_level]}")

        if start > 0:
            params.append(f"start={start}")

        return base + "&".join(params)

    @staticmethod
    def _extract_job_id_from_href(href: str) -> str | None:
        """Pull the numeric job ID from a LinkedIn job URL."""
        match = re.search(r"/jobs/view/(\d+)", href)
        return match.group(1) if match else None
