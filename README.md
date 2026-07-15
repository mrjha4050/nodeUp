# NodeUp MCP Server

A production-grade MCP server that aggregates job listings from LinkedIn and Indeed, exposing them as tools for AI assistants. Supports browser-based LinkedIn scraping — no API keys needed.

---

## The Simple Way (uvx — zero install)

Your friends don't need to clone, create venvs, or install anything. They just need `uv` installed ([install uv](https://docs.astral.sh/uv/getting-started/installation/)).

### Step 1: One-time setup (2 commands)

```bash
# Install the browser engine
uvx --from git+https://github.com/YOUR_USERNAME/mcp job-aggregator --install-browser

# Login to LinkedIn (opens a browser window — do this once)
uvx --from git+https://github.com/YOUR_USERNAME/mcp job-aggregator --login
```

### Step 2: Add to your AI client config

Paste this into your client's config file (see table below):

```json
{
  "mcpServers": {
    "job-aggregator": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/YOUR_USERNAME/mcp", "job-aggregator"]
    }
  }
}
```

That's it. `uvx` auto-downloads, installs dependencies, and runs the server. No clone, no venv, no pip install.

### Where to paste the config

| Client | Config file location |
|--------|---------------------|
| **Claude Desktop** (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Claude Desktop** (Windows) | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Claude Code** | Run: `claude mcp add job-aggregator -- uvx --from git+https://github.com/YOUR_USERNAME/mcp job-aggregator` |
| **Cursor** | `.cursor/mcp.json` in your project, or Settings > MCP Servers |
| **VS Code (Copilot)** | `.vscode/mcp.json` in your workspace |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` |
| **Codex CLI** | `~/.codex/config.json` |
| **Continue.dev** | `~/.continue/config.yaml` |

---

## Manual Setup (for development)

If you want to clone and work on the code:

```bash
git clone <your-repo-url>
cd mcp
uv venv && uv pip install -e ".[dev]"
python -m patchright install chromium
python main.py --login
```

Then use local paths in your client config:

```json
{
  "mcpServers": {
    "job-aggregator": {
      "command": "/absolute/path/to/mcp/.venv/bin/job-aggregator"
    }
  }
}
```

---

## Client-Specific Examples

### Claude Desktop

```json
{
  "mcpServers": {
    "job-aggregator": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/YOUR_USERNAME/mcp", "job-aggregator"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add job-aggregator -- uvx --from git+https://github.com/YOUR_USERNAME/mcp job-aggregator
```

### Cursor

Create `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "job-aggregator": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/YOUR_USERNAME/mcp", "job-aggregator"]
    }
  }
}
```

### VS Code (GitHub Copilot)

Create `.vscode/mcp.json`:

```json
{
  "servers": {
    "job-aggregator": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/YOUR_USERNAME/mcp", "job-aggregator"]
    }
  }
}
```

### Windsurf

Edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "job-aggregator": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/YOUR_USERNAME/mcp", "job-aggregator"]
    }
  }
}
```

### OpenAI Codex CLI

Edit `~/.codex/config.json`:

```json
{
  "mcpServers": {
    "job-aggregator": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/YOUR_USERNAME/mcp", "job-aggregator"]
    }
  }
}
```

### Continue.dev

Edit `~/.continue/config.yaml`:

```yaml
mcpServers:
  - name: job-aggregator
    command: uvx
    args:
      - --from
      - git+https://github.com/YOUR_USERNAME/mcp
      - job-aggregator
```

### SSE Transport (any HTTP-based client)

```bash
uvx --from git+https://github.com/YOUR_USERNAME/mcp mcp run --transport sse --port 8080 src.job_aggregator.server:mcp
```

Point your client to `http://localhost:8080/sse`.

---

## Available Tools

Once connected, your AI assistant has these tools:

| Tool | What it does |
|------|-------------|
| `search_jobs` | Search jobs across all providers with filters (query, location, job_type, experience_level, location_type, skills) |
| `get_job_details` | Get full details for a job by ID (e.g., `linkedin_browser_4433918896`) |
| `health_check` | Check server status and which providers are online |
| `get_server_config` | View current server configuration |

### Example prompts

```
"Search for remote Python developer jobs in the United States"
"Find senior machine learning engineer positions in New York"
"Get details for job linkedin_browser_4433918896"
"Check which job providers are currently available"
```

---

## Configuration

Copy `.env.example` to `.env` and customize (optional):

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `LINKEDIN_BROWSER_HEADLESS` | `true` | Run browser headless |
| `LINKEDIN_BROWSER_SLOW_MO` | `100` | Browser slowdown (ms, anti-detection) |
| `LINKEDIN_CLIENT_ID` | _(empty)_ | LinkedIn API OAuth2 ID (optional) |
| `LINKEDIN_CLIENT_SECRET` | _(empty)_ | LinkedIn API secret (optional) |
| `INDEED_API_KEY` | _(empty)_ | Indeed API key (optional) |

The browser provider works without any API keys. Just `--login` once.

---

## Providers

| Provider | Method | Auth |
|----------|--------|------|
| `linkedin_browser` | Browser scraping (Patchright) | One-time browser login |
| `linkedin` | REST API (httpx) | OAuth2 credentials |
| `indeed` | REST API (httpx) | API key |

All providers run concurrently. Results are deduplicated automatically.

---

## CLI Commands

```bash
job-aggregator                  # Run the MCP server
job-aggregator --login          # Login to LinkedIn (one-time)
job-aggregator --install-browser  # Install Chromium browser
job-aggregator --help           # Show help
```

---

## Development

```bash
python -m pytest tests/ -v              # Run tests
python -m pytest tests/ --cov           # Run with coverage
python main.py                          # Run server locally
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "LinkedIn login required" | Run `job-aggregator --login` |
| Session expired | Re-run `job-aggregator --login` |
| Browser not found | Run `job-aggregator --install-browser` |
| Server not showing in client | Restart the client after editing config |
| Tools not appearing | Run `health_check` — if `linkedin_browser` is "down", re-login |
