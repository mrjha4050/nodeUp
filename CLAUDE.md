# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP (Model Context Protocol) server that aggregates job listings from LinkedIn and Indeed, and exposes LinkedIn people-search/connect/message tools via browser automation. The primary provider (`linkedin_browser`) needs no API keys — it drives a real, persistently-logged-in Chromium session via Patchright (stealth Playwright).

## Commands

```bash
# Setup
uv venv && uv pip install -e ".[dev]"
python -m patchright install chromium      # one-time browser install

# Run
python main.py                             # run server locally (stdio)
python main.py --login                     # one-time interactive LinkedIn login
job-aggregator                             # same, via installed console script
job-aggregator --install-browser           # install Chromium for Patchright

# Test
python -m pytest tests/ -v
python -m pytest tests/ --cov
python -m pytest tests/test_aggregator.py -v          # single file
python -m pytest tests/test_aggregator.py::test_name -v  # single test

# Build the .mcpb bundle (see build_mcpb.py)
python build_mcpb.py
```

There is no lint/format command configured in `pyproject.toml` — don't assume one.

## Architecture

**Composition root:** `src/job_aggregator/server.py::create_server()` is the one place concrete providers are instantiated, registered, and wired into tool registration. `mcp = create_server()` at module scope is what `main.py` / the `job-aggregator` console script / the `.mcpb` manifest all point at.

**Provider plugin model** (`providers/`): every provider implements the `JobProvider` ABC (`providers/base.py`): `search_jobs`, `get_job_details`, `health_check`, plus a shared static `apply_filters` (location_type/skills filtering that provider APIs don't do natively — don't duplicate this per-provider). Providers register into a `ProviderRegistry` (`providers/registry.py`), keyed by `provider_name`. Three providers exist today, each its own subpackage with `config.py` (pydantic-settings, env-prefixed), `exceptions.py`, and a mapper/parser:
- `linkedin` — REST API via `client.py` (needs `LINKEDIN_CLIENT_ID`/`SECRET`)
- `indeed` — REST API via `client.py` (needs `INDEED_API_KEY`)
- `linkedin_browser` — Patchright-driven scraping (`browser.py` manages the persistent browser/session, `scraper.py` drives page interactions, `parser.py` turns raw scraped dicts into domain models). No API key; requires `job-aggregator --login` once to seed `~/.linkedin-mcp/profile`.

Adding a provider = implement `JobProvider`, register it in `create_server()`. It plugs into search/aggregation/health-check automatically.

**Fan-out/merge** (`services/aggregator.py`): `JobAggregatorService.search()` launches every registered provider concurrently as an `asyncio.Task`, waits for `ALL_COMPLETED`, and merges. `_execute_provider` is the error-isolation boundary — it never raises; a provider exception or timeout becomes a `ProviderResponse(success=False, error_message=...)` so one dead provider never kills the whole search. Results are merged then deduplicated across providers by `services/dedup.py`. `get_job_details(job_id)` routes to a single provider by splitting the provider-prefixed `job_id` on the first `_`.

**Browser-only networking** (`tools/networking.py`): `search_profiles` / `send_connection` / `send_message` call `LinkedInBrowserProvider` directly — they bypass the aggregator/registry entirely since networking isn't part of the `JobProvider` ABC and only makes sense for the browser provider. `server.py` passes the same `browser_provider` instance to both the registry (for job search) and `register_networking_tools` (for people/connections).

**Tools layer** (`tools/`): thin — validate input with pydantic, delegate to the service/provider, return `model_dump(mode="json")`. No business logic here; put it in `services/` or the provider.

**DB layer** (`db/`): SQLAlchemy async models/repositories (`tables.py`, `repositories/`) exist but are not currently wired into `create_server()` or the aggregator — nothing in `src/job_aggregator` outside `db/` imports from it. Treat it as not-yet-integrated rather than dead code to delete without checking with the user first.

**Settings**: each provider owns its own `*Settings` (pydantic-settings, scoped env prefix, e.g. `LINKEDIN_BROWSER_*`); `config/settings.py::get_settings()` is the separate, `lru_cache`-singleton app-level config (app name/env/log level/db url). Don't conflate the two.
