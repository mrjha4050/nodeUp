"""Job Aggregator Service.

Fans out a single SearchRequest to all registered providers
concurrently, collects their ProviderResponse objects, merges
the results, and returns a unified SearchResponse.

Provider failures are isolated — one provider going down never
takes down the entire search.
"""

import asyncio
import time

from src.job_aggregator.core import get_logger
from src.job_aggregator.models.job import Job
from src.job_aggregator.models.search import ProviderResponse, SearchRequest, SearchResponse
from src.job_aggregator.providers.base import JobProvider
from src.job_aggregator.providers.registry import ProviderRegistry
from src.job_aggregator.services.dedup import DeduplicationService

logger = get_logger(__name__)


class JobAggregatorService:
    """Orchestrates concurrent job searches across all providers."""

    def __init__(
        self,
        registry: ProviderRegistry,
        dedup_service: DeduplicationService | None = None,
    ) -> None:
        self._registry = registry
        self._dedup = dedup_service or DeduplicationService()

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Fan out the search to every registered provider concurrently.

        Each provider runs as an independent asyncio task. If a provider
        raises or times out, the others still return their results.
        """
        providers = self._registry.get_all()

        if not providers:
            logger.warning("aggregator_no_providers_registered")
            return self._empty_response(request)

        logger.info(
            "aggregator_search_start",
            query=request.query,
            providers=list(providers.keys()),
        )

        overall_start = time.monotonic()

        # Launch every provider concurrently
        tasks = {
            name: asyncio.create_task(
                self._execute_provider(provider, request),
                name=f"search_{name}",
            )
            for name, provider in providers.items()
        }

        # Wait for all to finish — never let one slow provider block the rest
        done, _ = await asyncio.wait(tasks.values(), return_when=asyncio.ALL_COMPLETED)

        # Collect results
        provider_responses: list[ProviderResponse] = []
        for name, task in tasks.items():
            response = task.result()  # _execute_provider never raises
            provider_responses.append(response)

        elapsed = time.monotonic() - overall_start

        merged = self._merge_responses(request, provider_responses)

        # Deduplicate across providers
        merged.jobs = self._dedup.deduplicate(merged.jobs)
        merged.total_results = len(merged.jobs)

        logger.info(
            "aggregator_search_complete",
            query=request.query,
            total_jobs=merged.total_results,
            providers_queried=len(providers),
            providers_failed=len(merged.error_messages),
            elapsed_seconds=round(elapsed, 3),
        )

        return merged

    async def get_job_details(self, job_id: str) -> Job | None:
        """Route a job-detail request to the correct provider.

        The provider is determined by the job ID prefix
        (e.g. 'linkedin_123' → linkedin provider).
        """
        provider_name = self._extract_provider_name(job_id)
        provider = self._registry.get(provider_name)

        if provider is None:
            logger.warning("aggregator_provider_not_found", job_id=job_id, provider=provider_name)
            return None

        logger.info("aggregator_job_detail_request", job_id=job_id, provider=provider_name)

        try:
            return await provider.get_job_details(job_id)
        except Exception:
            logger.exception("aggregator_job_detail_failed", job_id=job_id)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_provider(
        self,
        provider: JobProvider,
        request: SearchRequest,
    ) -> ProviderResponse:
        """Run a single provider's search with timing and error isolation.

        This method NEVER raises. On any failure it returns a
        ProviderResponse with success=False so the aggregator
        can merge partial results safely.
        """
        name = provider.provider_name
        start = time.monotonic()

        try:
            response = await provider.search_jobs(request)
            elapsed = time.monotonic() - start

            logger.info(
                "aggregator_provider_complete",
                provider=name,
                jobs=len(response.jobs) if response else 0,
                elapsed_seconds=round(elapsed, 3),
            )

            # Guard against a provider returning None
            if response is None:
                return ProviderResponse(
                    provider_name=name,
                    jobs=[],
                    total_results=0,
                    success=False,
                    error_message=f"Provider '{name}' returned None",
                )

            return response

        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "aggregator_provider_failed",
                provider=name,
                error=str(exc),
                elapsed_seconds=round(elapsed, 3),
            )
            return ProviderResponse(
                provider_name=name,
                jobs=[],
                total_results=0,
                success=False,
                error_message=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _merge_responses(
        request: SearchRequest,
        provider_responses: list[ProviderResponse],
    ) -> SearchResponse:
        """Combine multiple ProviderResponse objects into one SearchResponse."""
        all_jobs: list[Job] = []
        total_results = 0
        error_messages: list[str] = []

        for pr in provider_responses:
            if pr.success:
                all_jobs.extend(pr.jobs)
                total_results += pr.total_results
            else:
                if pr.error_message:
                    error_messages.append(f"[{pr.provider_name}] {pr.error_message}")

        return SearchResponse(
            query=request.query,
            location=request.location,
            jobs=all_jobs,
            job_type=request.job_type,
            skills=request.skills,
            total_results=total_results,
            providers=provider_responses,
            error_messages=error_messages,
        )

    @staticmethod
    def _empty_response(request: SearchRequest) -> SearchResponse:
        """Return an empty SearchResponse when no providers are registered."""
        return SearchResponse(
            query=request.query,
            location=request.location,
            jobs=[],
            job_type=request.job_type,
            skills=request.skills,
            total_results=0,
            providers=[],
            error_messages=["No providers registered"],
        )

    @staticmethod
    def _extract_provider_name(job_id: str) -> str:
        """Derive the provider name from a prefixed job ID.

        'linkedin_12345' → 'linkedin'
        'indeed_abc'     → 'indeed'
        'unknown'        → 'unknown'
        """
        parts = job_id.split("_", maxsplit=1)
        return parts[0] if len(parts) > 1 else job_id
