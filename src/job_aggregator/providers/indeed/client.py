"""Low-level HTTP client for the Indeed API.

Handles session lifecycle, authentication headers, and raw HTTP calls.
Returns raw dicts — the mapper handles conversion to domain models.
"""

import httpx

from src.job_aggregator.core import get_logger
from src.job_aggregator.providers.indeed.config import IndeedSettings
from src.job_aggregator.providers.indeed.exceptions import (
    IndeedAuthError,
    IndeedError,
    IndeedNotFoundError,
    IndeedRateLimitError,
)

logger = get_logger(__name__)


class IndeedClient:
    """Manages HTTP sessions and authentication with Indeed's API."""

    def __init__(self, settings: IndeedSettings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create and return the httpx async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._settings.base_url,
                timeout=httpx.Timeout(self._settings.timeout),
                headers=self._build_headers(),
            )
        return self._client

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with API key authentication."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"
        if self._settings.publisher_id:
            headers["X-Publisher-ID"] = self._settings.publisher_id
        return headers

    async def search_jobs_raw(
        self,
        query: str,
        location: str | None = None,
        job_type: str | None = None,
        start: int = 0,
        limit: int = 25,
    ) -> dict:
        """Execute a raw job search against Indeed's API.

        Returns the raw JSON dict from the API response.
        """
        client = await self._ensure_client()

        params: dict[str, str | int] = {
            "q": query,
            "start": start,
            "limit": min(limit, self._settings.max_results_per_page),
            "co": self._settings.country,
        }
        if location:
            params["l"] = location
        if job_type:
            params["jt"] = job_type

        logger.info("indeed_search_request", query=query, location=location)

        response = await client.get("/search", params=params)
        self._raise_for_status(response)
        return response.json()

    async def get_job_raw(self, job_key: str) -> dict:
        """Fetch raw job details by key from Indeed's API."""
        client = await self._ensure_client()

        logger.info("indeed_job_detail_request", job_key=job_key)

        response = await client.get("/job", params={"jk": job_key})
        self._raise_for_status(response)
        return response.json()

    async def ping(self) -> bool:
        """Check if the Indeed API is reachable."""
        try:
            client = await self._ensure_client()
            response = await client.get("/health")
            return response.status_code < 500
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._client and not self._client.is_closed:
            await self._client.close()
            logger.info("indeed_client_closed")

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Translate HTTP errors into Indeed-specific exceptions."""
        if response.status_code == 200:
            return

        if response.status_code in (401, 403):
            raise IndeedAuthError(
                f"Authentication failed: {response.status_code}",
                status_code=response.status_code,
            )

        if response.status_code == 404:
            raise IndeedNotFoundError(response.url.path)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise IndeedRateLimitError(
                retry_after=int(retry_after) if retry_after else None,
            )

        raise IndeedError(
            f"Indeed API error: {response.status_code} — {response.text[:200]}",
            status_code=response.status_code,
        )
