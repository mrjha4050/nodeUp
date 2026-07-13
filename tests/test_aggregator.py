"""Tests for the JobAggregatorService."""

import pytest

from src.job_aggregator.models.search import SearchRequest
from src.job_aggregator.providers.registry import ProviderRegistry
from src.job_aggregator.services.aggregator import JobAggregatorService
from src.job_aggregator.services.dedup import DeduplicationService

from tests.conftest import MockProvider, make_job


class TestAggregatorSearch:

    @pytest.mark.asyncio
    async def test_search_single_provider(self, registry, search_request) -> None:
        service = JobAggregatorService(registry)
        response = await service.search(search_request)

        assert response.query == "python developer"
        assert len(response.jobs) == 3
        assert len(response.providers) == 1
        assert response.providers[0].success is True

    @pytest.mark.asyncio
    async def test_search_multiple_providers(self, search_request) -> None:
        jobs_a = [make_job(id="a_1", title="Job A", company="Co A", location="NYC")]
        jobs_b = [make_job(id="b_1", title="Job B", company="Co B", location="LA")]

        reg = ProviderRegistry()
        reg.register(MockProvider(name="provider_a", jobs=jobs_a))
        reg.register(MockProvider(name="provider_b", jobs=jobs_b))

        service = JobAggregatorService(reg)
        response = await service.search(search_request)

        assert len(response.jobs) == 2
        assert len(response.providers) == 2
        assert response.total_results == 2

    @pytest.mark.asyncio
    async def test_search_no_providers(self, search_request) -> None:
        reg = ProviderRegistry()
        service = JobAggregatorService(reg)
        response = await service.search(search_request)

        assert len(response.jobs) == 0
        assert "No providers registered" in response.error_messages

    @pytest.mark.asyncio
    async def test_search_with_one_failing_provider(self, search_request) -> None:
        jobs = [make_job(id="ok_1", title="Good Job", company="GoodCo", location="NYC")]
        reg = ProviderRegistry()
        reg.register(MockProvider(name="good", jobs=jobs))
        reg.register(MockProvider(name="bad", should_fail=True))

        service = JobAggregatorService(reg)
        response = await service.search(search_request)

        assert len(response.jobs) == 1
        assert len(response.error_messages) == 1
        assert "[bad]" in response.error_messages[0]

    @pytest.mark.asyncio
    async def test_search_all_providers_fail(self, search_request) -> None:
        reg = ProviderRegistry()
        reg.register(MockProvider(name="fail1", should_fail=True))
        reg.register(MockProvider(name="fail2", should_fail=True))

        service = JobAggregatorService(reg)
        response = await service.search(search_request)

        assert len(response.jobs) == 0
        assert len(response.error_messages) == 2

    @pytest.mark.asyncio
    async def test_search_deduplicates_results(self, search_request) -> None:
        """Same job from two providers should be deduplicated."""
        same_job_a = make_job(id="a_1", title="Engineer", company="Acme", location="NYC")
        same_job_b = make_job(id="b_1", title="Engineer", company="Acme", location="NYC")

        reg = ProviderRegistry()
        reg.register(MockProvider(name="a", jobs=[same_job_a]))
        reg.register(MockProvider(name="b", jobs=[same_job_b]))

        service = JobAggregatorService(reg, dedup_service=DeduplicationService())
        response = await service.search(search_request)

        assert len(response.jobs) == 1


class TestAggregatorJobDetails:

    @pytest.mark.asyncio
    async def test_routes_to_correct_provider(self) -> None:
        job = make_job(id="alpha_123", title="Test", company="X", location="Y")
        reg = ProviderRegistry()
        reg.register(MockProvider(name="alpha", jobs=[job]))

        service = JobAggregatorService(reg)
        result = await service.get_job_details("alpha_123")
        assert result is not None
        assert result.id == "alpha_123"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_provider(self) -> None:
        reg = ProviderRegistry()
        service = JobAggregatorService(reg)
        result = await service.get_job_details("unknown_123")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_job(self) -> None:
        reg = ProviderRegistry()
        reg.register(MockProvider(name="mock", jobs=[]))
        service = JobAggregatorService(reg)
        result = await service.get_job_details("mock_nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_provider_exception(self) -> None:
        reg = ProviderRegistry()
        reg.register(MockProvider(name="crash", should_fail=True))
        service = JobAggregatorService(reg)
        result = await service.get_job_details("crash_123")
        assert result is None


class TestExtractProviderName:

    def test_linkedin_prefix(self) -> None:
        assert JobAggregatorService._extract_provider_name("linkedin_12345") == "linkedin"

    def test_indeed_prefix(self) -> None:
        assert JobAggregatorService._extract_provider_name("indeed_abc") == "indeed"

    def test_no_underscore(self) -> None:
        assert JobAggregatorService._extract_provider_name("nounderscore") == "nounderscore"

    def test_multiple_underscores(self) -> None:
        assert JobAggregatorService._extract_provider_name("provider_job_123") == "provider"
