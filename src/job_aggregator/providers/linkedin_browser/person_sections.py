"""LinkedIn profile section names and URL path mapping."""

from __future__ import annotations

VALID_PERSON_SECTIONS = frozenset({
    "experience",
    "education",
    "interests",
    "honors",
    "languages",
    "certifications",
    "skills",
    "projects",
    "contact_info",
    "posts",
})

# LinkedIn detail-page path segments relative to /in/{username}/
SECTION_PATHS: dict[str, str] = {
    "experience": "details/experience",
    "education": "details/education",
    "interests": "details/interests",
    "honors": "details/honors",
    "languages": "details/languages",
    "certifications": "details/certifications",
    "skills": "details/skills",
    "projects": "details/projects",
    "contact_info": "overlay/contact-info",
    "posts": "recent-activity/all",
}

DEFAULT_DETAIL_SCROLLS = 5
DEFAULT_POSTS_SCROLLS = 10


def normalize_username(username: str) -> str:
    """Strip URL fragments and return a bare LinkedIn vanity username."""
    value = username.strip().strip("/")
    if "/in/" in value:
        value = value.split("/in/", 1)[1]
    value = value.split("?", 1)[0].strip("/")
    if not value:
        raise ValueError("linkedin_username is required")
    return value


def parse_person_sections(sections: str | None) -> tuple[list[str], list[str]]:
    """Parse a comma-separated section list into known and unknown names."""
    if not sections or not sections.strip():
        return [], []

    requested: list[str] = []
    unknown: list[str] = []
    for raw in sections.split(","):
        name = raw.strip().lower()
        if not name:
            continue
        if name in VALID_PERSON_SECTIONS:
            if name not in requested:
                requested.append(name)
        elif name not in unknown:
            unknown.append(name)
    return requested, unknown


def profile_url(username: str) -> str:
    """Build the canonical profile URL for a username."""
    return f"https://www.linkedin.com/in/{normalize_username(username)}/"


def section_url(username: str, section: str) -> str:
    """Build a profile section URL."""
    base = profile_url(username).rstrip("/")
    path = SECTION_PATHS[section]
    if section == "contact_info":
        return f"{base}/{path}/"
    return f"{base}/{path}/"
