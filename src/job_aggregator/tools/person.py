"""MCP tools for LinkedIn person/profile scraping and actions."""

from mcp.server.fastmcp import FastMCP

from src.job_aggregator.core import get_logger
from src.job_aggregator.providers.linkedin_browser import LinkedInBrowserProvider
from src.job_aggregator.providers.registry import ProviderRegistry

logger = get_logger(__name__)


def _get_linkedin_provider(registry: ProviderRegistry) -> LinkedInBrowserProvider | None:
    provider = registry.get("linkedin_browser")
    if isinstance(provider, LinkedInBrowserProvider):
        return provider
    return None


def register_person_tools(mcp: FastMCP, registry: ProviderRegistry) -> None:
    """Register LinkedIn person-related tools on the MCP server."""

    @mcp.tool()
    async def get_person_profile(
        linkedin_username: str,
        sections: str | None = None,
        max_scrolls: int | None = None,
    ) -> dict:
        """Get a specific person's LinkedIn profile.

        Args:
            linkedin_username: LinkedIn username (e.g., "stickerdaniel", "williamhgates")
            sections: Comma-separated extra sections to scrape. The main profile page
                is always included. Available sections: experience, education,
                interests, honors, languages, certifications, skills, projects,
                contact_info, posts.
            max_scrolls: Maximum pagination attempts per section. On detail sections
                this is the max number of "Show more" clicks. On posts it is the max
                scroll iterations. Default uses 5 for detail sections and 10 for posts.
        """
        logger.info(
            "tool_get_person_profile_called",
            linkedin_username=linkedin_username,
            sections=sections,
        )

        provider = _get_linkedin_provider(registry)
        if provider is None:
            return {"success": False, "error": "LinkedIn browser provider not available"}

        if max_scrolls is not None and not 1 <= max_scrolls <= 50:
            return {
                "success": False,
                "error": "max_scrolls must be between 1 and 50",
            }

        return await provider.get_person_profile(
            linkedin_username=linkedin_username,
            sections=sections,
            max_scrolls=max_scrolls,
        )

    @mcp.tool()
    async def search_people(
        keywords: str,
        location: str | None = None,
        network: list[str] | None = None,
        current_company: str | None = None,
    ) -> dict:
        """Search for people on LinkedIn.

        Args:
            keywords: Search keywords (e.g., "software engineer", "recruiter at Google")
            location: Optional location filter (e.g., "New York", "Remote")
            network: Optional connection-degree filter. Each element is one of
                "F" (1st-degree), "S" (2nd-degree), "O" (3rd-degree and beyond).
            current_company: Optional current-employer filter using LinkedIn's
                numeric company URN id (e.g. "1115").
        """
        logger.info(
            "tool_search_people_called",
            keywords=keywords,
            location=location,
            network=network,
            current_company=current_company,
        )

        provider = _get_linkedin_provider(registry)
        if provider is None:
            return {"success": False, "error": "LinkedIn browser provider not available"}

        return await provider.search_people(
            keywords=keywords,
            location=location,
            network=network,
            current_company=current_company,
        )

    @mcp.tool()
    async def connect_with_person(
        linkedin_username: str,
        note: str | None = None,
    ) -> dict:
        """Send a LinkedIn connection request or accept an incoming one.

        Args:
            linkedin_username: LinkedIn username (e.g., "stickerdaniel", "williamhgates")
            note: Optional note to include with the invitation (max 300 characters)
        """
        logger.info(
            "tool_connect_with_person_called",
            linkedin_username=linkedin_username,
            has_note=note is not None,
        )

        provider = _get_linkedin_provider(registry)
        if provider is None:
            return {
                "success": False,
                "status": "unavailable",
                "message": "LinkedIn browser provider not available",
            }

        if note and len(note) > 300:
            return {
                "success": False,
                "status": "unavailable",
                "message": "Connection notes must be 300 characters or fewer",
            }

        return await provider.connect_with_person(
            linkedin_username=linkedin_username,
            note=note,
        )

    @mcp.tool()
    async def get_sidebar_profiles(linkedin_username: str) -> dict:
        """Get profile links from sidebar recommendation sections on a LinkedIn profile page.

        Args:
            linkedin_username: LinkedIn username of the profile page to scrape
        """
        logger.info(
            "tool_get_sidebar_profiles_called",
            linkedin_username=linkedin_username,
        )

        provider = _get_linkedin_provider(registry)
        if provider is None:
            return {"success": False, "error": "LinkedIn browser provider not available"}

        return await provider.get_sidebar_profiles(linkedin_username)

    @mcp.tool()
    async def get_my_profile(
        sections: str | None = None,
        max_scrolls: int | None = None,
    ) -> dict:
        """Get the authenticated user's own LinkedIn profile.

        Navigates to /in/me/ and resolves the redirect to obtain the real
        username before scraping.

        Args:
            sections: Comma-separated extra sections to scrape (same options as
                get_person_profile).
            max_scrolls: Maximum pagination attempts per section (same as
                get_person_profile).
        """
        logger.info("tool_get_my_profile_called", sections=sections)

        provider = _get_linkedin_provider(registry)
        if provider is None:
            return {"success": False, "error": "LinkedIn browser provider not available"}

        if max_scrolls is not None and not 1 <= max_scrolls <= 50:
            return {
                "success": False,
                "error": "max_scrolls must be between 1 and 50",
            }

        return await provider.get_my_profile(
            sections=sections,
            max_scrolls=max_scrolls,
        )
