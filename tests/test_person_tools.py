"""Tests for LinkedIn person MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.job_aggregator.providers.linkedin_browser.browser import BrowserManager
from src.job_aggregator.providers.linkedin_browser.config import LinkedInBrowserSettings
from src.job_aggregator.providers.linkedin_browser.provider import LinkedInBrowserProvider
from src.job_aggregator.providers.registry import ProviderRegistry
from src.job_aggregator.tools.person import register_person_tools


def _get_tool_fn(mcp: FastMCP, name: str):
    for tool in mcp._tool_manager.list_tools():
        if tool.name == name:
            return mcp._tool_manager._tools[name].fn
    raise ValueError(f"Tool '{name}' not found")


def _build_person_tools(provider: LinkedInBrowserProvider | None = None):
    registry = ProviderRegistry()
    if provider is not None:
        registry.register(provider)

    mcp = FastMCP(name="test-person-server")
    register_person_tools(mcp, registry=registry)
    return mcp, registry


@pytest.fixture
def linkedin_provider() -> LinkedInBrowserProvider:
    manager = MagicMock(spec=BrowserManager)
    manager.ensure_ready = AsyncMock()
    manager.close = AsyncMock()
    settings = LinkedInBrowserSettings()
    return LinkedInBrowserProvider(settings=settings, browser_manager=manager)


class TestPersonToolRegistration:

    def test_registers_all_person_tools(self, linkedin_provider: LinkedInBrowserProvider) -> None:
        mcp, _ = _build_person_tools(linkedin_provider)
        names = {tool.name for tool in mcp._tool_manager.list_tools()}
        assert names == {
            "get_person_profile",
            "search_people",
            "connect_with_person",
            "get_sidebar_profiles",
            "get_my_profile",
        }


class TestGetPersonProfileTool:

    @pytest.mark.asyncio
    async def test_delegates_to_provider(self, linkedin_provider: LinkedInBrowserProvider) -> None:
        linkedin_provider.get_person_profile = AsyncMock(
            return_value={"success": True, "url": "https://linkedin.com/in/jane/", "sections": {}}
        )
        mcp, _ = _build_person_tools(linkedin_provider)
        fn = _get_tool_fn(mcp, "get_person_profile")

        result = await fn(linkedin_username="jane", sections="experience,education")

        assert result["success"] is True
        linkedin_provider.get_person_profile.assert_awaited_once_with(
            linkedin_username="jane",
            sections="experience,education",
            max_scrolls=None,
        )

    @pytest.mark.asyncio
    async def test_invalid_max_scrolls(self, linkedin_provider: LinkedInBrowserProvider) -> None:
        mcp, _ = _build_person_tools(linkedin_provider)
        fn = _get_tool_fn(mcp, "get_person_profile")

        result = await fn(linkedin_username="jane", max_scrolls=100)

        assert result["success"] is False
        assert "max_scrolls" in result["error"]

    @pytest.mark.asyncio
    async def test_provider_unavailable(self) -> None:
        mcp, _ = _build_person_tools()
        fn = _get_tool_fn(mcp, "get_person_profile")

        result = await fn(linkedin_username="jane")

        assert result["success"] is False
        assert "not available" in result["error"]


class TestSearchPeopleTool:

    @pytest.mark.asyncio
    async def test_delegates_to_provider(self, linkedin_provider: LinkedInBrowserProvider) -> None:
        linkedin_provider.search_people = AsyncMock(
            return_value={"success": True, "url": "https://linkedin.com/search/", "sections": {}}
        )
        mcp, _ = _build_person_tools(linkedin_provider)
        fn = _get_tool_fn(mcp, "search_people")

        result = await fn(
            keywords="engineer",
            location="NYC",
            network=["F", "S"],
            current_company="1115",
        )

        assert result["success"] is True
        linkedin_provider.search_people.assert_awaited_once_with(
            keywords="engineer",
            location="NYC",
            network=["F", "S"],
            current_company="1115",
        )


class TestConnectWithPersonTool:

    @pytest.mark.asyncio
    async def test_rejects_long_note(self, linkedin_provider: LinkedInBrowserProvider) -> None:
        mcp, _ = _build_person_tools(linkedin_provider)
        fn = _get_tool_fn(mcp, "connect_with_person")

        result = await fn(linkedin_username="jane", note="x" * 301)

        assert result["success"] is False
        assert result["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_delegates_to_provider(self, linkedin_provider: LinkedInBrowserProvider) -> None:
        linkedin_provider.connect_with_person = AsyncMock(
            return_value={
                "success": True,
                "status": "pending",
                "message": "Connection request sent",
                "note_sent": True,
            }
        )
        mcp, _ = _build_person_tools(linkedin_provider)
        fn = _get_tool_fn(mcp, "connect_with_person")

        result = await fn(linkedin_username="jane", note="Hello")

        assert result["success"] is True
        linkedin_provider.connect_with_person.assert_awaited_once_with(
            linkedin_username="jane",
            note="Hello",
        )


class TestSidebarAndMyProfileTools:

    @pytest.mark.asyncio
    async def test_get_sidebar_profiles(self, linkedin_provider: LinkedInBrowserProvider) -> None:
        linkedin_provider.get_sidebar_profiles = AsyncMock(
            return_value={
                "success": True,
                "url": "https://linkedin.com/in/jane/",
                "sidebar_profiles": {"people_you_may_know": ["/in/bob/"]},
            }
        )
        mcp, _ = _build_person_tools(linkedin_provider)
        fn = _get_tool_fn(mcp, "get_sidebar_profiles")

        result = await fn(linkedin_username="jane")

        assert result["success"] is True
        assert "/in/bob/" in result["sidebar_profiles"]["people_you_may_know"]

    @pytest.mark.asyncio
    async def test_get_my_profile(self, linkedin_provider: LinkedInBrowserProvider) -> None:
        linkedin_provider.get_my_profile = AsyncMock(
            return_value={"success": True, "url": "https://linkedin.com/in/me-user/", "sections": {}}
        )
        mcp, _ = _build_person_tools(linkedin_provider)
        fn = _get_tool_fn(mcp, "get_my_profile")

        result = await fn(sections="skills")

        assert result["success"] is True
        linkedin_provider.get_my_profile.assert_awaited_once_with(
            sections="skills",
            max_scrolls=None,
        )
