
from abc import ABC, abstractmethod

from src.job_aggregator.models.job import Job
from src.job_aggregator.models.search import SearchRequest, ProviderResponse


class JobProvider(ABC):
    """Abstract base class for job providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of the job provider."""
        ...

    @abstractmethod
    async def search_jobs(self, search_request: SearchRequest) -> ProviderResponse:
        """Search for jobs based on the provided search request."""
        ...

    @abstractmethod
    async def get_job_details(self, job_id: str) -> Job | None:
        """Retrieve detailed information about a specific job."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check whether the provider's API is reachable."""
        ...

    @staticmethod
    def apply_filters(jobs: list[Job], request: SearchRequest) -> list[Job]:
        """Apply client-side filters that APIs don't natively support.

        Shared across all providers to avoid duplication.
        """
        filtered = jobs

        if request.location_type:
            filtered = [j for j in filtered if j.location_type == request.location_type]

        if request.skills:
            request_skills = {s.lower() for s in request.skills}
            filtered = [
                j for j in filtered
                if request_skills & {s.lower() for s in j.skills}
            ]

        return filtered