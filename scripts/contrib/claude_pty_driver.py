"""PoC: drive the interactive ``claude`` REPL through a pty (issue #80).

Why this exists
---------------
SPECA's production path is ``claude -p --output-format stream-json``
(ClaudeRunner). If Anthropic ever removes the ``-p`` print mode from
subscription tiers (the 2026-04 Pro-tier test made this a live risk),
the interactive REPL — the subscription's primary UX — remains. This
driver proves the fallback: spawn interactive ``claude`` under a pty,
paste one prompt, wait for the result file the prompt instructs Claude
to write, and read it back.

When to adopt for real
----------------------
Only when ``-p`` is actually unavailable on the account's tier. The
orchestrator wiring already exists and is dormant:
``ORCHESTRATOR_RUNNER=claude_pty`` (or ``run_phase.py --runtime
claude_pty``) selects ``scripts/orchestrator/claude_pty_runner.py``. The
default runtime stays ``claude`` (``-p``) — do not switch pre-emptively;
interactive driving is strictly worse (no usage telemetry, 1-session
concurrency, heuristic prompt detection).

Usage (manual, requires an authenticated claude CLI; NOT run in CI)::

    uv run python scripts/contrib/claude_pty_driver.py \
        "Read tests/fixtures/sample_property.json and write a 1-sentence \
summary to outputs/PARTIAL_TEST.json" \
        --result outputs/PARTIAL_TEST.json --timeout 300

Platform notes: POSIX works out of the box (stdlib pty). Windows needs
the optional ``pywinpty`` package; without it this script exits with an
actionable error instead of faking a pty.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Standalone bootstrap: make scripts/orchestrator importable when this file
# is executed directly from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator.claude_pty_runner import (  # noqa: E402
    drive_one_prompt,
    open_pty_session,
    pty_supported,
    result_file_ready,
)


async def run_one_prompt(
    prompt: str,
    result_path: Path,
    timeout: int = 600,
    model: str | None = None,
) -> dict | None:
    """Send one prompt to an interactive ``claude`` REPL; return the JSON
    document Claude wrote to ``result_path``, or ``None``.

    spawn -> expect prompt -> paste + Enter -> wait for result file ->
    /exit -> kill. The transcript goes to stderr for debugging.
    """

    supported, reason = pty_supported()
    if not supported:
        raise RuntimeError(reason)

    import os
    import shutil

    claude_bin = (
        shutil.which("claude.cmd") if sys.platform == "win32" else None
    ) or shutil.which("claude") or "claude"
    argv = [claude_bin, "--dangerously-skip-permissions"]
    if model:
        argv += ["--model", model]

    env = dict(os.environ)
    # A nested Claude Code session refuses to start; strip the markers the
    # parent session exports (same as ClaudeRunner._build_env).
    for var in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID"):
        env.pop(var, None)
    env.setdefault("TERM", "xterm-256color")

    def _drive() -> str:
        io = open_pty_session(argv, str(Path.cwd()), env)
        try:
            return drive_one_prompt(
                io,
                prompt,
                lambda: result_file_ready(result_path),
                ready_timeout=90.0,
                completion_timeout=float(timeout),
            )
        finally:
            io.kill()

    transcript = await asyncio.to_thread(_drive)
    print("--- transcript (ANSI-stripped, last 2000 chars) ---", file=sys.stderr)
    print(transcript[-2000:], file=sys.stderr)

    if not result_file_ready(result_path):
        return None
    return json.loads(result_path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prompt", help="user message to send to the REPL")
    parser.add_argument(
        "--result",
        type=Path,
        default=Path("outputs/PARTIAL_TEST.json"),
        help="result file the prompt instructs Claude to write "
        "(default: outputs/PARTIAL_TEST.json)",
    )
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    args.result.parent.mkdir(parents=True, exist_ok=True)
    doc = asyncio.run(
        run_one_prompt(args.prompt, args.result, timeout=args.timeout, model=args.model)
    )
    if doc is None:
        print("FAIL: no parseable result file was produced", file=sys.stderr)
        return 1
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
