"""Tests for provider implementations and registry."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from src.job_aggregator.models.search import SearchRequest
from src.job_aggregator.providers.linkedin.provider import LinkedInProvider
from src.job_aggregator.providers.linkedin.exceptions import LinkedInAuthError
from src.job_aggregator.providers.indeed.provider import IndeedProvider
from src.job_aggregator.providers.indeed.exceptions import IndeedAuthError
from src.job_aggregator.providers.registry import ProviderRegistry

from tests.conftest import MockProvider, make_job


# ------------------------------------------------------------------
# ProviderRegistry
# ------------------------------------------------------------------

class TestProviderRegistry:

    def test_register_and_get(self) -> None:
        reg = ProviderRegistry()
        provider = MockProvider(name="test")
        reg.register(provider)
        assert reg.get("test") is provider

    def test_get_nonexistent_returns_none(self) -> None:
        reg = ProviderRegistry()
        assert reg.get("nonexistent") is None

    def test_list_names(self) -> None:
        reg = ProviderRegistry()
        reg.register(MockProvider(name="a"))
        reg.register(MockProvider(name="b"))
        assert reg.list_names() == ["a", "b"]

    def test_duplicate_registration_warns(self) -> None:
        reg = ProviderRegistry()
        reg.register(MockProvider(name="dup"))
        reg.register(MockProvider(name="dup"))  # should warn, not raise
        assert len(reg.list_names()) == 1

    def test_get_all(self) -> None:
        reg = ProviderRegistry()
        reg.register(MockProvider(name="x"))
        reg.register(MockProvider(name="y"))
        assert len(reg.get_all()) == 2

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self) -> None:
        reg = ProviderRegistry()
        reg.register(MockProvider(name="healthy"))
        result = await reg.health_check_all()
        assert result == {"healthy": True}

    @pytest.mark.asyncio
    async def test_health_check_all_with_failure(self) -> None:
        reg = ProviderRegistry()
        reg.register(MockProvider(name="good"))
        reg.register(MockProvider(name="bad", should_fail=True))
        result = await reg.health_check_all()
        assert result["good"] is True
        assert result["bad"] is False


# ------------------------------------------------------------------
# LinkedInProvider (mocked client)
# ------------------------------------------------------------------

class TestLinkedInProvider:

    @pytest.mark.asyncio
    async def test_search_jobs_success(self) -> None:
        provider = LinkedInProvider()
        provider._client = AsyncMock()
        provider._client.authenticate = AsyncMock()
        provider._client.search_jobs_raw = AsyncMock(return_value={
            "elements": [
                {
                    "id": "111",
                    "title": "Python Dev",
                    "company": {"name": "TestCo", "url": "https://test.com", "industry": "Tech", "size": "10-50"},
                    "location": "NYC",
                    "employmentType": "F",
                    "experienceLevel": "2",
                    "skills": ["Python"],
                    "description": "Great job",
                    "applyUrl": "https://test.com/apply",
                },
            ],
            "paging": {"total": 1},
        })

        request = SearchRequest(query="python")
        response = await provider.search_jobs(request)

        assert response.success is True
        assert len(response.jobs) == 1
        assert response.jobs[0].id == "linkedin_111"
        assert response.provider_name == "linkedin"

    @pytest.mark.asyncio
    async def test_search_jobs_auth_error(self) -> None:
        provider = LinkedInProvider()
        provider._client = AsyncMock()
        provider._client.authenticate = AsyncMock(
            side_effect=LinkedInAuthError("bad token", status_code=401),
        )

        request = SearchRequest(query="python")
        response = await provider.search_jobs(request)

        assert response.success is False
        assert "bad token" in response.error_message

    @pytest.mark.asyncio
    async def test_search_jobs_unexpected_error(self) -> None:
        provider = LinkedInProvider()
        provider._client = AsyncMock()
        provider._client.authenticate = AsyncMock(side_effect=ValueError("boom"))

        request = SearchRequest(query="test")
        response = await provider.search_jobs(request)

        assert response.success is False
        assert "Unexpected error" in response.error_message

    @pytest.mark.asyncio
    async def test_get_job_details_success(self) -> None:
        provider = LinkedInProvider()
        provider._client = AsyncMock()
        provider._client.authenticate = AsyncMock()
        provider._client.get_job_raw = AsyncMock(return_value={
            "id": "222",
            "title": "ML Engineer",
            "company": {"name": "AI Co", "url": "https://ai.co", "industry": "AI", "size": "100+"},
            "location": "Remote",
            "description": "Do ML",
            "applyUrl": "https://ai.co/apply",
        })

        job = await provider.get_job_details("linkedin_222")
        assert job is not None
        assert job.id == "linkedin_222"

    @pytest.mark.asyncio
    async def test_get_job_details_not_found(self) -> None:
        provider = LinkedInProvider()
        provider._client = AsyncMock()
        provider._client.authenticate = AsyncMock()
        provider._client.get_job_raw = AsyncMock(return_value={"id": "", "title": ""})

        job = await provider.get_job_details("linkedin_999")
        assert job is None

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        provider = LinkedInProvider()
        provider._client = AsyncMock()
        provider._client.ping = AsyncMock(return_value=True)
        assert await provider.health_check() is True

    def test_provider_name(self) -> None:
        assert LinkedInProvider().provider_name == "linkedin"


# ------------------------------------------------------------------
# IndeedProvider (mocked client)
# ------------------------------------------------------------------

class TestIndeedProvider:

    @pytest.mark.asyncio
    async def test_search_jobs_success(self) -> None:
        provider = IndeedProvider()
        provider._client = AsyncMock()
        provider._client.search_jobs_raw = AsyncMock(return_value={
            "results": [
                {
                    "jobkey": "xyz789",
                    "jobtitle": "Go Developer",
                    "company": "GoCo",
                    "formattedLocation": "Austin, TX",
                    "snippet": "Write Go",
                    "url": "https://indeed.com/viewjob?jk=xyz789",
                    "jobType": "fulltime",
                    "remoteLocation": False,
                },
            ],
            "totalResults": 1,
        })

        request = SearchRequest(query="golang")
        response = await provider.search_jobs(request)

        assert response.success is True
        assert len(response.jobs) == 1
        assert response.jobs[0].id == "indeed_xyz789"

    @pytest.mark.asyncio
    async def test_search_jobs_api_error(self) -> None:
        provider = IndeedProvider()
        provider._client = AsyncMock()
        provider._client.search_jobs_raw = AsyncMock(
            side_effect=IndeedAuthError("bad key", status_code=403),
        )

        request = SearchRequest(query="test")
        response = await provider.search_jobs(request)

        assert response.success is False
        assert "bad key" in response.error_message

    @pytest.mark.asyncio
    async def test_get_job_details_success(self) -> None:
        provider = IndeedProvider()
        provider._client = AsyncMock()
        provider._client.get_job_raw = AsyncMock(return_value={
            "jobkey": "abc",
            "jobtitle": "Rust Dev",
            "company": "RustCo",
            "formattedLocation": "Remote",
            "snippet": "Write Rust",
            "url": "https://indeed.com/viewjob?jk=abc",
            "remoteLocation": True,
        })

        job = await provider.get_job_details("indeed_abc")
        assert job is not None
        assert job.id == "indeed_abc"

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        provider = IndeedProvider()
        provider._client = AsyncMock()
        provider._client.ping = AsyncMock(return_value=False)
        assert await provider.health_check() is False

    def test_provider_name(self) -> None:
        assert IndeedProvider().provider_name == "indeed"
