"""End-to-end sanity checks for server wiring and stale references.

These tests guard against broken imports, missing tool registration,
and leftover references to removed providers/tools.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from src.job_aggregator.server import create_server

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "manifest.json"

EXPECTED_TOOLS = frozenset({
    "connect_with_person",
    "get_job_details",
    "get_my_profile",
    "get_person_profile",
    "get_server_config",
    "get_sidebar_profiles",
    "health_check",
    "search_jobs",
    "search_people",
})

REMOVED_TOOL_NAMES = frozenset({
    "search_profiles",
    "send_connection",
})

REMOVED_MODULE_PREFIXES = (
    "src.job_aggregator.providers.indeed_browser",
    "src.job_aggregator.providers.indeed",
    "src.job_aggregator.providers.linkedin",
)


class TestServerSanity:

    def test_create_server_registers_expected_tools(self) -> None:
        mcp = create_server()
        tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}
        assert tool_names == EXPECTED_TOOLS

    def test_removed_tools_are_not_registered(self) -> None:
        mcp = create_server()
        tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}
        assert tool_names.isdisjoint(REMOVED_TOOL_NAMES)

    @pytest.mark.asyncio
    async def test_only_linkedin_browser_provider_registered(self) -> None:
        mcp = create_server()
        config_fn = mcp._tool_manager._tools["get_server_config"].fn
        config = await config_fn()
        assert config["registered_providers"] == ["linkedin_browser"]

    def test_tool_registration_exports(self) -> None:
        from src.job_aggregator.tools import (
            register_health_tools,
            register_person_tools,
            register_search_tools,
        )

        assert callable(register_health_tools)
        assert callable(register_person_tools)
        assert callable(register_search_tools)

    def test_cli_entrypoint_imports(self) -> None:
        importlib.import_module("src.job_aggregator.cli")

    def test_linkedin_provider_person_methods_exist(self) -> None:
        from src.job_aggregator.providers.linkedin_browser.provider import LinkedInBrowserProvider

        for method in (
            "get_person_profile",
            "get_my_profile",
            "search_people",
            "get_sidebar_profiles",
            "connect_with_person",
        ):
            assert hasattr(LinkedInBrowserProvider, method)

    @pytest.mark.parametrize("module_name", REMOVED_MODULE_PREFIXES)
    def test_removed_provider_modules_are_not_importable(self, module_name: str) -> None:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)


class TestManifestSanity:

    def test_manifest_tools_match_registered_tools(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest_tools = {tool["name"] for tool in manifest["tools"]}
        assert manifest_tools == EXPECTED_TOOLS

    def test_manifest_does_not_reference_removed_tools(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest_tools = {tool["name"] for tool in manifest["tools"]}
        assert manifest_tools.isdisjoint(REMOVED_TOOL_NAMES)

    def test_manifest_does_not_reference_indeed(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        blob = json.dumps(manifest).lower()
        assert "indeed" not in blob
