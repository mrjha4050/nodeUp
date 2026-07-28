"""Tests for the Indeed browser-based provider.

Browser interactions are mocked — these test the parser, scraper logic,
and provider orchestration without launching a real browser.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.job_aggregator.models.search import SearchRequest
from src.job_aggregator.providers.indeed_browser.provider import IndeedBrowserProvider
from src.job_aggregator.providers.indeed_browser.browser import IndeedBrowserManager
from src.job_aggregator.providers.indeed_browser.config import IndeedBrowserSettings
from src.job_aggregator.providers.indeed_browser.scraper import IndeedScraper
from src.job_aggregator.providers.indeed_browser.parser import (
    parse_job_card,
    parse_job_detail,
    _detect_job_type,
    _detect_experience_level,
    _detect_location_type,
    _extract_salary,
    _extract_posted_time,
    _extract_location,
)
from src.job_aggregator.providers.indeed_browser.exceptions import (
    IndeedBlockedError,
    IndeedBrowserError,
    IndeedPageLoadError,
)
from src.job_aggregator.models.job import JobType, ExperienceLevel, LocationType


# ------------------------------------------------------------------
# Parser tests
# ------------------------------------------------------------------

class TestParseJobCard:

    def test_valid_card(self) -> None:
        card = {
            "text": "Senior Python Developer\nAcme Corp\nNew York, NY\n$120,000 - $160,000 a year\nPosted 3 days ago",
            "job_key": "abc123def",
            "href": "https://www.indeed.com/rc/clk?jk=abc123def",
        }
        job = parse_job_card(card)
        assert job is not None
        assert job.id == "indeed_browser_abc123def"
        assert job.title == "Senior Python Developer"
        assert job.company_info.name == "Acme Corp"
        assert job.experience_level == ExperienceLevel.SENIOR

    def test_card_with_company_rating(self) -> None:
        card = {
            "text": "Data Engineer\nTechCo 4.2\nSan Francisco, CA\nPosted today",
            "job_key": "xyz789",
            "href": "/rc/clk?jk=xyz789",
        }
        job = parse_job_card(card)
        assert job is not None
        assert job.company_info.name == "TechCo"

    def test_card_missing_job_key(self) -> None:
        card = {"text": "Some Job\nSome Company", "job_key": None, "href": None}
        assert parse_job_card(card) is None

    def test_card_empty_text(self) -> None:
        card = {"text": "", "job_key": "abc", "href": None}
        assert parse_job_card(card) is None

    def test_card_too_few_lines(self) -> None:
        card = {"text": "Only Title", "job_key": "abc", "href": None}
        assert parse_job_card(card) is None

    def test_card_with_relative_href(self) -> None:
        card = {
            "text": "ML Engineer\nAI Corp\nRemote\nPosted 1 day ago",
            "job_key": "rel123",
            "href": "/rc/clk?jk=rel123",
        }
        job = parse_job_card(card)
        assert job is not None
        assert str(job.application_url).startswith("https://www.indeed.com/")

    def test_card_no_href_uses_viewjob(self) -> None:
        card = {
            "text": "Backend Dev\nStartup Inc\nAustin, TX",
            "job_key": "nohref1",
            "href": None,
        }
        job = parse_job_card(card)
        assert job is not None
        assert "viewjob?jk=nohref1" in str(job.application_url)

    def test_remote_card(self) -> None:
        card = {
            "text": "DevOps Engineer\nCloud Inc\nRemote\n$90,000 - $130,000 a year",
            "job_key": "rem456",
            "href": "https://www.indeed.com/viewjob?jk=rem456",
        }
        job = parse_job_card(card)
        assert job is not None
        assert job.location_type == LocationType.REMOTE


class TestParseJobDetail:

    def test_valid_detail(self) -> None:
        detail = {
            "text": "Full Stack Developer\nWebCo\nChicago, IL\n$100,000 - $140,000 a year\n\nFull job description\nWe are looking for a Full Stack Developer...",
            "url": "https://www.indeed.com/viewjob?jk=det123",
        }
        job = parse_job_detail(detail, "indeed_browser_det123")
        assert job is not None
        assert job.id == "indeed_browser_det123"
        assert job.title == "Full Stack Developer"
        assert job.company_info.name == "WebCo"

    def test_detail_empty_text(self) -> None:
        assert parse_job_detail({"text": ""}, "x") is None

    def test_detail_strips_id_prefix(self) -> None:
        detail = {
            "text": "Engineer\nCo\nNY, NY\nDescription here",
            "url": "https://www.indeed.com/viewjob?jk=abc",
        }
        job = parse_job_detail(detail, "indeed_browser_abc")
        assert job is not None
        assert job.id == "indeed_browser_abc"


# ------------------------------------------------------------------
# Detection helpers
# ------------------------------------------------------------------

class TestDetectJobType:

    def test_full_time(self) -> None:
        assert _detect_job_type("Full-time position") == JobType.FULL_TIME

    def test_part_time(self) -> None:
        assert _detect_job_type("Part-time weekend work") == JobType.PART_TIME

    def test_contract(self) -> None:
        assert _detect_job_type("Contract role, 6 months") == JobType.CONTRACT

    def test_internship(self) -> None:
        assert _detect_job_type("Summer internship program") == JobType.INTERNSHIP

    def test_temporary(self) -> None:
        assert _detect_job_type("Temporary warehouse work") == JobType.TEMPORARY

    def test_default_full_time(self) -> None:
        assert _detect_job_type("Software engineer") == JobType.FULL_TIME


class TestDetectExperienceLevel:

    def test_senior(self) -> None:
        assert _detect_experience_level("Senior Python Developer") == ExperienceLevel.SENIOR

    def test_entry(self) -> None:
        assert _detect_experience_level("Entry level analyst") == ExperienceLevel.ENTRY

    def test_lead(self) -> None:
        assert _detect_experience_level("Lead Engineer") == ExperienceLevel.LEAD

    def test_director(self) -> None:
        assert _detect_experience_level("Director of Engineering") == ExperienceLevel.DIRECTOR

    def test_executive(self) -> None:
        assert _detect_experience_level("VP of Engineering") == ExperienceLevel.EXECUTIVE

    def test_default_mid(self) -> None:
        assert _detect_experience_level("Software Developer") == ExperienceLevel.MID


class TestDetectLocationType:

    def test_remote(self) -> None:
        assert _detect_location_type("Work from home", "Remote") == LocationType.REMOTE

    def test_hybrid(self) -> None:
        assert _detect_location_type("Hybrid remote", "Austin, TX") == LocationType.HYBRID

    def test_onsite(self) -> None:
        assert _detect_location_type("In office", "NYC") == LocationType.ONSITE


class TestExtractSalary:

    def test_yearly_range(self) -> None:
        salary = _extract_salary("$80,000 - $120,000 a year")
        assert salary.min == 80000
        assert salary.max == 120000

    def test_hourly_range(self) -> None:
        salary = _extract_salary("$25 - $35 an hour")
        assert salary.min == 25 * 2080
        assert salary.max == 35 * 2080

    def test_no_salary(self) -> None:
        salary = _extract_salary("No salary info here")
        assert salary.min == 0
        assert salary.max == 0


class TestExtractLocation:

    def test_city_state(self) -> None:
        lines = ["Title", "Company", "New York, NY", "Other stuff"]
        assert _extract_location(lines) == "New York, NY"

    def test_remote(self) -> None:
        lines = ["Title", "Company", "Remote", "Other"]
        assert _extract_location(lines) == "Remote"

    def test_hybrid_remote(self) -> None:
        lines = ["Title", "Company", "Hybrid remote in Austin, TX"]
        assert _extract_location(lines) == "Hybrid remote in Austin, TX"


class TestExtractPostedTime:

    def test_days_ago(self) -> None:
        dt = _extract_posted_time("Posted 3 days ago")
        from datetime import datetime, timezone
        assert (datetime.now(tz=timezone.utc) - dt).days >= 2

    def test_just_posted(self) -> None:
        dt = _extract_posted_time("Just posted")
        from datetime import datetime, timezone
        assert (datetime.now(tz=timezone.utc) - dt).total_seconds() < 60

    def test_active_days(self) -> None:
        dt = _extract_posted_time("Active 5 days ago")
        from datetime import datetime, timezone
        assert (datetime.now(tz=timezone.utc) - dt).days >= 4


# ------------------------------------------------------------------
# Scraper URL building tests
# ------------------------------------------------------------------

class TestIndeedScraperUrlBuilding:

    def _make_scraper(self) -> IndeedScraper:
        page = MagicMock()
        return IndeedScraper(page, navigation_timeout=30000, country="")

    def test_basic_search_url(self) -> None:
        scraper = self._make_scraper()
        url = scraper._build_search_url("python developer")
        assert "q=python+developer" in url
        assert "indeed.com/jobs?" in url

    def test_search_url_with_location(self) -> None:
        scraper = self._make_scraper()
        url = scraper._build_search_url("engineer", location="New York")
        assert "l=New+York" in url

    def test_search_url_with_job_type(self) -> None:
        scraper = self._make_scraper()
        url = scraper._build_search_url("dev", job_type="full_time")
        assert "jt=fulltime" in url

    def test_search_url_with_start(self) -> None:
        scraper = self._make_scraper()
        url = scraper._build_search_url("dev", start=10)
        assert "start=10" in url

    def test_country_domain(self) -> None:
        page = MagicMock()
        scraper = IndeedScraper(page, country="co.uk")
        url = scraper._build_search_url("engineer")
        assert "indeed.co.uk/jobs?" in url

    def test_extract_job_key_from_href(self) -> None:
        assert IndeedScraper._extract_job_key_from_href("/rc/clk?jk=abc123def") == "abc123def"
        assert IndeedScraper._extract_job_key_from_href("?jk=xyz789") == "xyz789"
        assert IndeedScraper._extract_job_key_from_href("/some/other/path") is None


# ------------------------------------------------------------------
# Provider orchestration tests
# ------------------------------------------------------------------

class TestIndeedBrowserProvider:

    @pytest.fixture
    def mock_browser(self) -> IndeedBrowserManager:
        manager = MagicMock(spec=IndeedBrowserManager)
        page = AsyncMock()
        manager.ensure_ready = AsyncMock(return_value=page)
        manager.close = AsyncMock()
        return manager

    @pytest.fixture
    def provider(self, mock_browser: IndeedBrowserManager) -> IndeedBrowserProvider:
        settings = IndeedBrowserSettings()
        return IndeedBrowserProvider(settings=settings, browser_manager=mock_browser)

    def test_provider_name(self, provider: IndeedBrowserProvider) -> None:
        assert provider.provider_name == "indeed_browser"

    @pytest.mark.asyncio
    async def test_search_returns_provider_response(self, provider: IndeedBrowserProvider) -> None:
        request = SearchRequest(query="python developer")

        with patch.object(IndeedScraper, "scrape_job_search", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = {
                "url": "https://www.indeed.com/jobs?q=python+developer",
                "text": "results",
                "job_cards": [
                    {
                        "text": "Python Dev\nTech Co\nNYC, NY\nPosted 1 day ago",
                        "job_key": "abc123",
                        "href": "https://www.indeed.com/viewjob?jk=abc123",
                    }
                ],
            }

            response = await provider.search_jobs(request)
            assert response.success is True
            assert response.provider_name == "indeed_browser"
            assert len(response.jobs) == 1
            assert response.jobs[0].title == "Python Dev"

    @pytest.mark.asyncio
    async def test_search_handles_browser_error(self, provider: IndeedBrowserProvider) -> None:
        request = SearchRequest(query="test")

        with patch.object(IndeedScraper, "scrape_job_search", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = IndeedPageLoadError("https://indeed.com", "timeout")

            response = await provider.search_jobs(request)
            assert response.success is False
            assert response.error_message is not None

    @pytest.mark.asyncio
    async def test_search_handles_blocked_error(self, provider: IndeedBrowserProvider) -> None:
        request = SearchRequest(query="test")

        with patch.object(IndeedScraper, "scrape_job_search", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = IndeedBlockedError()

            response = await provider.search_jobs(request)
            assert response.success is False
            assert "blocked" in response.error_message.lower()

    @pytest.mark.asyncio
    async def test_search_handles_unexpected_error(self, provider: IndeedBrowserProvider) -> None:
        request = SearchRequest(query="test")

        with patch.object(IndeedScraper, "scrape_job_search", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = RuntimeError("Something unexpected")

            response = await provider.search_jobs(request)
            assert response.success is False
            assert "unexpected" in response.error_message.lower()

    @pytest.mark.asyncio
    async def test_get_job_details(self, provider: IndeedBrowserProvider) -> None:
        with patch.object(IndeedScraper, "scrape_job_details", new_callable=AsyncMock) as mock_detail:
            mock_detail.return_value = {
                "text": "Senior Engineer\nBigCo\nRemote\n$150,000 - $200,000 a year\n\nFull job description\nGreat role...",
                "url": "https://www.indeed.com/viewjob?jk=det456",
            }

            job = await provider.get_job_details("indeed_browser_det456")
            assert job is not None
            assert job.title == "Senior Engineer"

    @pytest.mark.asyncio
    async def test_get_job_details_returns_none_on_error(self, provider: IndeedBrowserProvider) -> None:
        with patch.object(IndeedScraper, "scrape_job_details", new_callable=AsyncMock) as mock_detail:
            mock_detail.side_effect = IndeedPageLoadError("url", "error")

            job = await provider.get_job_details("indeed_browser_xxx")
            assert job is None

    @pytest.mark.asyncio
    async def test_health_check_success(self, provider: IndeedBrowserProvider) -> None:
        with patch.object(IndeedScraper, "check_connectivity", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True
            assert await provider.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, provider: IndeedBrowserProvider) -> None:
        with patch.object(IndeedScraper, "check_connectivity", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False
            assert await provider.health_check() is False

    @pytest.mark.asyncio
    async def test_close(self, provider: IndeedBrowserProvider, mock_browser: IndeedBrowserManager) -> None:
        await provider.close()
        mock_browser.close.assert_awaited_once()


# ------------------------------------------------------------------
# Exception tests
# ------------------------------------------------------------------

class TestExceptions:

    def test_browser_error(self) -> None:
        err = IndeedBrowserError("test error", status_code=500)
        assert str(err) == "test error"
        assert err.status_code == 500

    def test_page_load_error(self) -> None:
        err = IndeedPageLoadError("https://indeed.com", "timeout")
        assert "indeed.com" in str(err)
        assert "timeout" in str(err)
        assert err.status_code == 500

    def test_page_load_error_no_reason(self) -> None:
        err = IndeedPageLoadError("https://indeed.com")
        assert "indeed.com" in str(err)

    def test_blocked_error(self) -> None:
        err = IndeedBlockedError()
        assert err.status_code == 429
        assert "blocked" in str(err).lower()
