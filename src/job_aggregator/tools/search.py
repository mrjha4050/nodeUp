"""MCP tools for job search, job details, profile search, and connections.

These are the tools exposed to MCP clients (e.g. Claude Desktop).
They validate input, delegate to the service layer, and return
structured JSON responses. No business logic lives here.
"""

from pydantic import ValidationError

from mcp.server.fastmcp import FastMCP

from src.job_aggregator.core import get_logger
from src.job_aggregator.models.search import SearchRequest
from src.job_aggregator.providers.linkedin_browser import LinkedInBrowserProvider
from src.job_aggregator.services.aggregator import JobAggregatorService

logger = get_logger(__name__)


def register_search_tools(mcp: FastMCP, service: JobAggregatorService) -> None:
    """Register search-related tools on the MCP server."""

    @mcp.tool()
    async def search_jobs(
        query: str,
        location: str | None = None,
        job_type: str | None = None,
        experience_level: str | None = None,
        location_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        skills: list[str] | None = None,
    ) -> dict:
        """Search for jobs across all registered providers.

        Searches LinkedIn, Indeed, and any other registered provider
        concurrently, deduplicates results, and returns a unified list.

        Args:
            query: Search keywords, e.g. "python backend engineer".
            location: Location filter, e.g. "New York" or "Remote".
            job_type: Filter by type: full_time, part_time, contract, internship, temporary.
            experience_level: Filter by level: entry, mid, senior, lead, director, executive.
            location_type: Filter: onsite, remote, hybrid.
            limit: Max number of results (default 25).
            offset: Pagination offset (default 0).
            skills: Filter by required skills, e.g. ["python", "aws"].
        """
        logger.info("tool_search_jobs_called", query=query, location=location)

        try:
            request = SearchRequest(
                query=query,
                location=location,
                job_type=job_type,
                experience_level=experience_level,
                location_type=location_type,
                limited_results=limit,
                offset=offset,
                skills=skills,
            )
        except ValidationError as exc:
            logger.warning("tool_search_jobs_validation_error", error=str(exc))
            return {
                "success": False,
                "error": "Validation error",
                "details": exc.errors(),
            }

        try:
            response = await service.search(request)
            return response.model_dump(mode="json")
        except Exception as exc:
            logger.exception("tool_search_jobs_failed", query=query)
            return {
                "success": False,
                "error": f"Search failed: {exc}",
            }

    @mcp.tool()
    async def get_job_details(job_id: str) -> dict:
        """Get full details for a specific job by its ID.

        The job ID includes the provider prefix, e.g. "linkedin_12345"
        or "indeed_abc". The request is routed to the correct provider
        automatically.

        Args:
            job_id: The full job ID including provider prefix.
        """
        logger.info("tool_get_job_details_called", job_id=job_id)

        if not job_id or not job_id.strip():
            return {
                "success": False,
                "error": "job_id is required and cannot be empty",
            }

        try:
            job = await service.get_job_details(job_id.strip())

            if job is None:
                return {
                    "success": False,
                    "error": f"Job '{job_id}' not found",
                }

            return {
                "success": True,
                "job": job.model_dump(mode="json"),
            }
        except Exception as exc:
            logger.exception("tool_get_job_details_failed", job_id=job_id)
            return {
                "success": False,
                "error": f"Failed to fetch job details: {exc}",
            }

    @mcp.tool()
    async def search_profiles(
        query: str,
        location: str | None = None,
        network: str | None = None,
        limit: int = 10,
    ) -> dict:
        """Search LinkedIn for people profiles.

        Uses the browser-based LinkedIn provider to find people.

        Args:
            query: Search keywords, e.g. "machine learning engineer" or a person's name.
            location: Filter by location, e.g. "San Francisco".
            network: Connection degree: "first", "second", or "third".
            limit: Max number of profiles to return (default 10).
        """
        logger.info("tool_search_profiles_called", query=query, location=location)

        linkedin_browser = service.registry.get("linkedin_browser")
        if not linkedin_browser or not isinstance(linkedin_browser, LinkedInBrowserProvider):
            return {"success": False, "error": "LinkedIn browser provider not available"}

        return await linkedin_browser.search_profiles(
            keywords=query,
            location=location,
            network=network,
            limit=limit,
        )

    @mcp.tool()
    async def send_connection(
        profile_url: str,
        note: str = "",
    ) -> dict:
        """Send a LinkedIn connection request with an optional personalized note.

        Uses the browser-based LinkedIn provider.

        Args:
            profile_url: Full LinkedIn profile URL, e.g. "https://www.linkedin.com/in/username/".
            note: Optional personalized message to include (max 300 characters).
        """
        logger.info("tool_send_connection_called", profile_url=profile_url)

        if not profile_url or "linkedin.com/in/" not in profile_url:
            return {"success": False, "message": "Invalid LinkedIn profile URL"}

        linkedin_browser = service.registry.get("linkedin_browser")
        if not linkedin_browser or not isinstance(linkedin_browser, LinkedInBrowserProvider):
            return {"success": False, "message": "LinkedIn browser provider not available"}

        return await linkedin_browser.send_connection(
            profile_url=profile_url,
            note=note,
        )
