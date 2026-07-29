# AGENTS.md

Instructions for AI coding agents (Claude Code, Cursor, etc.) setting up this
MCP server on a user's machine from just this repo URL. Follow these steps in
order — do not skip the login step, tools will fail without it.

## Prerequisite

Check `uv` is installed: `uv --version`. If missing, tell the user to install
it from https://docs.astral.sh/uv/getting-started/installation/ and stop —
you cannot install it for them silently on most systems.

## Setup (run these two commands, in order)

```bash
uvx --from git+https://github.com/mrjha4050/nodeUp job-aggregator --install-browser
uvx --from git+https://github.com/mrjha4050/nodeUp job-aggregator --login
```

The second command opens a real browser window and requires the user to log
into LinkedIn interactively. You cannot do this step for them — tell them to
complete the login in the window that opens, then wait for
"Login successful!" in the terminal before continuing.

## Register the server with the user's AI client

Detect which client the user is running and act accordingly:

- **Claude Code**: run directly —
  `claude mcp add job-aggregator -- uvx --from git+https://github.com/mrjha4050/nodeUp job-aggregator`
- **Claude Desktop, Cursor, Windsurf, VS Code (Copilot), Codex CLI, Continue.dev**:
  these need a JSON/YAML edit you should make yourself if you have file
  access, using the exact config block and file path for that client from the
  "Client-Specific Examples" section of `README.md`. Ask the user which
  client they use if it isn't obvious from context.

After editing a config file, tell the user to restart that client — servers
are only picked up on launch.

## Verify

If the client exposes an MCP status command (e.g. `claude mcp list`), run it
and confirm `job-aggregator` shows as connected. Otherwise ask the user to
run the `health_check` tool once the client restarts and confirm
`linkedin_browser` and `indeed_browser` both report as up.

## Notes

- No API keys are required — both providers are browser-based scraping, not
  the REST APIs. Ignore the optional `linkedin_client_id` /
  `linkedin_client_secret` / `indeed_api_key` settings unless the user
  specifically asks to switch to API-based auth.
- Full client config examples, troubleshooting, and tool list: see
  `README.md`.
