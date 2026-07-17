"""
Centralized output and core directory resolution.

All orchestrator modules import get_output_root() / get_core_root() from here.
The values are resolved at call time from the SPECA_OUTPUT_DIR / SPECA_ROOT
environment variables, defaulting to "outputs" / the repo root for backward
compatibility.
"""

import os
from pathlib import Path


def get_output_root() -> Path:
    """Return the output root directory, resolved from env or default.

    Supports parallel SPECA instances by allowing each process
    to set its own ``SPECA_OUTPUT_DIR``.
    """
    return Path(os.environ.get("SPECA_OUTPUT_DIR", "outputs"))


def get_core_root() -> Path:
    """Return the SPECA core root directory, resolved from env or default.

    The core root is the directory containing SPECA's own assets
    (``scripts/``, ``prompts/``, ``schemas/``, ``.claude/skills/``). It is
    resolved at call time from the ``SPECA_ROOT`` environment variable so the
    orchestrator can run from any cwd (e.g. a user's target repo). When unset,
    it defaults to the repo root derived from this file's location
    (``scripts/orchestrator/paths.py`` lives two directories below the repo
    root), so existing repo-root usage keeps working unchanged.
    """
    env_root = os.environ.get("SPECA_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[2]


def resolve_core_asset(p: Path | str) -> Path:
    """Resolve a core-relative asset path against the current core root.

    Config asset paths are kept as-is (relative paths like
    ``prompts/01a_crawl.md``). This function resolves them at usage time,
    supporting ``SPECA_ROOT``. Absolute paths are returned unchanged.
    """
    path = Path(p)
    if path.is_absolute():
        return path
    return get_core_root() / path
