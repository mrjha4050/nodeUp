"""Indeed page scraper using innerText extraction.

Navigates to Indeed pages and extracts visible text content.
Uses innerText instead of DOM selectors for resilience against
Indeed's layout changes.
"""

import re
from urllib.parse import quote_plus

from patchright.async_api import Page

from src.job_aggregator.core import get_logger
from src.job_aggregator.providers.indeed_browser.exceptions import (
    IndeedBlockedError,
    IndeedPageLoadError,
)

logger = get_logger(__name__)

# Indeed UI noise patterns to strip from extracted text
_NOISE_PATTERNS = [
    r"Skip to main content.*?\n",
    r"Post your resume.*?\n",
    r"Sign in.*?\n",
    r"Employers / Post Job.*?\n",
    r"Find jobs.*?\n",
    r"Company reviews.*?\n",
    r"Find salaries.*?\n",
    r"Upload your resume.*?\n",
    r"Let employers find you.*?\n",
    r"Page \d+ of \d+.*?\n",
    r"Be the first to see new.*?\n",
    r"By creating a job alert.*?\n",
    r"People also searched.*",
    r"Popular searches.*",
]

_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE | re.DOTALL)

# Patterns that indicate Indeed has blocked us
_BLOCK_PATTERNS = (
    "unusual traffic",
    "captcha",
    "verify you are human",
    "automated access",
)


def _clean_text(text: str) -> str:
    """Strip Indeed UI chrome from extracted text."""
    text = _NOISE_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class IndeedScraper:
    """Scrapes Indeed pages by extracting visible text."""

    def __init__(
        self,
        page: Page,
        navigation_timeout: int = 30000,
        country: str = "",
    ) -> None:
        self._page = page
        self._timeout = navigation_timeout
        self._base_domain = f"indeed.{country}" if country else "indeed.com"

    async def scrape_job_search(
        self,
        keywords: str,
        location: str | None = None,
        job_type: str | None = None,
        start: int = 0,
        count: int = 15,
    ) -> dict:
        """Scrape Indeed job search results page.

        Returns a dict with:
            - url: the scraped URL
            - text: cleaned visible text of the results
            - job_cards: list of dicts with per-card text chunks
        """
        url = self._build_search_url(keywords, location, job_type, start)

        logger.info("indeed_scraper_navigating", url=url)
        await self._navigate(url)

        # Check for blocking
        await self._check_blocked()

        # Wait for job cards to render
        try:
            await self._page.wait_for_selector(
                "#mosaic-jobResults, .jobsearch-ResultsList, #resultsBody, main",
                timeout=10000,
            )
        except Exception:
            logger.warning("indeed_scraper_job_list_selector_timeout", url=url)

        # Scroll to load more results
        await self._scroll_page(scroll_count=3)

        # Extract main content text
        main_text = await self._extract_main_text()

        # Extract individual job card texts
        job_cards = await self._extract_job_cards(count)

        logger.info(
            "indeed_scraper_search_complete",
            keywords=keywords,
            cards_found=len(job_cards),
        )

        return {
            "url": url,
            "text": _clean_text(main_text),
            "job_cards": job_cards,
        }

    async def scrape_job_details(self, job_key: str) -> dict:
        """Scrape a single job posting's detail page.

        Returns a dict with:
            - url: the scraped URL
            - text: cleaned visible text of the job posting
        """
        clean_key = job_key.removeprefix("indeed_browser_")
        url = f"https://www.{self._base_domain}/viewjob?jk={clean_key}"

        logger.info("indeed_scraper_job_detail_navigating", url=url)
        await self._navigate(url)

        await self._check_blocked()

        # Wait for job detail content
        try:
            await self._page.wait_for_selector(
                "#jobDescriptionText, .jobsearch-JobComponent, main",
                timeout=10000,
            )
        except Exception:
            logger.warning("indeed_scraper_job_detail_selector_timeout", url=url)

        text = await self._extract_detail_text()

        logger.info("indeed_scraper_job_detail_complete", job_key=job_key)

        return {
            "url": url,
            "text": _clean_text(text),
        }

    async def check_connectivity(self) -> bool:
        """Verify we can reach Indeed without being blocked."""
        try:
            await self._navigate(f"https://www.{self._base_domain}/")
            text = await self._extract_main_text()
            # If we can see the search form, we're good
            return "find jobs" in text.lower() or "job title" in text.lower() or "what" in text.lower()
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
                raise IndeedPageLoadError(url, f"HTTP {response.status}")
        except IndeedPageLoadError:
            raise
        except Exception as exc:
            raise IndeedPageLoadError(url, str(exc)) from exc

    async def _check_blocked(self) -> None:
        """Check if Indeed has blocked us with a CAPTCHA or rate limit.

        Only triggers on actual block pages — not the standard footer
        text "This site is protected by reCAPTCHA" that appears on all pages.
        """
        # Check page title and URL for block indicators
        title = await self._page.title()
        url = self._page.url
        title_lower = title.lower()

        if any(p in title_lower for p in ("security", "blocked", "denied", "verify")):
            logger.warning("indeed_scraper_blocked", title=title, url=url)
            raise IndeedBlockedError()

        # Check if the page has minimal content (a block page is usually very short)
        text = await self._page.evaluate(
            "() => (document.querySelector('main') || document.body).innerText || ''"
        )
        text_lower = text.lower()
        # Only flag if the page is very short AND contains blocking keywords
        if len(text) < 500:
            for pattern in _BLOCK_PATTERNS:
                if pattern in text_lower:
                    logger.warning("indeed_scraper_blocked", pattern=pattern)
                    raise IndeedBlockedError()

    async def _extract_main_text(self) -> str:
        """Extract visible text from the page's main content area."""
        text = await self._page.evaluate(
            "() => (document.querySelector('main') || document.getElementById('mosaic-provider-jobcards') || document.body).innerText || ''"
        )
        return text

    async def _extract_detail_text(self) -> str:
        """Extract visible text from a job detail page.

        Targets the job content container to avoid navigation header noise.
        """
        text = await self._page.evaluate("""() => {
            const selectors = [
                '.jobsearch-ViewJobLayout',
                '.jobsearch-JobComponent',
                '#viewJobSSRRoot',
                'main',
                'body'
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.innerText && el.innerText.length > 100) {
                    return el.innerText;
                }
            }
            return document.body.innerText || '';
        }""")
        return text

    async def _extract_job_cards(self, max_cards: int) -> list[dict]:
        """Extract text from individual job card elements.

        Tries multiple selectors since Indeed changes class names.
        """
        card_selectors = [
            ".job_seen_beacon",
            ".jobsearch-ResultsList > li",
            ".resultContent",
            "#mosaic-provider-jobcards .result",
            "div[data-jk]",
        ]

        for selector in card_selectors:
            cards = await self._page.query_selector_all(selector)
            if cards:
                results = []
                for card in cards[:max_cards]:
                    try:
                        text = await card.inner_text()
                        # Extract the job key from data-jk attribute
                        job_key = await card.get_attribute("data-jk")
                        if not job_key:
                            # Try child element with data-jk
                            child = await card.query_selector("[data-jk]")
                            if child:
                                job_key = await child.get_attribute("data-jk")

                        # Try to get the job link
                        link = await card.query_selector("a[href*='/rc/clk'], a[data-jk], h2 a")
                        href = await link.get_attribute("href") if link else None

                        # Extract job key from href if not found via attribute
                        if not job_key and href:
                            job_key = self._extract_job_key_from_href(href)

                        results.append({
                            "text": text.strip(),
                            "job_key": job_key,
                            "href": href,
                        })
                    except Exception:
                        continue
                if results:
                    return results

        logger.info("indeed_scraper_no_card_selectors_matched")
        return []

    async def _scroll_page(self, scroll_count: int = 3) -> None:
        """Scroll the page to trigger lazy-loaded content."""
        for i in range(scroll_count):
            await self._page.evaluate(f"window.scrollBy(0, {400 * (i + 1)})")
            await self._page.wait_for_timeout(500)

    def _build_search_url(
        self,
        keywords: str,
        location: str | None = None,
        job_type: str | None = None,
        start: int = 0,
    ) -> str:
        """Build an Indeed job search URL with query parameters."""
        base = f"https://www.{self._base_domain}/jobs?"
        params = [f"q={quote_plus(keywords)}"]

        if location:
            params.append(f"l={quote_plus(location)}")

        # Indeed jt codes: fulltime, parttime, contract, temporary, internship
        jt_map = {
            "full_time": "fulltime",
            "part_time": "parttime",
            "contract": "contract",
            "temporary": "temporary",
            "internship": "internship",
        }
        if job_type and job_type in jt_map:
            params.append(f"jt={jt_map[job_type]}")

        if start > 0:
            params.append(f"start={start}")

        return base + "&".join(params)

    @staticmethod
    def _extract_job_key_from_href(href: str) -> str | None:
        """Pull the job key from an Indeed job URL."""
        match = re.search(r"[?&]jk=([a-zA-Z0-9]+)", href)
        if match:
            return match.group(1)
        match = re.search(r"/rc/clk.*jk=([a-zA-Z0-9]+)", href)
        return match.group(1) if match else None
