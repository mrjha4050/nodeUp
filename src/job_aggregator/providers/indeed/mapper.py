"""Maps raw Indeed API responses into the common Job model.

This is the ONLY place that understands Indeed's data structures.
Everything else works with the domain models from models/job.py.
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

# Indeed uses human-readable strings for job types.
_JOB_TYPE_MAP: dict[str, JobType] = {
    "fulltime": JobType.FULL_TIME,
    "full-time": JobType.FULL_TIME,
    "full_time": JobType.FULL_TIME,
    "parttime": JobType.PART_TIME,
    "part-time": JobType.PART_TIME,
    "part_time": JobType.PART_TIME,
    "contract": JobType.CONTRACT,
    "internship": JobType.INTERNSHIP,
    "temporary": JobType.TEMPORARY,
}

_EXPERIENCE_MAP: dict[str, ExperienceLevel] = {
    "entry_level": ExperienceLevel.ENTRY,
    "entry level": ExperienceLevel.ENTRY,
    "mid_level": ExperienceLevel.MID,
    "mid level": ExperienceLevel.MID,
    "senior_level": ExperienceLevel.SENIOR,
    "senior level": ExperienceLevel.SENIOR,
    "senior": ExperienceLevel.SENIOR,
    "lead": ExperienceLevel.LEAD,
    "director": ExperienceLevel.DIRECTOR,
    "executive": ExperienceLevel.EXECUTIVE,
}


def map_job(raw: dict) -> Job | None:
    """Convert a single raw Indeed job dict into a domain Job.

    Returns None if required fields are missing, so one bad
    record never crashes an entire search.
    """
    try:
        job_key = str(raw.get("jobkey", "") or raw.get("id", ""))
        title = raw.get("jobtitle", "") or raw.get("title", "")
        if not job_key or not title:
            logger.warning("indeed_job_missing_required_fields", raw_id=raw.get("jobkey"))
            return None

        company = _parse_company(raw)
        salary = _parse_salary(raw)
        location_type = _detect_location_type(raw)
        posted_at = _parse_date(raw.get("date") or raw.get("formattedRelativeTime"))

        return Job(
            id=f"indeed_{job_key}",
            title=title,
            description=raw.get("snippet", "") or raw.get("description", ""),
            type=_parse_job_type(raw.get("jobType") or raw.get("type", "")),
            experience_level=_parse_experience(raw.get("experienceLevel", "")),
            location_type=location_type,
            location=raw.get("formattedLocation", "") or raw.get("location", "Not specified"),
            salary_range=salary,
            skills=_extract_skills(raw),
            company_info=company,
            posted_at=posted_at,
            application_url=raw.get("url", f"https://www.indeed.com/viewjob?jk={job_key}"),
            raw_data=raw,
        )
    except Exception:
        logger.exception("indeed_job_mapping_failed", raw_id=raw.get("jobkey"))
        return None


def _parse_company(raw: dict) -> CompanyInfo:
    """Extract company info from an Indeed job record."""
    company_name = raw.get("company", "") or raw.get("companyName", "Unknown")
    company_url = raw.get("companyUrl") or raw.get("company_url")

    return CompanyInfo(
        name=company_name,
        website=company_url or "https://www.indeed.com",
        industry=raw.get("industry", "Unknown"),
        size=raw.get("companySize", "Unknown"),
    )


def _parse_salary(raw: dict) -> SalaryRange:
    """Parse Indeed salary data into a SalaryRange."""
    salary_snippet = raw.get("salarySnippet") or {}
    salary_min = raw.get("salaryMin") or salary_snippet.get("min")
    salary_max = raw.get("salaryMax") or salary_snippet.get("max")
    currency = salary_snippet.get("currency", "USD")
    salary_type = salary_snippet.get("salaryType", "yearly")

    return SalaryRange(
        min=float(salary_min) if salary_min else 0,
        max=float(salary_max) if salary_max else 0,
        currency=currency,
        period=salary_type,
    )


def _parse_job_type(raw_type: str) -> JobType:
    """Map an Indeed job type string to the domain enum."""
    return _JOB_TYPE_MAP.get(raw_type.lower().strip(), JobType.FULL_TIME)


def _parse_experience(raw_level: str) -> ExperienceLevel:
    """Map an Indeed experience string to the domain enum."""
    return _EXPERIENCE_MAP.get(raw_level.lower().strip(), ExperienceLevel.MID)


def _detect_location_type(raw: dict) -> LocationType:
    """Detect remote/onsite/hybrid from Indeed's various location fields."""
    remote_flag = raw.get("remoteLocation", False) or raw.get("isRemote", False)
    if remote_flag:
        return LocationType.REMOTE

    location_text = (raw.get("formattedLocation", "") or "").lower()
    if "remote" in location_text:
        return LocationType.REMOTE
    if "hybrid" in location_text:
        return LocationType.HYBRID

    return LocationType.ONSITE


def _extract_skills(raw: dict) -> list[str]:
    """Pull skills/tags from Indeed's various attribute fields."""
    skills: list[str] = []

    if raw.get("skills"):
        skills.extend(raw["skills"])

    for attr in raw.get("attributes", []):
        if isinstance(attr, str):
            skills.append(attr)
        elif isinstance(attr, dict) and attr.get("label"):
            skills.append(attr["label"])

    if raw.get("taxonAttributes"):
        for taxon in raw["taxonAttributes"]:
            if isinstance(taxon, dict) and taxon.get("label"):
                skills.append(taxon["label"])

    return skills


def _parse_date(date_str: str | None) -> datetime:
    """Parse Indeed date strings into datetime.

    Indeed returns dates in various formats: ISO strings,
    relative strings like '3 days ago', or epoch timestamps.
    Falls back to now() if parsing fails.
    """
    if not date_str:
        return datetime.now(tz=timezone.utc)

    # Try ISO format first
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # If it's a relative string or unparseable, use current time
    return datetime.now(tz=timezone.utc)
