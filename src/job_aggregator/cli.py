"""CLI entry point for the Job Aggregator MCP Server.

This is the single entry point used by both `uvx` and `python main.py`.
Supports:
    job-aggregator          → runs the MCP server (stdio)
    job-aggregator --login  → opens browser for LinkedIn login
    job-aggregator --install-browser  → installs Chromium for Patchright
"""

import argparse
import asyncio
import subprocess
import sys


def _run_login() -> None:
    """Open a headed browser for interactive LinkedIn login."""
    from src.job_aggregator.providers.linkedin_browser import (
        LinkedInBrowserProvider,
        LinkedInBrowserSettings,
    )
    from src.job_aggregator.core import setup_logging

    setup_logging()
    settings = LinkedInBrowserSettings()
    provider = LinkedInBrowserProvider(settings=settings)

    async def _login():
        success = await provider.browser_manager.login_interactive()
        await provider.close()
        return success

    success = asyncio.run(_login())
    if not success:
        print("Login failed. Please try again.")
        sys.exit(1)
    print("Login successful! You can now use the MCP server.")


def _install_browser() -> None:
    """Install the Patchright Chromium browser."""
    print("Installing Chromium browser for LinkedIn scraping...")
    result = subprocess.run(
        [sys.executable, "-m", "patchright", "install", "chromium"],
        check=False,
    )
    if result.returncode == 0:
        print("Browser installed successfully!")
    else:
        print("Browser installation failed.", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """CLI entry point — handles --login, --install-browser, or runs the server."""
    parser = argparse.ArgumentParser(
        prog="job-aggregator",
        description="Job Aggregator MCP Server — search LinkedIn & Indeed from any AI assistant",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open a browser window to log in to LinkedIn (required once)",
    )
    parser.add_argument(
        "--install-browser",
        action="store_true",
        help="Install the Chromium browser needed for LinkedIn scraping",
    )
    args = parser.parse_args()

    if args.install_browser:
        _install_browser()
    elif args.login:
        _run_login()
    else:
        from src.job_aggregator.server import main as server_main
        server_main()
