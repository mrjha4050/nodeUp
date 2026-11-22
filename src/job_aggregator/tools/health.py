"""Health and config tools for the MCP server."""

import httpx
from mcp.server.fastmcp import FastMCP

from src.job_aggregator.config import get_settings
from src.job_aggregator.core import get_logger
from src.job_aggregator.models.health import HealthStatus
from src.job_aggregator.providers.registry import ProviderRegistry

logger = get_logger(__name__)

_GITHUB_REPO = "mrjha4050/nodeUp"
_LATEST_RELEASE_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"


async def _check_for_update(current_version: str) -> dict | None:
    """Compare current_version against the latest GitHub release tag.

    Returns None on any failure (offline, rate-limited, malformed tag) so
    callers can degrade gracefully instead of failing the whole tool call.
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                _LATEST_RELEASE_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "job-aggregator-mcp",
                },
            )
            response.raise_for_status()
            latest_tag = response.json()["tag_name"].lstrip("v")

        current = tuple(int(p) for p in current_version.split(".")[:3])
        latest = tuple(int(p) for p in latest_tag.split(".")[:3])
    except Exception:
        logger.warning("update_check_failed")
        return None

    return {
        "current_version": current_version,
        "latest_version": latest_tag,
        "update_available": latest > current,
        "release_url": f"https://github.com/{_GITHUB_REPO}/releases/tag/v{latest_tag}",
    }


def register_health_tools(mcp: FastMCP, registry: ProviderRegistry) -> None:
    """Register health-related tools on the MCP server."""

    @mcp.tool()
    async def health_check() -> dict:
        """Check the health and status of the Job Aggregator MCP server.

        Returns server status, version, environment, and provider availability.
        Use this to verify the server is running and which providers are online.
        """
        settings = get_settings()
        logger.info("health_check_requested")

        try:
            provider_health = await registry.health_check_all()

            status = HealthStatus(
                status="healthy",
                server_name=settings.app_name,
                version=settings.version,
                environment=settings.app_env.value,
                providers={
                    name: "up" if ok else "down"
                    for name, ok in provider_health.items()
                },
            )

            logger.info("health_check_ok", version=settings.version)
            result = status.model_dump(mode="json")
            result["update_check"] = await _check_for_update(settings.version)
            return result

        except Exception as exc:
            logger.exception("health_check_failed")
            return {
                "status": "unhealthy",
                "error": str(exc),
            }
