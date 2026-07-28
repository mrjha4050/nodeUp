"""FastMCP server entrypoint.

Creates the server, wires up the dependency graph, and registers
all MCP tools. This is the composition root — the one place where
concrete implementations are chosen and injected.
"""

from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from src.job_aggregator.config import get_settings
from src.job_aggregator.core import get_logger, setup_logging
from src.job_aggregator.providers.linkedin import LinkedInProvider
from src.job_aggregator.providers.indeed import IndeedProvider
from src.job_aggregator.providers.linkedin_browser import LinkedInBrowserProvider
from src.job_aggregator.providers.indeed_browser import IndeedBrowserProvider
from src.job_aggregator.providers.registry import ProviderRegistry
from src.job_aggregator.services.aggregator import JobAggregatorService
from src.job_aggregator.services.dedup import DeduplicationService
from src.job_aggregator.tools.health import register_health_tools
from src.job_aggregator.tools.search import register_search_tools


def create_server() -> FastMCP:
    """Build and return a fully configured FastMCP server."""
    setup_logging()
    settings = get_settings()
    logger = get_logger(__name__)

    # --- Dependency graph ---
    registry = ProviderRegistry()
    registry.register(LinkedInProvider())
    registry.register(IndeedProvider())

    # Browser-based providers (no API keys needed)
    browser_provider = LinkedInBrowserProvider()
    registry.register(browser_provider)

    indeed_browser_provider = IndeedBrowserProvider()
    registry.register(indeed_browser_provider)

    dedup = DeduplicationService()
    service = JobAggregatorService(registry=registry, dedup_service=dedup)

    @asynccontextmanager
    async def lifespan(server: FastMCP):
        """Manage provider lifecycle — clean up HTTP sessions on shutdown."""
        logger.info("server_starting")
        yield
        for name, provider in registry.get_all().items():
            if hasattr(provider, "close"):
                try:
                    await provider.close()
                    logger.info("provider_closed", provider=name)
                except Exception:
                    logger.exception("provider_close_failed", provider=name)

    mcp = FastMCP(
        name=settings.app_name,
        instructions=f"Job Aggregator MCP Server v{settings.version}",
        lifespan=lifespan,
    )

    # --- Register MCP tools ---
    register_health_tools(mcp, registry=registry)
    register_search_tools(mcp, service=service)

    logger.info(
        "server_initialized",
        app_name=settings.app_name,
        environment=settings.app_env.value,
        version=settings.version,
        providers=registry.list_names(),
    )
    return mcp


mcp = create_server()


def main() -> None:
    """CLI entrypoint — runs the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
