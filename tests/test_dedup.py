"""Unit tests for the deduplication service."""

from datetime import datetime, timezone

import pytest

from src.job_aggregator.models.job import (
    CompanyInfo,
    ExperienceLevel,
    Job,
    JobType,
    LocationType,
    SalaryRange,
)
from src.job_aggregator.services.dedup import (
    DedupStrategy,
    DeduplicationService,
    ExactMatchStrategy,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_job(
    id: str = "test_1",
    title: str = "Software Engineer",
    company: str = "Acme Corp",
    location: str = "New York, NY",
    description: str = "Build things",
) -> Job:
    """Create a Job with sensible defaults for testing."""
    return Job(
        id=id,
        title=title,
        description=description,
        type=JobType.FULL_TIME,
        experience_level=ExperienceLevel.MID,
        location_type=LocationType.ONSITE,
        location=location,
        salary_range=SalaryRange(min=100000, max=150000, currency="USD", period="yearly"),
        skills=["python", "aws"],
        company_info=CompanyInfo(
            name=company,
            website="https://example.com",
            industry="Tech",
            size="51-200",
        ),
        posted_at=datetime.now(tz=timezone.utc),
        application_url="https://example.com/apply",
        raw_data={},
    )


# ------------------------------------------------------------------
# ExactMatchStrategy tests
# ------------------------------------------------------------------

class TestExactMatchStrategy:

    def test_no_duplicates(self) -> None:
        """All unique jobs should pass through unchanged."""
        jobs = [
            _make_job(id="1", title="Engineer", company="A", location="NYC"),
            _make_job(id="2", title="Designer", company="B", location="LA"),
            _make_job(id="3", title="Manager", company="C", location="SF"),
        ]
        result = ExactMatchStrategy().deduplicate(jobs)
        assert len(result) == 3

    def test_exact_duplicates_removed(self) -> None:
        """Identical company+title+location should collapse to one."""
        jobs = [
            _make_job(id="linkedin_1", title="Engineer", company="Acme", location="NYC"),
            _make_job(id="indeed_1", title="Engineer", company="Acme", location="NYC"),
        ]
        result = ExactMatchStrategy().deduplicate(jobs)
        assert len(result) == 1
        assert result[0].id == "linkedin_1"  # first occurrence wins

    def test_case_insensitive(self) -> None:
        """Matching should be case-insensitive."""
        jobs = [
            _make_job(id="1", title="Software Engineer", company="ACME CORP", location="new york"),
            _make_job(id="2", title="software engineer", company="acme corp", location="New York"),
        ]
        result = ExactMatchStrategy().deduplicate(jobs)
        assert len(result) == 1

    def test_whitespace_normalized(self) -> None:
        """Leading/trailing whitespace should not create false uniqueness."""
        jobs = [
            _make_job(id="1", title="  Engineer  ", company=" Acme ", location=" NYC "),
            _make_job(id="2", title="Engineer", company="Acme", location="NYC"),
        ]
        result = ExactMatchStrategy().deduplicate(jobs)
        assert len(result) == 1

    def test_different_title_not_deduped(self) -> None:
        """Same company+location but different title should remain."""
        jobs = [
            _make_job(id="1", title="Frontend Engineer", company="Acme", location="NYC"),
            _make_job(id="2", title="Backend Engineer", company="Acme", location="NYC"),
        ]
        result = ExactMatchStrategy().deduplicate(jobs)
        assert len(result) == 2

    def test_different_company_not_deduped(self) -> None:
        """Same title+location but different company should remain."""
        jobs = [
            _make_job(id="1", title="Engineer", company="Acme", location="NYC"),
            _make_job(id="2", title="Engineer", company="Globex", location="NYC"),
        ]
        result = ExactMatchStrategy().deduplicate(jobs)
        assert len(result) == 2

    def test_different_location_not_deduped(self) -> None:
        """Same company+title but different location should remain."""
        jobs = [
            _make_job(id="1", title="Engineer", company="Acme", location="NYC"),
            _make_job(id="2", title="Engineer", company="Acme", location="SF"),
        ]
        result = ExactMatchStrategy().deduplicate(jobs)
        assert len(result) == 2

    def test_empty_list(self) -> None:
        """Empty input should return empty output."""
        assert ExactMatchStrategy().deduplicate([]) == []

    def test_single_job(self) -> None:
        """A single job should pass through."""
        jobs = [_make_job(id="1")]
        result = ExactMatchStrategy().deduplicate(jobs)
        assert len(result) == 1

    def test_multiple_duplicates_across_providers(self) -> None:
        """Same job from 3 providers should collapse to 1."""
        jobs = [
            _make_job(id="linkedin_1", title="Engineer", company="Acme", location="NYC"),
            _make_job(id="indeed_1", title="Engineer", company="Acme", location="NYC"),
            _make_job(id="glassdoor_1", title="Engineer", company="Acme", location="NYC"),
        ]
        result = ExactMatchStrategy().deduplicate(jobs)
        assert len(result) == 1
        assert result[0].id == "linkedin_1"

    def test_preserves_order(self) -> None:
        """First occurrence should always win."""
        jobs = [
            _make_job(id="indeed_1", title="Engineer", company="Acme", location="NYC"),
            _make_job(id="linkedin_1", title="Engineer", company="Acme", location="NYC"),
        ]
        result = ExactMatchStrategy().deduplicate(jobs)
        assert result[0].id == "indeed_1"


# ------------------------------------------------------------------
# DeduplicationService tests
# ------------------------------------------------------------------

class TestDeduplicationService:

    def test_default_strategy(self) -> None:
        """Service should use ExactMatchStrategy by default."""
        service = DeduplicationService()
        assert service.strategy_name == "ExactMatchStrategy"

    def test_custom_strategy(self) -> None:
        """Service should accept a custom strategy."""

        class NoOpStrategy(DedupStrategy):
            def deduplicate(self, jobs: list[Job]) -> list[Job]:
                return jobs

        service = DeduplicationService(strategy=NoOpStrategy())
        assert service.strategy_name == "NoOpStrategy"

        jobs = [
            _make_job(id="1", title="Engineer", company="Acme", location="NYC"),
            _make_job(id="2", title="Engineer", company="Acme", location="NYC"),
        ]
        result = service.deduplicate(jobs)
        assert len(result) == 2  # NoOp keeps everything

    def test_service_delegates_to_strategy(self) -> None:
        """Service.deduplicate should call the strategy's deduplicate."""
        service = DeduplicationService()
        jobs = [
            _make_job(id="linkedin_1", title="Engineer", company="Acme", location="NYC"),
            _make_job(id="indeed_1", title="Engineer", company="Acme", location="NYC"),
            _make_job(id="indeed_2", title="Designer", company="Globex", location="LA"),
        ]
        result = service.deduplicate(jobs)
        assert len(result) == 2

    def test_service_with_no_jobs(self) -> None:
        """Empty input should work without errors."""
        service = DeduplicationService()
        assert service.deduplicate([]) == []
