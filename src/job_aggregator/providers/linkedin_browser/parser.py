"""Parses raw scraped text into domain Job models.

This is the browser equivalent of the API mapper modules.
It takes raw visible text from LinkedIn pages and extracts
structured data using regex patterns.

Because scraped text is inherently messy, the parser is
intentionally lenient — it extracts what it can and uses
sensible defaults for the rest.
"""

import re
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


def parse_job_card(card: dict) -> Job | None:
    """Parse a single scraped job card into a domain Job.

    Args:
        card: dict with 'text', 'job_id', 'href' from the scraper.

    Returns None if the card can't be meaningfully parsed.
    """
    text = card.get("text", "")
    job_id = card.get("job_id")

    if not text or not job_id:
        return None

    try:
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        if len(lines) < 2:
            return None

        # LinkedIn duplicates the job title on the first two lines of a card.
        # Detect this and skip the duplicate to find the real company name.
        title = lines[0]
        if len(lines) > 2 and lines[1] == lines[0]:
            # lines[0] = title, lines[1] = title (duplicate), lines[2] = company
            company_name = lines[2] if len(lines) > 2 else "Unknown"
            remaining_lines = lines[2:]
        else:
            company_name = lines[1]
            remaining_lines = lines[1:]

        location = _extract_location(remaining_lines)
        job_type = _detect_job_type(text)
        location_type = _detect_location_type(text, location)
        salary = _extract_salary(text)
        posted_at = _extract_posted_time(text)

        # Build absolute URL from href (scraped hrefs are often relative)
        href = card.get("href") or ""
        if href.startswith("/"):
            application_url = f"https://www.linkedin.com{href}"
        elif href.startswith("http"):
            application_url = href
        else:
            application_url = f"https://www.linkedin.com/jobs/view/{job_id}"

        return Job(
            id=f"linkedin_browser_{job_id}",
            title=title,
            description=text,
            type=job_type,
            experience_level=_detect_experience_level(text),
            location_type=location_type,
            location=location,
            salary_range=salary,
            skills=[],
            company_info=CompanyInfo(
                name=company_name,
                website=f"https://www.linkedin.com/company/{_slugify(company_name)}",
                industry="Unknown",
                size="Unknown",
            ),
            posted_at=posted_at,
            application_url=application_url,
            raw_data=card,
        )
    except Exception:
        logger.exception("browser_parser_card_failed", job_id=job_id)
        return None


def parse_job_detail(detail: dict, job_id: str) -> Job | None:
    """Parse a scraped job detail page into a domain Job.

    The detail page has richer text, so we can extract more fields.

    LinkedIn detail pages render as:
        Line 0: Company name
        Line 1: Job title
        Line 2: Location · time · applicants
    This is REVERSED from search cards (title first, then company).
    """
    text = detail.get("text", "")
    if not text:
        return None

    clean_id = job_id.removeprefix("linkedin_browser_")

    try:
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        if len(lines) < 2:
            return None

        # Detail page layout: company (line 0), title (line 1), location (line 2)
        # Detect detail page by checking if line 2 has location markers (·, ago, applicants)
        if len(lines) > 2 and re.search(r"·|ago|applicant", lines[2], re.IGNORECASE):
            company_name = lines[0]
            title = lines[1]
            remaining_lines = lines[2:]
        elif len(lines) > 2 and lines[1] == lines[0]:
            # Duplicate title pattern
            title = lines[0]
            company_name = lines[2]
            remaining_lines = lines[2:]
        else:
            title = lines[0]
            company_name = lines[1]
            remaining_lines = lines[1:]

        location = _extract_location(remaining_lines)
        salary = _extract_salary(text)
        skills = _extract_skills(text)
        description = _extract_description(text)

        return Job(
            id=f"linkedin_browser_{clean_id}",
            title=title,
            description=description or text,
            type=_detect_job_type(text),
            experience_level=_detect_experience_level(text),
            location_type=_detect_location_type(text, location),
            location=location,
            salary_range=salary,
            skills=skills,
            company_info=CompanyInfo(
                name=company_name,
                website=f"https://www.linkedin.com/company/{_slugify(company_name)}",
                industry="Unknown",
                size="Unknown",
            ),
            posted_at=_extract_posted_time(text),
            application_url=f"https://www.linkedin.com/jobs/view/{clean_id}",
            raw_data=detail,
        )
    except Exception:
        logger.exception("browser_parser_detail_failed", job_id=job_id)
        return None


# ------------------------------------------------------------------
# Extraction helpers
# ------------------------------------------------------------------

def _extract_location(lines: list[str]) -> str:
    """Find the location line from remaining card lines.

    LinkedIn location lines look like:
        "San Francisco, CA (Remote)"
        "United States (On-site)"
        "New York, NY"
        "Remote"
    """
    location_patterns = [
        r"\(On-site\)|\(Remote\)|\(Hybrid\)",  # LinkedIn location type suffix
        r"^.+,\s*.+$",  # "City, State" or "City, Country"
        r"^Remote$",
    ]
    for line in lines[1:5]:
        for pattern in location_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return line
    return lines[1] if len(lines) > 1 else "Not specified"


def _detect_job_type(text: str) -> JobType:
    """Detect job type from visible text."""
    text_lower = text.lower()
    if "part-time" in text_lower or "part time" in text_lower:
        return JobType.PART_TIME
    if "contract" in text_lower:
        return JobType.CONTRACT
    if "internship" in text_lower or "intern " in text_lower:
        return JobType.INTERNSHIP
    if "temporary" in text_lower or "temp " in text_lower:
        return JobType.TEMPORARY
    return JobType.FULL_TIME


def _detect_experience_level(text: str) -> ExperienceLevel:
    """Detect experience level from visible text."""
    text_lower = text.lower()
    if "director" in text_lower:
        return ExperienceLevel.DIRECTOR
    if "executive" in text_lower or "vp " in text_lower or "c-level" in text_lower:
        return ExperienceLevel.EXECUTIVE
    if "lead" in text_lower or "principal" in text_lower or "staff" in text_lower:
        return ExperienceLevel.LEAD
    if "senior" in text_lower or "sr." in text_lower or "sr " in text_lower:
        return ExperienceLevel.SENIOR
    if "entry" in text_lower or "junior" in text_lower or "jr." in text_lower:
        return ExperienceLevel.ENTRY
    return ExperienceLevel.MID


def _detect_location_type(text: str, location: str) -> LocationType:
    """Detect location type from text and location string."""
    combined = f"{text} {location}".lower()
    if "hybrid" in combined:
        return LocationType.HYBRID
    if "remote" in combined:
        return LocationType.REMOTE
    return LocationType.ONSITE


def _extract_salary(text: str) -> SalaryRange:
    """Extract salary range from text using common patterns."""
    # Match patterns like "$100K - $150K", "$100,000 - $150,000/yr"
    patterns = [
        r"\$(\d{1,3}(?:,\d{3})*)\s*[-–]\s*\$(\d{1,3}(?:,\d{3})*)",
        r"\$(\d{2,3})K\s*[-–]\s*\$(\d{2,3})K",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            min_val = match.group(1).replace(",", "")
            max_val = match.group(2).replace(",", "")
            min_f = float(min_val)
            max_f = float(max_val)
            # If values are small (like 100, 150), they're in K
            if min_f < 1000:
                min_f *= 1000
                max_f *= 1000
            return SalaryRange(min=min_f, max=max_f, currency="USD", period="yearly")

    return SalaryRange(min=0, max=0, currency="USD", period="yearly")


def _extract_posted_time(text: str) -> datetime:
    """Parse relative time strings like '2 days ago' into datetime."""
    match = re.search(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", text, re.IGNORECASE)
    if match:
        value = int(match.group(1))
        unit = match.group(2).lower()
        now = datetime.now(tz=timezone.utc)
        from datetime import timedelta
        deltas = {
            "minute": timedelta(minutes=value),
            "hour": timedelta(hours=value),
            "day": timedelta(days=value),
            "week": timedelta(weeks=value),
            "month": timedelta(days=value * 30),
        }
        return now - deltas.get(unit, timedelta())
    return datetime.now(tz=timezone.utc)


def _extract_skills(text: str) -> list[str]:
    """Extract skills from job detail text by looking for common patterns."""
    skills = []
    # Look for a skills section
    skills_match = re.search(
        r"(?:skills|requirements|qualifications)[:\s]*\n((?:.*\n)*?)(?:\n\n|\Z)",
        text,
        re.IGNORECASE,
    )
    if skills_match:
        section = skills_match.group(1)
        # Extract bullet-pointed or line-separated items
        for line in section.split("\n"):
            line = line.strip().lstrip("•·-–—*▪ ")
            if line and len(line) < 80:
                skills.append(line)
    return skills[:20]


def _extract_description(text: str) -> str:
    """Extract the job description section from detail page text."""
    # Look for description start markers
    markers = ["About the job", "Job Description", "Description"]
    for marker in markers:
        idx = text.find(marker)
        if idx >= 0:
            return text[idx:]
    return text


def _slugify(name: str) -> str:
    """Convert a company name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug
