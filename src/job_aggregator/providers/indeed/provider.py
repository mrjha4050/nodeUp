"""IndeedProvider — the concrete JobProvider implementation for Indeed.

This is the only class the rest of the application sees.
It delegates HTTP work to IndeedClient and data mapping to the mapper.
Indeed-specific types never leak past this boundary.
"""

from src.job_aggregator.core import get_logger
from src.job_aggregator.models.job import Job
from src.job_aggregator.models.search import SearchRequest, ProviderResponse
from src.job_aggregator.providers.base import JobProvider
from src.job_aggregator.providers.indeed.client import IndeedClient
from src.job_aggregator.providers.indeed.config import IndeedSettings
from src.job_aggregator.providers.indeed.exceptions import IndeedError
from src.job_aggregator.providers.indeed.mapper import map_job

logger = get_logger(__name__)


class IndeedProvider(JobProvider):
    """Concrete Indeed implementation of the JobProvider interface."""

    def __init__(self, settings: IndeedSettings | None = None) -> None:
        self._settings = settings or IndeedSettings()
        self._client = IndeedClient(self._settings)

    @property
    def provider_name(self) -> str:
        return "indeed"

    async def search_jobs(self, search_request: SearchRequest) -> ProviderResponse:
        """Search Indeed for jobs and return a normalized ProviderResponse.

        All Indeed-specific data is mapped into domain models here.
        If the API call fails, returns ProviderResponse with
        success=False rather than raising.
        """
        try:
            raw_response = await self._client.search_jobs_raw(
                query=search_request.query,
                location=search_request.location,
                job_type=search_request.job_type.value if search_request.job_type else None,
                start=search_request.offset or 0,
                limit=search_request.limited_results or 25,
            )

            raw_jobs = raw_response.get("results", [])
            total = raw_response.get("totalResults", len(raw_jobs))

            jobs: list[Job] = []
            for raw in raw_jobs:
                job = map_job(raw)
                if job is not None:
                    jobs.append(job)

            jobs = self.apply_filters(jobs, search_request)

            logger.info(
                "indeed_search_complete",
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

        except IndeedError as exc:
            logger.error(
                "indeed_search_failed",
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
            logger.exception("indeed_search_unexpected_error", query=search_request.query)
            return ProviderResponse(
                provider_name=self.provider_name,
                jobs=[],
                total_results=0,
                success=False,
                error_message=f"Unexpected error: {exc}",
            )

    async def get_job_details(self, job_id: str) -> Job | None:
        """Fetch a single job's full details from Indeed.

        Returns None if the job is not found or the API fails.
        """
        clean_id = job_id.removeprefix("indeed_")
        try:
            raw = await self._client.get_job_raw(clean_id)
            job = map_job(raw)

            if job:
                logger.info("indeed_job_detail_ok", job_id=job_id)
            else:
                logger.warning("indeed_job_detail_mapping_failed", job_id=job_id)

            return job

        except IndeedError as exc:
            logger.error(
                "indeed_job_detail_failed",
                job_id=job_id,
                error=str(exc),
                status_code=exc.status_code,
            )
            return None
        except Exception:
            logger.exception("indeed_job_detail_unexpected_error", job_id=job_id)
            return None

    async def health_check(self) -> bool:
        """Check whether Indeed's API is reachable."""
        healthy = await self._client.ping()
        logger.info("indeed_health_check", healthy=healthy)
        return healthy

    async def close(self) -> None:
        """Shut down the HTTP session cleanly."""
        await self._client.close()

