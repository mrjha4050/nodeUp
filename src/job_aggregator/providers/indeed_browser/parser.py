"""Parses raw scraped text into domain Job models.

This is the browser equivalent of the Indeed API mapper module.
It takes raw visible text from Indeed pages and extracts
structured data using regex patterns.

Indeed job cards typically render as:
    Line 0: Job title
    Line 1: Company name
    Line 2: Location
    Line 3: Salary (if available)
    Line 4+: Snippet / description
    Last lines: "Posted X days ago" / "Active X days ago"
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
    """Parse a single scraped Indeed job card into a domain Job.

    Args:
        card: dict with 'text', 'job_key', 'href' from the scraper.

    Returns None if the card can't be meaningfully parsed.
    """
    text = card.get("text", "")
    job_key = card.get("job_key")

    if not text or not job_key:
        return None

    try:
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        if len(lines) < 2:
            return None

        title = lines[0]
        company_name = lines[1] if len(lines) > 1 else "Unknown"

        # Indeed sometimes has a rating next to the company name (e.g., "Company 3.5")
        company_name = re.sub(r"\s+\d+\.\d+$", "", company_name)

        # Indeed inserts response-time badges like "Often replies in 1 day"
        # If company looks like a badge, use the next line
        if re.match(r"^(Often|Usually|Typically)\s+(replies|responds)", company_name, re.IGNORECASE):
            company_name = lines[2] if len(lines) > 2 else "Unknown"
            lines = [lines[0]] + lines[2:]  # remove the badge line

        location = _extract_location(lines)
        salary = _extract_salary(text)
        job_type = _detect_job_type(text)
        location_type = _detect_location_type(text, location)
        posted_at = _extract_posted_time(text)

        # Build application URL
        href = card.get("href") or ""
        if href.startswith("/"):
            application_url = f"https://www.indeed.com{href}"
        elif href.startswith("http"):
            application_url = href
        else:
            application_url = f"https://www.indeed.com/viewjob?jk={job_key}"

        return Job(
            id=f"indeed_browser_{job_key}",
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
                website=f"https://www.indeed.com/cmp/{_slugify(company_name)}",
                industry="Unknown",
                size="Unknown",
            ),
            posted_at=posted_at,
            application_url=application_url,
            raw_data=card,
        )
    except Exception:
        logger.exception("indeed_browser_parser_card_failed", job_key=job_key)
        return None


def parse_job_detail(detail: dict, job_key: str) -> Job | None:
    """Parse a scraped Indeed job detail page into a domain Job.

    Indeed detail pages typically show:
        - Job title prominently
        - Company name and location
        - Salary info (if available)
        - Full job description
        - Job details (type, shift, benefits)
    """
    text = detail.get("text", "")
    if not text:
        return None

    clean_key = job_key.removeprefix("indeed_browser_")

    try:
        # Strip navigation/header noise from detail page
        # Look for the actual job content starting point
        content_start = 0
        for marker in ["Full job description", "Job Description", "full job description"]:
            idx = text.find(marker)
            if idx >= 0:
                content_start = idx
                break

        # Extract title and company from the text before the description
        # or from the whole text if no marker found
        header_text = text[:content_start] if content_start > 0 else text
        lines = [line.strip() for line in header_text.strip().split("\n") if line.strip()]

        # Filter out navigation noise lines
        noise_keywords = {"home", "company reviews", "find salaries", "sign in",
                          "post job", "start of main content", "employers"}
        lines = [l for l in lines if l.lower() not in noise_keywords
                 and not l.startswith("&nbsp")]

        if len(lines) < 2:
            return None

        title = lines[0]
        company_name = lines[1] if len(lines) > 1 else "Unknown"
        company_name = re.sub(r"\s+\d+\.\d+$", "", company_name)

        # On detail pages, sometimes there's a rating and reviews count
        # "Company Name 3.8  1,234 reviews"
        company_name = re.sub(r"\s+\d[\d,]*\s+reviews?$", "", company_name, flags=re.IGNORECASE)

        location = _extract_location(lines)
        salary = _extract_salary(text)
        skills = _extract_skills(text)
        description = _extract_description(text)

        return Job(
            id=f"indeed_browser_{clean_key}",
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
                website=f"https://www.indeed.com/cmp/{_slugify(company_name)}",
                industry="Unknown",
                size="Unknown",
            ),
            posted_at=_extract_posted_time(text),
            application_url=f"https://www.indeed.com/viewjob?jk={clean_key}",
            raw_data=detail,
        )
    except Exception:
        logger.exception("indeed_browser_parser_detail_failed", job_key=job_key)
        return None


# ------------------------------------------------------------------
# Extraction helpers
# ------------------------------------------------------------------

def _extract_location(lines: list[str]) -> str:
    """Find the location line from card lines.

    Indeed location lines look like:
        "New York, NY"
        "San Francisco, CA 94105"
        "Remote"
        "Hybrid remote in Austin, TX"
    """
    for line in lines[2:6]:
        # "City, State" pattern
        if re.match(r"^[A-Z][a-zA-Z\s.]+,\s*[A-Z]{2}(?:\s+\d{5})?$", line):
            return line.strip()
        # "Remote" or "Hybrid remote in ..."
        if re.match(r"^(?:Remote|Hybrid remote)", line, re.IGNORECASE):
            return line.strip()
        # "City, State ZIP" with more flexible pattern
        if re.match(r"^[A-Za-z\s.'-]+,\s*[A-Za-z\s]+", line) and len(line) < 60:
            # Avoid matching job descriptions or snippets
            if not any(word in line.lower() for word in ["experience", "salary", "apply", "posted", "ago"]):
                return line.strip()
    return lines[2] if len(lines) > 2 else "Not specified"


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
    """Extract salary range from text using common Indeed patterns.

    Indeed shows salaries like:
        "$80,000 - $120,000 a year"
        "$25 - $35 an hour"
        "From $60,000 a year"
        "Up to $100,000 a year"
    """
    # Range pattern: "$X - $Y a year/hour"
    range_match = re.search(
        r"\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*[-–]\s*\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:a|an|per)\s*(year|hour|month|week)",
        text,
        re.IGNORECASE,
    )
    if range_match:
        min_val = float(range_match.group(1).replace(",", ""))
        max_val = float(range_match.group(2).replace(",", ""))
        period = range_match.group(3).lower()
        return _normalize_salary(min_val, max_val, period)

    # Single value: "From $X a year" or "Up to $X a year"
    single_match = re.search(
        r"(?:From|Up to|Estimated)\s*\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:a|an|per)\s*(year|hour|month|week)",
        text,
        re.IGNORECASE,
    )
    if single_match:
        val = float(single_match.group(1).replace(",", ""))
        period = single_match.group(2).lower()
        return _normalize_salary(val, val, period)

    return SalaryRange(min=0, max=0, currency="USD", period="yearly")


def _normalize_salary(min_val: float, max_val: float, period: str) -> SalaryRange:
    """Normalize salary to yearly USD."""
    multipliers = {"hour": 2080, "week": 52, "month": 12, "year": 1}
    mult = multipliers.get(period, 1)
    return SalaryRange(
        min=min_val * mult,
        max=max_val * mult,
        currency="USD",
        period="yearly",
    )


def _extract_posted_time(text: str) -> datetime:
    """Parse relative time strings like 'Posted 2 days ago' into datetime."""
    match = re.search(
        r"(?:Posted|Active)\s+(\d+)\s+(minute|hour|day|week|month)s?\s+ago",
        text,
        re.IGNORECASE,
    )
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

    # Indeed also uses "Just posted" or "Today"
    if re.search(r"just posted|today", text, re.IGNORECASE):
        return datetime.now(tz=timezone.utc)

    return datetime.now(tz=timezone.utc)


def _extract_skills(text: str) -> list[str]:
    """Extract skills from job detail text."""
    skills = []
    skills_match = re.search(
        r"(?:skills|requirements|qualifications)[:\s]*\n((?:.*\n)*?)(?:\n\n|\Z)",
        text,
        re.IGNORECASE,
    )
    if skills_match:
        section = skills_match.group(1)
        for line in section.split("\n"):
            line = line.strip().lstrip("•·-–—*▪ ")
            if line and len(line) < 80:
                skills.append(line)
    return skills[:20]


def _extract_description(text: str) -> str:
    """Extract the job description section from detail page text."""
    markers = ["Full job description", "Job Description", "Description", "What you'll do"]
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
