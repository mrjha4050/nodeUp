"""Tests for MCP tools (search, details, health, config).

Tools are tested by calling the inner functions directly —
we register them on a real FastMCP instance, then extract
and invoke the registered tool functions.
"""

import pytest
from unittest.mock import AsyncMock

from mcp.server.fastmcp import FastMCP

from src.job_aggregator.models.search import SearchRequest, SearchResponse, ProviderResponse
from src.job_aggregator.providers.registry import ProviderRegistry
from src.job_aggregator.services.aggregator import JobAggregatorService
from src.job_aggregator.tools.health import register_health_tools
from src.job_aggregator.tools.search import register_search_tools

from tests.conftest import MockProvider, make_job


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_tool_fn(mcp: FastMCP, name: str):
    """Extract a registered tool's callable by name."""
    for tool in mcp._tool_manager.list_tools():
        if tool.name == name:
            return mcp._tool_manager._tools[name].fn
    raise ValueError(f"Tool '{name}' not found")


def _build_tools():
    """Wire up a FastMCP with mock providers and return (mcp, registry, service)."""
    jobs = [
        make_job(id="mock_1", title="Engineer", company="Acme", location="NYC"),
        make_job(id="mock_2", title="Designer", company="Globex", location="LA"),
    ]

    registry = ProviderRegistry()
    registry.register(MockProvider(name="mock", jobs=jobs))

    service = JobAggregatorService(registry)
    mcp = FastMCP(name="test-server")

    register_health_tools(mcp, registry=registry)
    register_search_tools(mcp, service=service)

    return mcp, registry, service


# ------------------------------------------------------------------
# search_jobs tool
# ------------------------------------------------------------------

class TestSearchJobsTool:

    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        mcp, _, _ = _build_tools()
        search_fn = _get_tool_fn(mcp, "search_jobs")

        result = await search_fn(query="python")
        assert result["query"] == "python"
        assert len(result["jobs"]) == 2
        assert result["total_results"] == 2

    @pytest.mark.asyncio
    async def test_search_with_filters(self) -> None:
        mcp, _, _ = _build_tools()
        search_fn = _get_tool_fn(mcp, "search_jobs")

        result = await search_fn(
            query="python",
            location="NYC",
            job_type="full_time",
        )
        assert result["query"] == "python"

    @pytest.mark.asyncio
    async def test_search_invalid_job_type(self) -> None:
        mcp, _, _ = _build_tools()
        search_fn = _get_tool_fn(mcp, "search_jobs")

        result = await search_fn(query="python", job_type="INVALID_TYPE")
        assert result["success"] is False
        assert "Validation error" in result["error"]

    @pytest.mark.asyncio
    async def test_search_service_exception(self) -> None:
        registry = ProviderRegistry()
        service = JobAggregatorService(registry)
        service.search = AsyncMock(side_effect=RuntimeError("db down"))

        mcp = FastMCP(name="test")
        register_search_tools(mcp, service=service)
        search_fn = _get_tool_fn(mcp, "search_jobs")

        result = await search_fn(query="test")
        assert result["success"] is False
        assert "Search failed" in result["error"]


# ------------------------------------------------------------------
# get_job_details tool
# ------------------------------------------------------------------

class TestGetJobDetailsTool:

    @pytest.mark.asyncio
    async def test_get_existing_job(self) -> None:
        mcp, _, _ = _build_tools()
        detail_fn = _get_tool_fn(mcp, "get_job_details")

        result = await detail_fn(job_id="mock_1")
        assert result["success"] is True
        assert result["job"]["id"] == "mock_1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_job(self) -> None:
        mcp, _, _ = _build_tools()
        detail_fn = _get_tool_fn(mcp, "get_job_details")

        result = await detail_fn(job_id="mock_999")
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_empty_job_id(self) -> None:
        mcp, _, _ = _build_tools()
        detail_fn = _get_tool_fn(mcp, "get_job_details")

        result = await detail_fn(job_id="  ")
        assert result["success"] is False
        assert "required" in result["error"]

    @pytest.mark.asyncio
    async def test_get_job_service_exception(self) -> None:
        registry = ProviderRegistry()
        service = JobAggregatorService(registry)
        service.get_job_details = AsyncMock(side_effect=RuntimeError("boom"))

        mcp = FastMCP(name="test")
        register_search_tools(mcp, service=service)
        detail_fn = _get_tool_fn(mcp, "get_job_details")

        result = await detail_fn(job_id="test_1")
        assert result["success"] is False
        assert "Failed to fetch" in result["error"]


# ------------------------------------------------------------------
# health_check tool
# ------------------------------------------------------------------

class TestHealthCheckTool:

    @pytest.mark.asyncio
    async def test_healthy_response(self) -> None:
        mcp, _, _ = _build_tools()
        health_fn = _get_tool_fn(mcp, "health_check")

        result = await health_fn()
        assert result["status"] == "healthy"
        assert "mock" in result["providers"]

    @pytest.mark.asyncio
    async def test_provider_down(self) -> None:
        registry = ProviderRegistry()
        registry.register(MockProvider(name="down", should_fail=True))

        mcp = FastMCP(name="test")
        register_health_tools(mcp, registry=registry)
        health_fn = _get_tool_fn(mcp, "health_check")

        result = await health_fn()
        assert result["status"] == "healthy"  # server is healthy even if a provider is down
        assert result["providers"]["down"] == "down"


# ------------------------------------------------------------------
# get_server_config tool
# ------------------------------------------------------------------

class TestGetServerConfigTool:

    @pytest.mark.asyncio
    async def test_config_response(self) -> None:
        mcp, _, _ = _build_tools()
        config_fn = _get_tool_fn(mcp, "get_server_config")

        result = await config_fn()
        assert "app_name" in result
        assert "version" in result
        assert "registered_providers" in result
        assert "mock" in result["registered_providers"]
