"""Runtime registry for the orchestrator CLI.

Resolves "runtime id" → "runner class" + an availability probe. Today
two runners are wired:

* ``claude`` (default) — ClaudeRunner. Production audit path; assumes
  stream-json + tool_use shape from the Anthropic claude CLI so the
  circuit breaker, cost tracker, and resume scanner all line up.
* ``api`` — APIRunner. Bare OpenRouter-style API client used for
  non-Claude models that speak the OpenAI chat-completions wire.

Four additional runtimes are *registered* but not yet wired — they
return a clear "not yet implemented" error if selected. Doing the
registration here means the CLI's ``--list-runtimes`` and the env
snapshot already know about them, which lets a downstream PR drop in a
``ChatRunner`` subclass without touching the CLI surface.

* ``codex``   — OpenAI codex CLI (``codex exec --json``).
* ``gemini``  — Google gemini CLI (``gemini -p --output-format stream-json``).
* ``ollama``  — Ollama HTTP (``/api/chat``, cloud or self-hosted).
* ``copilot`` — GitHub Copilot CLI (``gh copilot suggest``).

The Web side (``web/server/services/chat_runtime_*``) already has
streaming implementations for all four; the orchestrator side is more
demanding (resume scanning + tool_use counting + per-batch PARTIAL
shape) and is intentionally deferred.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


RuntimeId = Literal["claude", "api", "codex", "gemini", "ollama", "copilot"]


@dataclass(frozen=True)
class RuntimeAvailability:
    """Result of a runtime's availability probe."""

    runtime_id: str
    available: bool
    """``True`` when the runtime CAN be used right now (CLI on PATH +
    auth resolved, or HTTP endpoint reachable). ``False`` does NOT mean
    the runtime is broken — it means the user has to do something
    (install a CLI, log in, set an env var)."""
    implemented: bool
    """``True`` when the orchestrator can drive this runtime today.
    ``False`` for the four "registered but stubbed" runtimes — selecting
    them aborts with a helpful message instead of silently producing
    bogus PARTIALs."""
    notes: tuple[str, ...] = field(default_factory=tuple)
    """Operator-readable hints: what's missing, what to run to fix."""


@dataclass(frozen=True)
class RuntimeDescriptor:
    """One row in the registry."""

    runtime_id: RuntimeId
    summary: str
    """One-line description suitable for ``--list-runtimes`` output."""
    probe: Callable[[], RuntimeAvailability]
    """Closure that returns the current availability snapshot."""
    implemented: bool
    """Whether the orchestrator can actually drive this runtime now."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _which(name: str) -> str | None:
    """Cross-platform ``shutil.which`` that also checks ``.cmd``/``.exe`` on Windows."""

    found = shutil.which(name)
    if found is None and sys.platform == "win32":
        found = shutil.which(f"{name}.cmd") or shutil.which(f"{name}.exe")
    return found


_WIN_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _run(cmd: list[str], timeout: float = 3.0) -> subprocess.CompletedProcess[str] | None:
    """Run a short probe command with timeout; return None on failure.

    Forces UTF-8 with replacement so a Windows host whose stdout encoding
    is cp932 doesn't blow up the probe when ``gh auth status`` (or any
    other CLI we shell out to) emits a stray byte the JP locale cannot
    decode.
    """

    try:
        return subprocess.run(  # noqa: S603 — argv resolved via shutil.which
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            creationflags=_WIN_NO_WINDOW,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------


def _probe_claude() -> RuntimeAvailability:
    claude = _which("claude")
    if claude is None:
        return RuntimeAvailability(
            runtime_id="claude",
            available=False,
            implemented=True,
            notes=(
                "claude CLI not found on PATH.",
                "Install via `npm install -g @anthropic-ai/claude-code`.",
            ),
        )
    # ``claude auth status --json`` returns even when logged out, so we
    # treat a 0-exit + non-empty stdout as "wire is healthy" and let
    # ClaudeRunner surface auth errors at run time.
    proc = _run([claude, "auth", "status", "--json"])
    if proc is None or proc.returncode != 0:
        return RuntimeAvailability(
            runtime_id="claude",
            available=True,  # CLI is there; auth may or may not be
            implemented=True,
            notes=("claude CLI present; run `claude auth login` if needed.",),
        )
    return RuntimeAvailability(
        runtime_id="claude",
        available=True,
        implemented=True,
        notes=("claude CLI ready.",),
    )


def _probe_api() -> RuntimeAvailability:
    has_key = bool(os.environ.get("API_RUNNER_API_KEY"))
    notes = (
        "API_RUNNER_BASE_URL: "
        f"{os.environ.get('API_RUNNER_BASE_URL', 'https://openrouter.ai/api/v1')}",
        f"API_RUNNER_MODEL: {os.environ.get('API_RUNNER_MODEL', 'deepseek/deepseek-r1')}",
        "Set API_RUNNER_API_KEY to authenticate." if not has_key else "Key present.",
    )
    return RuntimeAvailability(
        runtime_id="api",
        available=has_key,
        implemented=True,
        notes=notes,
    )


def _probe_codex() -> RuntimeAvailability:
    codex = _which("codex")
    if codex is None:
        return RuntimeAvailability(
            runtime_id="codex",
            available=False,
            implemented=False,
            notes=(
                "codex CLI not found on PATH.",
                "Install via `npm install -g @openai/codex`.",
                "Note: orchestrator runner not yet implemented (Web chat works today).",
            ),
        )
    proc = _run([codex, "login", "status"])
    logged_in = bool(proc and "logged in" in (proc.stdout or "").lower()
                     and "not logged" not in (proc.stdout or "").lower())
    return RuntimeAvailability(
        runtime_id="codex",
        available=logged_in,
        implemented=False,
        notes=(
            ("codex CLI present; "
             + ("logged in." if logged_in else "run `codex login`.")),
            "Note: orchestrator runner not yet implemented (Web chat works today).",
        ),
    )


def _probe_gemini() -> RuntimeAvailability:
    gemini = _which("gemini")
    if gemini is None:
        return RuntimeAvailability(
            runtime_id="gemini",
            available=False,
            implemented=False,
            notes=(
                "gemini CLI not found on PATH.",
                "Install via `npm install -g @google/gemini-cli`.",
                "Note: orchestrator runner not yet implemented (Web chat works today).",
            ),
        )
    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    return RuntimeAvailability(
        runtime_id="gemini",
        available=has_key,
        implemented=False,
        notes=(
            "gemini CLI present.",
            ("GEMINI_API_KEY is set." if has_key else "Set GEMINI_API_KEY to authenticate."),
            "Note: orchestrator runner not yet implemented (Web chat works today).",
        ),
    )


def _probe_ollama() -> RuntimeAvailability:
    host = os.environ.get("OLLAMA_HOST", "https://ollama.com")
    cloud = "ollama.com" in host
    has_key = bool(os.environ.get("OLLAMA_API_KEY"))
    return RuntimeAvailability(
        runtime_id="ollama",
        available=(not cloud) or has_key,
        implemented=False,
        notes=(
            f"OLLAMA_HOST: {host}",
            (
                "OLLAMA_API_KEY is set."
                if has_key
                else (
                    "Cloud host requires OLLAMA_API_KEY; self-hosted (localhost) does not."
                )
            ),
            "Note: orchestrator runner not yet implemented (Web chat works today).",
        ),
    )


def _probe_copilot() -> RuntimeAvailability:
    gh = _which("gh")
    if gh is None:
        return RuntimeAvailability(
            runtime_id="copilot",
            available=False,
            implemented=False,
            notes=(
                "gh CLI not found on PATH.",
                "Install GitHub CLI from https://cli.github.com/.",
                "Note: orchestrator runner not yet implemented (Web chat works today).",
            ),
        )
    proc = _run([gh, "auth", "status"])
    logged_in = bool(
        proc
        and proc.returncode == 0
        and "logged in" in (proc.stderr or proc.stdout or "").lower()
    )
    return RuntimeAvailability(
        runtime_id="copilot",
        available=logged_in,
        implemented=False,
        notes=(
            ("gh CLI present; "
             + ("logged in." if logged_in else "run `gh auth login`.")),
            "Copilot subscription required.",
            "Note: orchestrator runner not yet implemented (Web chat works today).",
        ),
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


REGISTRY: dict[str, RuntimeDescriptor] = {
    "claude": RuntimeDescriptor(
        runtime_id="claude",
        summary="Anthropic claude CLI (stream-json). Production audit path.",
        probe=_probe_claude,
        implemented=True,
    ),
    "api": RuntimeDescriptor(
        runtime_id="api",
        summary="OpenRouter-style HTTP (OPENAI_API_KEY-compatible). Non-Claude models.",
        probe=_probe_api,
        implemented=True,
    ),
    "codex": RuntimeDescriptor(
        runtime_id="codex",
        summary="OpenAI codex CLI (`codex exec --json`). Registered but stubbed.",
        probe=_probe_codex,
        implemented=False,
    ),
    "gemini": RuntimeDescriptor(
        runtime_id="gemini",
        summary="Google gemini CLI (`gemini -p --output-format stream-json`). Registered but stubbed.",
        probe=_probe_gemini,
        implemented=False,
    ),
    "ollama": RuntimeDescriptor(
        runtime_id="ollama",
        summary="Ollama HTTP (`/api/chat`, cloud or self-hosted). Registered but stubbed.",
        probe=_probe_ollama,
        implemented=False,
    ),
    "copilot": RuntimeDescriptor(
        runtime_id="copilot",
        summary="GitHub Copilot CLI (`gh copilot suggest`, no streaming). Registered but stubbed.",
        probe=_probe_copilot,
        implemented=False,
    ),
}


def all_runtime_ids() -> tuple[str, ...]:
    return tuple(REGISTRY.keys())


def get(runtime_id: str) -> RuntimeDescriptor:
    """Return the descriptor for ``runtime_id`` or raise ``ValueError``."""

    descr = REGISTRY.get(runtime_id)
    if descr is None:
        raise ValueError(
            f"unknown runtime id: {runtime_id!r}. "
            f"Known: {', '.join(all_runtime_ids())}."
        )
    return descr


def probe(runtime_id: str) -> RuntimeAvailability:
    """Return availability for ``runtime_id`` (CLI present, auth, …)."""

    return get(runtime_id).probe()


def list_runtimes() -> list[dict[str, Any]]:
    """Return a JSON-friendly snapshot of every registered runtime."""

    out: list[dict[str, Any]] = []
    for runtime_id, descr in REGISTRY.items():
        avail = descr.probe()
        out.append(
            {
                "runtime_id": runtime_id,
                "summary": descr.summary,
                "implemented": descr.implemented,
                "available": avail.available,
                "notes": list(avail.notes),
            }
        )
    return out


def resolve_active() -> str:
    """Return the currently-selected runtime id from the environment.

    The orchestrator's :mod:`base` reads ``ORCHESTRATOR_RUNNER`` directly;
    this helper centralises the default + validation so we never
    silently fall back to ``claude`` on a typo'd env var.
    """

    raw = os.environ.get("ORCHESTRATOR_RUNNER", "claude").strip()
    if raw == "":
        return "claude"
    if raw not in REGISTRY:
        # Don't raise — keep the boot path tolerant; just warn loudly so
        # the user notices.
        import warnings

        warnings.warn(
            f"ORCHESTRATOR_RUNNER={raw!r} is not a known runtime "
            f"(known: {', '.join(all_runtime_ids())}). Falling back to 'claude'.",
            stacklevel=2,
        )
        return "claude"
    return raw
