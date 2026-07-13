"""Build script to create a .mcpb bundle for Claude Desktop.

Usage:
    python build_mcpb.py

Produces: job-aggregator-mcp-v0.1.0.mcpb

A .mcpb file is a ZIP archive containing:
    manifest.json       — server metadata + tool declarations
    pyproject.toml      — Python dependencies (UV resolves these)
    uv.lock             — pinned dependency versions
    src/                — all source code
    main.py             — CLI entry point
    .env.example        — config template
"""

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent

# Files/dirs to exclude from the bundle
EXCLUDE = {
    ".venv", ".git", ".pytest_cache", "__pycache__", ".coverage",
    ".env", ".DS_Store", "tests", "build", "dist", "htmlcov",
    "*.egg-info", "build_mcpb.py", ".claude", ".coveragerc",
}


def should_exclude(path: Path) -> bool:
    """Check if a path should be excluded from the bundle."""
    for part in path.parts:
        if part in EXCLUDE or part.endswith(".egg-info"):
            return True
        if part.startswith(".") and part not in (".env.example",):
            return True
    return False


def build():
    # Read version from manifest
    manifest = json.loads((ROOT / "manifest.json").read_text())
    version = manifest["version"]
    name = manifest["name"]
    output = ROOT / f"{name}-v{version}.mcpb"

    print(f"Building {output.name}...")

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add manifest.json at the root
        zf.write(ROOT / "manifest.json", "manifest.json")

        # Add essential files
        for filename in ["pyproject.toml", "uv.lock", "main.py", ".env.example", "README.md"]:
            filepath = ROOT / filename
            if filepath.exists():
                zf.write(filepath, filename)
                print(f"  + {filename}")

        # Add all source code
        src_dir = ROOT / "src"
        for filepath in sorted(src_dir.rglob("*")):
            if filepath.is_file() and not should_exclude(filepath.relative_to(ROOT)):
                arcname = str(filepath.relative_to(ROOT))
                zf.write(filepath, arcname)
                print(f"  + {arcname}")

    size_kb = output.stat().st_size / 1024
    print(f"\nBuilt: {output.name} ({size_kb:.1f} KB)")
    print(f"\nTo install: drag {output.name} into Claude Desktop")
    print("Or: File > Settings > Extensions > Install Extension...")


if __name__ == "__main__":
    build()
