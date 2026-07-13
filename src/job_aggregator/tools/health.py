"""Health and config tools for the MCP server."""

from mcp.server.fastmcp import FastMCP

from src.job_aggregator.config import get_settings
from src.job_aggregator.core import get_logger
from src.job_aggregator.models.health import HealthStatus
from src.job_aggregator.providers.registry import ProviderRegistry

logger = get_logger(__name__)


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
            return status.model_dump(mode="json")

        except Exception as exc:
            logger.exception("health_check_failed")
            return {
                "status": "unhealthy",
                "error": str(exc),
            }

    @mcp.tool()
    async def get_server_config() -> dict:
        """Return the current server configuration (non-sensitive fields only).

        Useful for debugging connection and environment issues.
        """
        settings = get_settings()
        logger.info("config_requested")

        return {
            "app_name": settings.app_name,
            "environment": settings.app_env.value,
            "log_level": settings.log_level,
            "version": settings.version,
            "registered_providers": registry.list_names(),
        }
