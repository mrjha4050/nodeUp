"""Tests for LinkedIn response mapper."""

from src.job_aggregator.providers.linkedin.mapper import map_job


class TestLinkedInMapper:

    def _raw_job(self, **overrides) -> dict:
        """Build a minimal valid LinkedIn raw job dict."""
        base = {
            "id": "12345",
            "title": "Software Engineer",
            "description": "Build great software",
            "company": {
                "name": "Acme Corp",
                "url": "https://acme.com",
                "industry": "Tech",
                "size": "51-200",
            },
            "location": "San Francisco, CA",
            "employmentType": "F",
            "experienceLevel": "3",
            "workRemoteAllowed": "2",
            "skills": ["Python", "AWS"],
            "applyUrl": "https://acme.com/apply",
            "listedAt": 1700000000000,
            "salary": {"min": 120000, "max": 180000, "currency": "USD", "period": "yearly"},
        }
        base.update(overrides)
        return base

    def test_valid_job_maps_correctly(self) -> None:
        job = map_job(self._raw_job())
        assert job is not None
        assert job.id == "linkedin_12345"
        assert job.title == "Software Engineer"
        assert job.company_info.name == "Acme Corp"
        assert job.salary_range.min == 120000
        assert job.skills == ["Python", "AWS"]

    def test_job_type_mapping(self) -> None:
        for code, expected in [("F", "full_time"), ("P", "part_time"), ("C", "contract")]:
            job = map_job(self._raw_job(employmentType=code))
            assert job is not None
            assert job.type.value == expected

    def test_experience_level_mapping(self) -> None:
        job = map_job(self._raw_job(experienceLevel="1"))
        assert job is not None
        assert job.experience_level.value == "entry"

    def test_remote_location_mapping(self) -> None:
        job = map_job(self._raw_job(workRemoteAllowed="2"))
        assert job is not None
        assert job.location_type.value == "remote"

    def test_missing_id_returns_none(self) -> None:
        assert map_job(self._raw_job(id="")) is None

    def test_missing_title_returns_none(self) -> None:
        assert map_job(self._raw_job(title="")) is None

    def test_missing_salary_defaults(self) -> None:
        raw = self._raw_job()
        del raw["salary"]
        job = map_job(raw)
        assert job is not None
        assert job.salary_range.min == 0
        assert job.salary_range.max == 0

    def test_missing_company_defaults(self) -> None:
        raw = self._raw_job()
        del raw["company"]
        job = map_job(raw)
        assert job is not None
        assert job.company_info.name == "Unknown"

    def test_missing_listed_at_defaults_to_now(self) -> None:
        raw = self._raw_job()
        del raw["listedAt"]
        job = map_job(raw)
        assert job is not None
        assert job.posted_at is not None

    def test_default_apply_url(self) -> None:
        raw = self._raw_job()
        del raw["applyUrl"]
        job = map_job(raw)
        assert job is not None
        assert "linkedin.com/jobs/view/12345" in str(job.application_url)
