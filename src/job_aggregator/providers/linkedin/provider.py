"""LinkedInProvider — the concrete JobProvider implementation.

This is the only class the rest of the application sees.
It delegates HTTP work to LinkedInClient and data mapping to the mapper.
LinkedIn-specific types never leak past this boundary.
"""

from src.job_aggregator.core import get_logger
from src.job_aggregator.models.job import Job
from src.job_aggregator.models.search import SearchRequest, SearchResponse, ProviderResponse
from src.job_aggregator.providers.base import JobProvider
from src.job_aggregator.providers.linkedin.client import LinkedInClient
from src.job_aggregator.providers.linkedin.config import LinkedInSettings
from src.job_aggregator.providers.linkedin.exceptions import LinkedInError
from src.job_aggregator.providers.linkedin.mapper import map_job

logger = get_logger(__name__)


class LinkedInProvider(JobProvider):
    """Concrete LinkedIn implementation of the JobProvider interface."""

    def __init__(self, settings: LinkedInSettings | None = None) -> None:
        self._settings = settings or LinkedInSettings()
        self._client = LinkedInClient(self._settings)

    @property
    def provider_name(self) -> str:
        return "linkedin"

    async def search_jobs(self, search_request: SearchRequest) -> ProviderResponse:
        """Search LinkedIn for jobs and return a normalized ProviderResponse.

        All LinkedIn-specific data is mapped into domain models here.
        If the API call fails, we return a ProviderResponse with
        success=False rather than raising — the aggregator can then
        decide how to handle partial failures.
        """
        try:
            await self._client.authenticate()

            raw_response = await self._client.search_jobs_raw(
                keywords=search_request.query,
                location=search_request.location,
                job_type=search_request.job_type.value if search_request.job_type else None,
                experience_level=(
                    search_request.experience_level.value
                    if search_request.experience_level
                    else None
                ),
                start=search_request.offset or 0,
                count=search_request.limited_results or 25,
            )

            raw_jobs = raw_response.get("elements", [])
            total = raw_response.get("paging", {}).get("total", len(raw_jobs))

            jobs: list[Job] = []
            for raw in raw_jobs:
                job = map_job(raw)
                if job is not None:
                    jobs.append(job)

            jobs = self.apply_filters(jobs, search_request)

            logger.info(
                "linkedin_search_complete",
                query=search_request.query,
                results=len(jobs),
                total=total,
            )

            return ProviderResponse(
                provider_name=self.provider_name,
                jobs=jobs,
                total_results=total,
                success=True,
            )

        except LinkedInError as exc:
            logger.error(
                "linkedin_search_failed",
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
            logger.exception("linkedin_search_unexpected_error", query=search_request.query)
            return ProviderResponse(
                provider_name=self.provider_name,
                jobs=[],
                total_results=0,
                success=False,
                error_message=f"Unexpected error: {exc}",
            )

    async def get_job_details(self, job_id: str) -> Job | None:
        """Fetch a single job's full details from LinkedIn.

        Returns None if the job is not found or the API fails.
        """
        clean_id = job_id.removeprefix("linkedin_")
        try:
            await self._client.authenticate()
            raw = await self._client.get_job_raw(clean_id)
            job = map_job(raw)

            if job:
                logger.info("linkedin_job_detail_ok", job_id=job_id)
            else:
                logger.warning("linkedin_job_detail_mapping_failed", job_id=job_id)

            return job

        except LinkedInError as exc:
            logger.error(
                "linkedin_job_detail_failed",
                job_id=job_id,
                error=str(exc),
                status_code=exc.status_code,
            )
            return None
        except Exception:
            logger.exception("linkedin_job_detail_unexpected_error", job_id=job_id)
            return None

    async def health_check(self) -> bool:
        """Check whether LinkedIn's API is reachable."""
        healthy = await self._client.ping()
        logger.info("linkedin_health_check", healthy=healthy)
        return healthy

    async def close(self) -> None:
        """Shut down the HTTP session cleanly."""
        await self._client.close()

