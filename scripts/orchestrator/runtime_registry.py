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
* ``copilot`` — GitHub Copilot agentic CLI (``copilot`` from ``@github/copilot``).

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
    """Orchestrator codex path goes through CodexAPIRunner → OpenAI Chat API.

    We do NOT require the ``codex`` CLI to be installed; the orchestrator
    only needs ``OPENAI_API_KEY`` to authenticate against
    ``api.openai.com/v1``. The CLI is still useful for chat-side flows
    (see web/server/services/chat_runtime_codex.py) but is optional here.
    """

    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    codex_cli = _which("codex")
    notes_list = [
        "Routes through CodexAPIRunner -> https://api.openai.com/v1 (OpenAI Chat API).",
        f"OPENAI_MODEL: {os.environ.get('OPENAI_MODEL', 'gpt-4o')}",
        "OPENAI_API_KEY is set." if has_key else "Set OPENAI_API_KEY to authenticate.",
    ]
    if codex_cli is not None:
        proc = _run([codex_cli, "login", "status"])
        logged_in = bool(
            proc
            and "logged in" in (proc.stdout or "").lower()
            and "not logged" not in (proc.stdout or "").lower()
        )
        notes_list.append(
            f"codex CLI on PATH ({'logged in' if logged_in else 'logged out'}) — only used by Web chat side."
        )
    return RuntimeAvailability(
        runtime_id="codex",
        available=has_key,
        implemented=True,
        notes=tuple(notes_list),
    )


def _probe_gemini() -> RuntimeAvailability:
    """Orchestrator gemini path uses Google's OpenAI compatibility layer.

    The optional ``gemini`` CLI is only used by Web chat; the orchestrator
    speaks directly to ``generativelanguage.googleapis.com``.
    """

    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    gemini_cli = _which("gemini")
    notes_list = [
        "Routes through GeminiAPIRunner -> Google's OpenAI compatibility endpoint.",
        f"GEMINI_MODEL: {os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')}",
        "GEMINI_API_KEY is set." if has_key else "Set GEMINI_API_KEY to authenticate.",
    ]
    if gemini_cli is not None:
        notes_list.append("gemini CLI on PATH — only used by Web chat side.")
    return RuntimeAvailability(
        runtime_id="gemini",
        available=has_key,
        implemented=True,
        notes=tuple(notes_list),
    )


def _probe_ollama() -> RuntimeAvailability:
    """Orchestrator ollama path uses Ollama's OpenAI-compatible endpoint.

    Self-hosted (``http://localhost:11434``) does not need a key; cloud
    (``https://ollama.com``) does.
    """

    host = os.environ.get("OLLAMA_HOST", "https://ollama.com")
    cloud = "ollama.com" in host
    has_key = bool(os.environ.get("OLLAMA_API_KEY"))
    return RuntimeAvailability(
        runtime_id="ollama",
        available=(not cloud) or has_key,
        implemented=True,
        notes=(
            "Routes through OllamaAPIRunner -> <OLLAMA_HOST>/v1/chat/completions.",
            f"OLLAMA_HOST: {host}",
            f"OLLAMA_MODEL: {os.environ.get('OLLAMA_MODEL', 'llama3.2')}",
            (
                "OLLAMA_API_KEY is set."
                if has_key
                else "Cloud host requires OLLAMA_API_KEY; self-hosted (localhost) does not."
            ),
        ),
    )


def _probe_copilot() -> RuntimeAvailability:
    """Probe the agentic ``copilot`` CLI (``@github/copilot``).

    The Web chat path now uses this CLI directly (replacing the older
    ``gh copilot suggest`` shim). The orchestrator-side runner is still
    a follow-up — it needs a CopilotRunner subclass that parses
    copilot's JSONL events and threads them through the existing cost
    tracker / circuit breaker. The CLI itself fully supports it, so
    ``implemented=False`` is a deliberate scope choice, not a
    fundamental limitation like before.
    """

    bin_ = _which("copilot")
    if bin_ is None:
        return RuntimeAvailability(
            runtime_id="copilot",
            available=False,
            implemented=False,
            notes=(
                "copilot CLI not found on PATH.",
                "Install via `npm install -g @github/copilot`, then run "
                "`copilot` once interactively to OAuth into GitHub.",
                "Note: orchestrator runner not yet implemented (Web chat works today).",
            ),
        )
    return RuntimeAvailability(
        runtime_id="copilot",
        available=True,
        implemented=False,
        notes=(
            "copilot CLI on PATH.",
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
        summary="OpenAI Chat API (codex CLI authenticates against this). Tool-calling enabled.",
        probe=_probe_codex,
        implemented=True,
    ),
    "gemini": RuntimeDescriptor(
        runtime_id="gemini",
        summary="Google Gemini via its OpenAI compatibility endpoint. Tool-calling enabled.",
        probe=_probe_gemini,
        implemented=True,
    ),
    "ollama": RuntimeDescriptor(
        runtime_id="ollama",
        summary="Ollama via /v1/chat/completions (cloud or self-hosted). Tool-calling enabled.",
        probe=_probe_ollama,
        implemented=True,
    ),
    "copilot": RuntimeDescriptor(
        runtime_id="copilot",
        summary="GitHub Copilot agentic CLI (`copilot -p --output-format json`). Web chat works today; orchestrator runner is a follow-up.",
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
