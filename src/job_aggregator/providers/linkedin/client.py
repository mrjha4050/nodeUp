"""Low-level HTTP client for the LinkedIn API.

Handles session management, authentication, and raw HTTP calls.
This module speaks LinkedIn's API language — query params, headers,
endpoints. It returns raw dicts; the mapper handles conversion.
"""

import httpx

from src.job_aggregator.core import get_logger
from src.job_aggregator.providers.linkedin.config import LinkedInSettings
from src.job_aggregator.providers.linkedin.exceptions import (
    LinkedInAuthError,
    LinkedInError,
    LinkedInNotFoundError,
    LinkedInRateLimitError,
)

logger = get_logger(__name__)


class LinkedInClient:
    """Manages HTTP sessions and authentication with LinkedIn's API."""

    def __init__(self, settings: LinkedInSettings) -> None:
        self._settings = settings
        self._access_token: str | None = None
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
        """Build default request headers."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def authenticate(self) -> None:
        """Obtain an OAuth2 access token using client credentials.

        In production you would call LinkedIn's token endpoint.
        For now this is an abstraction point — swap in real logic
        when you have API credentials.
        """
        if not self._settings.client_id or not self._settings.client_secret:
            logger.warning("linkedin_auth_skipped", reason="missing credentials")
            return

        token_url = "https://www.linkedin.com/oauth/v2/accessToken"
        async with httpx.AsyncClient(timeout=httpx.Timeout(self._settings.timeout)) as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._settings.client_id,
                    "client_secret": self._settings.client_secret,
                },
            )

        if response.status_code != 200:
            raise LinkedInAuthError(
                f"Authentication failed: {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        self._access_token = data.get("access_token")
        logger.info("linkedin_authenticated")

    async def search_jobs_raw(
        self,
        keywords: str,
        location: str | None = None,
        job_type: str | None = None,
        experience_level: str | None = None,
        start: int = 0,
        count: int = 25,
    ) -> dict:
        """Execute a raw job search against LinkedIn's API.

        Returns the raw JSON dict from the API response.
        """
        client = await self._ensure_client()

        params: dict[str, str | int] = {
            "keywords": keywords,
            "start": start,
            "count": min(count, self._settings.max_results_per_page),
        }
        if location:
            params["location"] = location
        if job_type:
            params["jobType"] = job_type
        if experience_level:
            params["experienceLevel"] = experience_level

        logger.info("linkedin_search_request", keywords=keywords, location=location)

        response = await client.get("/jobSearch", params=params)
        self._raise_for_status(response)
        return response.json()

    async def get_job_raw(self, job_id: str) -> dict:
        """Fetch raw job details by ID from LinkedIn's API."""
        client = await self._ensure_client()

        logger.info("linkedin_job_detail_request", job_id=job_id)

        response = await client.get(f"/jobs/{job_id}")
        self._raise_for_status(response)
        return response.json()

    async def ping(self) -> bool:
        """Check if the LinkedIn API is reachable."""
        try:
            client = await self._ensure_client()
            response = await client.get("/me")
            return response.status_code < 500
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._client and not self._client.is_closed:
            await self._client.close()
            logger.info("linkedin_client_closed")

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Translate HTTP errors into LinkedIn-specific exceptions."""
        if response.status_code == 200:
            return

        if response.status_code == 401:
            raise LinkedInAuthError("Invalid or expired access token", status_code=401)

        if response.status_code == 404:
            raise LinkedInNotFoundError(response.url.path)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise LinkedInRateLimitError(
                retry_after=int(retry_after) if retry_after else None,
            )

        raise LinkedInError(
            f"LinkedIn API error: {response.status_code} — {response.text[:200]}",
            status_code=response.status_code,
        )
