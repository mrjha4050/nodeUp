"""Tests for Indeed response mapper."""

from datetime import timezone

from src.job_aggregator.providers.indeed.mapper import (
    map_job,
    _detect_location_type,
    _extract_skills,
    _parse_date,
    _parse_job_type,
)
from src.job_aggregator.models.job import JobType, LocationType


class TestIndeedMapper:

    def _raw_job(self, **overrides) -> dict:
        """Build a minimal valid Indeed raw job dict."""
        base = {
            "jobkey": "abc123",
            "jobtitle": "Data Engineer",
            "company": "Globex Inc",
            "formattedLocation": "Remote",
            "snippet": "Work with data pipelines",
            "url": "https://indeed.com/viewjob?jk=abc123",
            "jobType": "fulltime",
            "experienceLevel": "senior",
            "remoteLocation": True,
            "salarySnippet": {"min": 130000, "max": 170000, "currency": "USD", "salaryType": "yearly"},
            "date": "2026-01-15",
            "skills": ["Python", "Spark"],
        }
        base.update(overrides)
        return base

    def test_valid_job_maps_correctly(self) -> None:
        job = map_job(self._raw_job())
        assert job is not None
        assert job.id == "indeed_abc123"
        assert job.title == "Data Engineer"
        assert job.company_info.name == "Globex Inc"
        assert job.location_type == LocationType.REMOTE

    def test_uses_jobtitle_field(self) -> None:
        job = map_job(self._raw_job(jobtitle="ML Engineer"))
        assert job is not None
        assert job.title == "ML Engineer"

    def test_falls_back_to_title_field(self) -> None:
        raw = self._raw_job()
        del raw["jobtitle"]
        raw["title"] = "Alt Title"
        job = map_job(raw)
        assert job is not None
        assert job.title == "Alt Title"

    def test_falls_back_to_id_field(self) -> None:
        raw = self._raw_job()
        del raw["jobkey"]
        raw["id"] = "fallback_id"
        job = map_job(raw)
        assert job is not None
        assert job.id == "indeed_fallback_id"

    def test_missing_jobkey_and_id_returns_none(self) -> None:
        raw = self._raw_job()
        del raw["jobkey"]
        assert map_job(raw) is None

    def test_missing_title_returns_none(self) -> None:
        raw = self._raw_job()
        raw["jobtitle"] = ""
        assert map_job(raw) is None

    def test_salary_parsing(self) -> None:
        job = map_job(self._raw_job())
        assert job is not None
        assert job.salary_range.min == 130000
        assert job.salary_range.max == 170000

    def test_salary_from_flat_fields(self) -> None:
        raw = self._raw_job()
        del raw["salarySnippet"]
        raw["salaryMin"] = 100000
        raw["salaryMax"] = 140000
        job = map_job(raw)
        assert job is not None
        assert job.salary_range.min == 100000

    def test_skills_from_attributes(self) -> None:
        raw = self._raw_job()
        raw["skills"] = []
        raw["attributes"] = ["Docker", {"label": "Kubernetes"}]
        job = map_job(raw)
        assert job is not None
        assert "Docker" in job.skills
        assert "Kubernetes" in job.skills

    def test_skills_from_taxon_attributes(self) -> None:
        raw = self._raw_job()
        raw["skills"] = []
        raw["taxonAttributes"] = [{"label": "React"}]
        job = map_job(raw)
        assert job is not None
        assert "React" in job.skills


class TestDetectLocationType:

    def test_remote_flag(self) -> None:
        assert _detect_location_type({"remoteLocation": True}) == LocationType.REMOTE

    def test_is_remote_flag(self) -> None:
        assert _detect_location_type({"isRemote": True}) == LocationType.REMOTE

    def test_remote_in_location_text(self) -> None:
        assert _detect_location_type({"formattedLocation": "Remote US"}) == LocationType.REMOTE

    def test_hybrid_in_location_text(self) -> None:
        assert _detect_location_type({"formattedLocation": "Hybrid - NYC"}) == LocationType.HYBRID

    def test_defaults_to_onsite(self) -> None:
        assert _detect_location_type({"formattedLocation": "New York, NY"}) == LocationType.ONSITE


class TestParseJobType:

    def test_fulltime_variants(self) -> None:
        for s in ("fulltime", "full-time", "full_time", "FULLTIME"):
            assert _parse_job_type(s) == JobType.FULL_TIME

    def test_unknown_defaults_to_fulltime(self) -> None:
        assert _parse_job_type("something_weird") == JobType.FULL_TIME


class TestParseDate:

    def test_iso_format(self) -> None:
        dt = _parse_date("2026-01-15")
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.tzinfo == timezone.utc

    def test_iso_with_time(self) -> None:
        dt = _parse_date("2026-01-15T10:30:00")
        assert dt.hour == 10

    def test_unparseable_returns_now(self) -> None:
        dt = _parse_date("3 days ago")
        assert dt.tzinfo == timezone.utc

    def test_none_returns_now(self) -> None:
        dt = _parse_date(None)
        assert dt is not None
