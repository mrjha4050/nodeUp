"""Tests for the LinkedIn browser-based provider.

Browser interactions are mocked — these test the parser, scraper logic,
and provider orchestration without launching a real browser.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.job_aggregator.models.search import SearchRequest
from src.job_aggregator.providers.linkedin_browser.provider import LinkedInBrowserProvider
from src.job_aggregator.providers.linkedin_browser.browser import BrowserManager
from src.job_aggregator.providers.linkedin_browser.config import LinkedInBrowserSettings
from src.job_aggregator.providers.linkedin_browser.scraper import LinkedInScraper
from src.job_aggregator.providers.linkedin_browser.parser import (
    parse_job_card,
    parse_job_detail,
    _detect_job_type,
    _detect_experience_level,
    _detect_location_type,
    _extract_salary,
    _extract_posted_time,
)
from src.job_aggregator.providers.linkedin_browser.exceptions import (
    LinkedInAuthRequiredError,
    LinkedInBrowserError,
    LinkedInPageLoadError,
)
from src.job_aggregator.models.job import JobType, ExperienceLevel, LocationType


# ------------------------------------------------------------------
# Parser tests
# ------------------------------------------------------------------

class TestParseJobCard:

    def test_valid_card(self) -> None:
        card = {
            "text": "Senior Python Engineer\nAcme Corp\nNew York, NY\n2 days ago",
            "job_id": "12345",
            "href": "https://www.linkedin.com/jobs/view/12345",
        }
        job = parse_job_card(card)
        assert job is not None
        assert job.id == "linkedin_browser_12345"
        assert job.title == "Senior Python Engineer"
        assert job.company_info.name == "Acme Corp"
        assert job.experience_level == ExperienceLevel.SENIOR

    def test_valid_card_with_duplicate_title(self) -> None:
        """LinkedIn duplicates the title — parser should skip it to find company."""
        card = {
            "text": "Python Developer\nPython Developer\nEmonics LLC\nArizona, United States (On-site)\n3 days ago\nEasy Apply",
            "job_id": "4438354140",
            "href": "/jobs/view/4438354140/?eBP=something",
        }
        job = parse_job_card(card)
        assert job is not None
        assert job.title == "Python Developer"
        assert job.company_info.name == "Emonics LLC"
        assert job.location == "Arizona, United States (On-site)"
        assert job.location_type == LocationType.ONSITE
        assert "linkedin.com" in str(job.application_url)

    def test_relative_href_becomes_absolute(self) -> None:
        card = {
            "text": "Dev\nCo\nNYC, NY\n1 day ago",
            "job_id": "999",
            "href": "/jobs/view/999/?tracking=abc",
        }
        job = parse_job_card(card)
        assert job is not None
        assert str(job.application_url).startswith("https://www.linkedin.com/")

    def test_missing_job_id_returns_none(self) -> None:
        card = {"text": "Some Job\nSome Company", "job_id": None, "href": None}
        assert parse_job_card(card) is None

    def test_missing_text_returns_none(self) -> None:
        card = {"text": "", "job_id": "123", "href": None}
        assert parse_job_card(card) is None

    def test_single_line_returns_none(self) -> None:
        card = {"text": "Just a title", "job_id": "123", "href": None}
        assert parse_job_card(card) is None

    def test_remote_detection(self) -> None:
        card = {
            "text": "Data Engineer\nData Engineer\nTech Co\nRemote\nFull-time",
            "job_id": "456",
            "href": None,
        }
        job = parse_job_card(card)
        assert job is not None
        assert job.company_info.name == "Tech Co"
        assert job.location_type == LocationType.REMOTE

    def test_hybrid_detection(self) -> None:
        card = {
            "text": "Designer\nDesigner\nDesign Studio\nSan Francisco, CA (Hybrid)\nFull-time",
            "job_id": "789",
            "href": None,
        }
        job = parse_job_card(card)
        assert job is not None
        assert job.location_type == LocationType.HYBRID


class TestParseJobDetail:

    def test_valid_detail(self) -> None:
        detail = {
            "text": "ML Engineer\nDeepTech Inc\nBoston, MA\nFull-time · Senior level\n\nAbout the job\nWe need a machine learning engineer.",
            "url": "https://www.linkedin.com/jobs/view/999",
        }
        job = parse_job_detail(detail, "linkedin_browser_999")
        assert job is not None
        assert job.title == "ML Engineer"
        assert job.company_info.name == "DeepTech Inc"

    def test_empty_text_returns_none(self) -> None:
        assert parse_job_detail({"text": ""}, "999") is None


# ------------------------------------------------------------------
# Detection helper tests
# ------------------------------------------------------------------

class TestDetectJobType:

    def test_full_time(self) -> None:
        assert _detect_job_type("Full-time position") == JobType.FULL_TIME

    def test_part_time(self) -> None:
        assert _detect_job_type("Part-time role") == JobType.PART_TIME

    def test_contract(self) -> None:
        assert _detect_job_type("Contract - 6 months") == JobType.CONTRACT

    def test_internship(self) -> None:
        assert _detect_job_type("Summer Internship") == JobType.INTERNSHIP

    def test_temporary(self) -> None:
        assert _detect_job_type("Temporary assignment") == JobType.TEMPORARY

    def test_default(self) -> None:
        assert _detect_job_type("Some job description") == JobType.FULL_TIME


class TestDetectExperienceLevel:

    def test_senior(self) -> None:
        assert _detect_experience_level("Senior Engineer") == ExperienceLevel.SENIOR

    def test_entry(self) -> None:
        assert _detect_experience_level("Entry Level Position") == ExperienceLevel.ENTRY

    def test_lead(self) -> None:
        assert _detect_experience_level("Lead Developer") == ExperienceLevel.LEAD

    def test_director(self) -> None:
        assert _detect_experience_level("Director of Engineering") == ExperienceLevel.DIRECTOR

    def test_default(self) -> None:
        assert _detect_experience_level("Software Engineer") == ExperienceLevel.MID


class TestDetectLocationType:

    def test_remote(self) -> None:
        assert _detect_location_type("Work from anywhere", "Remote") == LocationType.REMOTE

    def test_hybrid(self) -> None:
        assert _detect_location_type("Hybrid schedule", "NYC") == LocationType.HYBRID

    def test_onsite(self) -> None:
        assert _detect_location_type("In office", "San Francisco") == LocationType.ONSITE


class TestExtractSalary:

    def test_k_format(self) -> None:
        salary = _extract_salary("$100K - $150K per year")
        assert salary.min == 100000
        assert salary.max == 150000

    def test_full_format(self) -> None:
        salary = _extract_salary("$120,000 - $180,000/yr")
        assert salary.min == 120000
        assert salary.max == 180000

    def test_no_salary(self) -> None:
        salary = _extract_salary("No salary information")
        assert salary.min == 0
        assert salary.max == 0


class TestExtractPostedTime:

    def test_days_ago(self) -> None:
        dt = _extract_posted_time("Posted 3 days ago")
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        diff = now - dt
        assert 2 <= diff.days <= 4

    def test_no_time(self) -> None:
        dt = _extract_posted_time("No time info")
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        assert (now - dt).total_seconds() < 5


# ------------------------------------------------------------------
# Scraper URL building tests
# ------------------------------------------------------------------

class TestScraperUrlBuilding:

    def test_basic_search_url(self) -> None:
        url = LinkedInScraper._build_search_url("python developer")
        assert "keywords=python+developer" in url
        assert "linkedin.com/jobs/search" in url

    def test_search_url_with_location(self) -> None:
        url = LinkedInScraper._build_search_url("engineer", location="New York")
        assert "location=New+York" in url

    def test_search_url_with_job_type(self) -> None:
        url = LinkedInScraper._build_search_url("dev", job_type="full_time")
        assert "f_JT=F" in url

    def test_search_url_with_experience(self) -> None:
        url = LinkedInScraper._build_search_url("dev", experience_level="senior")
        assert "f_E=4" in url

    def test_search_url_with_offset(self) -> None:
        url = LinkedInScraper._build_search_url("dev", start=25)
        assert "start=25" in url

    def test_extract_job_id_from_href(self) -> None:
        href = "https://www.linkedin.com/jobs/view/3847291234/?trk=something"
        assert LinkedInScraper._extract_job_id_from_href(href) == "3847291234"

    def test_extract_job_id_no_match(self) -> None:
        assert LinkedInScraper._extract_job_id_from_href("/some/other/url") is None


# ------------------------------------------------------------------
# Provider orchestration tests (mocked browser)
# ------------------------------------------------------------------

class TestLinkedInBrowserProvider:

    @pytest.fixture
    def mock_browser_manager(self) -> BrowserManager:
        manager = MagicMock(spec=BrowserManager)
        manager.ensure_ready = AsyncMock()
        manager.close = AsyncMock()
        return manager

    @pytest.fixture
    def provider(self, mock_browser_manager) -> LinkedInBrowserProvider:
        settings = LinkedInBrowserSettings()
        return LinkedInBrowserProvider(settings=settings, browser_manager=mock_browser_manager)

    def test_provider_name(self, provider) -> None:
        assert provider.provider_name == "linkedin_browser"

    @pytest.mark.asyncio
    async def test_search_returns_provider_response(self, provider, mock_browser_manager) -> None:
        mock_page = MagicMock()
        mock_browser_manager.ensure_ready.return_value = mock_page

        with patch.object(LinkedInScraper, "scrape_job_search", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = {
                "url": "https://linkedin.com/jobs/search",
                "text": "results",
                "job_cards": [
                    {
                        "text": "Python Dev\nAcme\nNYC\nFull-time",
                        "job_id": "111",
                        "href": "https://linkedin.com/jobs/view/111",
                    },
                ],
            }

            request = SearchRequest(query="python")
            response = await provider.search_jobs(request)

            assert response.success is True
            assert response.provider_name == "linkedin_browser"
            assert len(response.jobs) == 1
            assert response.jobs[0].title == "Python Dev"

    @pytest.mark.asyncio
    async def test_search_auth_required(self, provider, mock_browser_manager) -> None:
        mock_browser_manager.ensure_ready.side_effect = LinkedInAuthRequiredError()

        request = SearchRequest(query="python")
        response = await provider.search_jobs(request)

        assert response.success is False
        assert "login required" in response.error_message.lower()

    @pytest.mark.asyncio
    async def test_search_unexpected_error(self, provider, mock_browser_manager) -> None:
        mock_browser_manager.ensure_ready.side_effect = RuntimeError("browser crashed")

        request = SearchRequest(query="python")
        response = await provider.search_jobs(request)

        assert response.success is False
        assert "Unexpected error" in response.error_message

    @pytest.mark.asyncio
    async def test_get_job_details_success(self, provider, mock_browser_manager) -> None:
        mock_page = MagicMock()
        mock_browser_manager.ensure_ready.return_value = mock_page

        with patch.object(LinkedInScraper, "scrape_job_details", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = {
                "url": "https://linkedin.com/jobs/view/222",
                "text": "ML Engineer\nDeepTech\nBoston, MA\nFull-time\n\nAbout the job\nGreat role.",
            }

            job = await provider.get_job_details("linkedin_browser_222")
            assert job is not None
            assert job.title == "ML Engineer"

    @pytest.mark.asyncio
    async def test_get_job_details_not_found(self, provider, mock_browser_manager) -> None:
        mock_page = MagicMock()
        mock_browser_manager.ensure_ready.return_value = mock_page

        with patch.object(LinkedInScraper, "scrape_job_details", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = {"url": "...", "text": ""}

            job = await provider.get_job_details("linkedin_browser_999")
            assert job is None

    @pytest.mark.asyncio
    async def test_health_check_success(self, provider, mock_browser_manager) -> None:
        mock_page = MagicMock()
        mock_browser_manager.ensure_ready.return_value = mock_page

        with patch.object(LinkedInScraper, "check_connectivity", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True
            assert await provider.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, provider, mock_browser_manager) -> None:
        mock_browser_manager.ensure_ready.side_effect = Exception("no browser")
        assert await provider.health_check() is False

    @pytest.mark.asyncio
    async def test_close(self, provider, mock_browser_manager) -> None:
        await provider.close()
        mock_browser_manager.close.assert_awaited_once()


# ------------------------------------------------------------------
# Exception tests
# ------------------------------------------------------------------

class TestExceptions:

    def test_auth_required(self) -> None:
        exc = LinkedInAuthRequiredError()
        assert "login required" in str(exc).lower()
        assert exc.status_code == 401

    def test_page_load_error(self) -> None:
        exc = LinkedInPageLoadError("https://linkedin.com/test", "timeout")
        assert "timeout" in str(exc)
        assert exc.status_code == 500

    def test_base_error(self) -> None:
        exc = LinkedInBrowserError("something broke", status_code=503)
        assert exc.status_code == 503


# ------------------------------------------------------------------
# Scraper URL builder tests for people search
# ------------------------------------------------------------------

class TestPeopleSearchUrl:

    def test_basic_people_search_url(self) -> None:
        url = LinkedInScraper._build_people_search_url("data scientist")
        assert "keywords=data+scientist" in url
        assert "linkedin.com/search/results/people" in url

    def test_people_search_url_with_location(self) -> None:
        url = LinkedInScraper._build_people_search_url("engineer", location="NYC")
        assert "location=NYC" in url

    def test_people_search_url_with_network(self) -> None:
        url = LinkedInScraper._build_people_search_url("pm", network="second")
        assert "network=" in url
        assert "S" in url

    def test_people_search_url_with_offset(self) -> None:
        url = LinkedInScraper._build_people_search_url("ml", start=10)
        assert "page=2" in url


# ------------------------------------------------------------------
# Provider: search_profiles tests
# ------------------------------------------------------------------

class TestSearchProfiles:

    @pytest.fixture
    def mock_browser_manager(self) -> BrowserManager:
        manager = MagicMock(spec=BrowserManager)
        manager.ensure_ready = AsyncMock()
        manager.close = AsyncMock()
        return manager

    @pytest.fixture
    def provider(self, mock_browser_manager) -> LinkedInBrowserProvider:
        settings = LinkedInBrowserSettings()
        return LinkedInBrowserProvider(settings=settings, browser_manager=mock_browser_manager)

    @pytest.mark.asyncio
    async def test_search_profiles_success(self, provider, mock_browser_manager) -> None:
        mock_page = MagicMock()
        mock_browser_manager.ensure_ready.return_value = mock_page

        with patch.object(LinkedInScraper, "scrape_people_search", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = {
                "url": "https://linkedin.com/search/results/people/?keywords=ml",
                "profiles": [
                    {
                        "name": "Jane Doe",
                        "headline": "ML Engineer at BigCo",
                        "location": "San Francisco",
                        "profile_url": "https://linkedin.com/in/janedoe",
                    },
                ],
            }

            result = await provider.search_profiles(keywords="ml engineer")

            assert result["success"] is True
            assert len(result["profiles"]) == 1
            assert result["profiles"][0]["name"] == "Jane Doe"

    @pytest.mark.asyncio
    async def test_search_profiles_auth_required(self, provider, mock_browser_manager) -> None:
        mock_browser_manager.ensure_ready.side_effect = LinkedInAuthRequiredError()

        result = await provider.search_profiles(keywords="ml")

        assert result["success"] is False
        assert "login required" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_search_profiles_unexpected_error(self, provider, mock_browser_manager) -> None:
        mock_browser_manager.ensure_ready.side_effect = RuntimeError("crashed")

        result = await provider.search_profiles(keywords="ml")

        assert result["success"] is False
        assert "Unexpected error" in result["error_message"]


# ------------------------------------------------------------------
# Provider: send_connection tests
# ------------------------------------------------------------------

class TestSendConnection:

    @pytest.fixture
    def mock_browser_manager(self) -> BrowserManager:
        manager = MagicMock(spec=BrowserManager)
        manager.ensure_ready = AsyncMock()
        manager.close = AsyncMock()
        return manager

    @pytest.fixture
    def provider(self, mock_browser_manager) -> LinkedInBrowserProvider:
        settings = LinkedInBrowserSettings()
        return LinkedInBrowserProvider(settings=settings, browser_manager=mock_browser_manager)

    @pytest.mark.asyncio
    async def test_send_connection_success(self, provider, mock_browser_manager) -> None:
        mock_page = MagicMock()
        mock_browser_manager.ensure_ready.return_value = mock_page

        with patch.object(LinkedInScraper, "send_connection_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"success": True, "message": "Connection request sent"}

            result = await provider.send_connection(
                profile_url="https://www.linkedin.com/in/janedoe/",
                note="Hi Jane, would love to connect!",
            )

            assert result["success"] is True
            mock_send.assert_awaited_once_with(
                "https://www.linkedin.com/in/janedoe/",
                "Hi Jane, would love to connect!",
            )

    @pytest.mark.asyncio
    async def test_send_connection_auth_required(self, provider, mock_browser_manager) -> None:
        mock_browser_manager.ensure_ready.side_effect = LinkedInAuthRequiredError()

        result = await provider.send_connection(
            profile_url="https://www.linkedin.com/in/janedoe/",
        )

        assert result["success"] is False
        assert "login required" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_send_connection_no_button(self, provider, mock_browser_manager) -> None:
        mock_page = MagicMock()
        mock_browser_manager.ensure_ready.return_value = mock_page

        with patch.object(LinkedInScraper, "send_connection_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {
                "success": False,
                "message": "Connect button not found — may already be connected or pending",
            }

            result = await provider.send_connection(
                profile_url="https://www.linkedin.com/in/janedoe/",
            )

            assert result["success"] is False
            assert "Connect button not found" in result["message"]
