"""Maps raw LinkedIn API responses into the common Job model.

This is the ONLY place that understands LinkedIn's data structures.
Everything else in the application works with the domain models.
"""

from datetime import datetime, timezone

from src.job_aggregator.core import get_logger
from src.job_aggregator.models.job import (
    CompanyInfo,
    ExperienceLevel,
    Job,
    JobType,
    LocationType,
    SalaryRange,
)

logger = get_logger(__name__)

# LinkedIn uses specific string codes for these fields.
# These maps translate them into our domain enums.
_JOB_TYPE_MAP: dict[str, JobType] = {
    "F": JobType.FULL_TIME,
    "P": JobType.PART_TIME,
    "C": JobType.CONTRACT,
    "I": JobType.INTERNSHIP,
    "T": JobType.TEMPORARY,
}

_EXPERIENCE_MAP: dict[str, ExperienceLevel] = {
    "1": ExperienceLevel.ENTRY,
    "2": ExperienceLevel.MID,
    "3": ExperienceLevel.SENIOR,
    "4": ExperienceLevel.LEAD,
    "5": ExperienceLevel.DIRECTOR,
    "6": ExperienceLevel.EXECUTIVE,
}

_LOCATION_TYPE_MAP: dict[str, LocationType] = {
    "1": LocationType.ONSITE,
    "2": LocationType.REMOTE,
    "3": LocationType.HYBRID,
}


def map_job(raw: dict) -> Job | None:
    """Convert a single raw LinkedIn job dict into a domain Job.

    Returns None if the raw data is missing required fields,
    so one bad record never crashes a whole search.
    """
    try:
        job_id = str(raw.get("id", ""))
        title = raw.get("title", "")
        if not job_id or not title:
            logger.warning("linkedin_job_missing_required_fields", raw_id=raw.get("id"))
            return None

        company_raw = raw.get("company", {})
        company = CompanyInfo(
            name=company_raw.get("name", "Unknown"),
            website=company_raw.get("url", "https://linkedin.com"),
            industry=company_raw.get("industry", "Unknown"),
            size=company_raw.get("size", "Unknown"),
        )

        salary = _parse_salary(raw.get("salary"))
        posted_at = _parse_timestamp(raw.get("listedAt"))

        return Job(
            id=f"linkedin_{job_id}",
            title=title,
            description=raw.get("description", ""),
            type=_JOB_TYPE_MAP.get(str(raw.get("employmentType", "")), JobType.FULL_TIME),
            experience_level=_EXPERIENCE_MAP.get(
                str(raw.get("experienceLevel", "")), ExperienceLevel.MID
            ),
            location_type=_LOCATION_TYPE_MAP.get(
                str(raw.get("workRemoteAllowed", "")), LocationType.ONSITE
            ),
            location=raw.get("location", "Not specified"),
            salary_range=salary,
            skills=raw.get("skills", []),
            company_info=company,
            posted_at=posted_at,
            application_url=raw.get("applyUrl", f"https://www.linkedin.com/jobs/view/{job_id}"),
            raw_data=raw,
        )
    except Exception:
        logger.exception("linkedin_job_mapping_failed", raw_id=raw.get("id"))
        return None


def _parse_salary(salary_raw: dict | None) -> SalaryRange:
    """Parse LinkedIn salary data into a SalaryRange, with safe defaults."""
    if not salary_raw:
        return SalaryRange(min=0, max=0, currency="USD", period="yearly")

    return SalaryRange(
        min=float(salary_raw.get("min", 0)),
        max=float(salary_raw.get("max", 0)),
        currency=salary_raw.get("currency", "USD"),
        period=salary_raw.get("period", "yearly"),
    )


def _parse_timestamp(epoch_ms: int | None) -> datetime:
    """Convert a millisecond epoch timestamp to a datetime."""
    if not epoch_ms:
        return datetime.now(tz=timezone.utc)
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
