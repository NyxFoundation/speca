"""Runtime preferences API.

Lets the SPA read / write the user's chat-runtime preference (the choice
between ``claude``, ``codex``, and ``ollama``) plus ancillary settings
like the Ollama host and per-runtime default models.

Secrets (API keys) do NOT flow through this router. The Anthropic /
OpenAI / Ollama keys live in:

* ``ANTHROPIC_API_KEY`` env var or ``~/.claude/.credentials.json`` (handled
  by the existing ``/api/auth`` router).
* ``OPENAI_API_KEY`` env var or ``codex login --with-api-key`` (handled
  by the official ``codex`` CLI).
* ``OLLAMA_API_KEY`` env var (used by :mod:`chat_runtime_ollama`).

Endpoints here only surface availability flags / hints so the SPA can
render a "you need to set $OLLAMA_API_KEY to use Ollama Cloud" banner
without us teaching this router how to write process env vars.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import runtime_preferences

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


RuntimeLit = Literal["claude", "codex", "gemini", "ollama", "copilot"]


class RuntimeView(BaseModel):
    """Outbound shape — never includes secret material."""

    runtime: RuntimeLit
    ollama_host: str
    claude_model: str | None
    codex_model: str | None
    gemini_model: str | None
    ollama_model: str | None
    # Availability hints derived from the host environment. Each
    # ``<runtime>_available`` is true when the CLI / endpoint can be
    # spawned / reached; ``<runtime>_logged_in`` (when applicable) is
    # true when the runtime believes the user is authenticated.
    codex_cli_available: bool
    codex_logged_in: bool
    gemini_cli_available: bool
    gemini_api_key_present: bool
    copilot_cli_available: bool
    ollama_api_key_present: bool


class RuntimeUpdate(BaseModel):
    """Inbound shape — every field is optional so the SPA can PATCH atomically."""

    runtime: RuntimeLit | None = None
    ollama_host: str | None = Field(default=None, max_length=512)
    claude_model: str | None = Field(default=None, max_length=128)
    codex_model: str | None = Field(default=None, max_length=128)
    gemini_model: str | None = Field(default=None, max_length=128)
    ollama_model: str | None = Field(default=None, max_length=128)


def _which(name: str) -> str | None:
    found = shutil.which(name)
    if found is None and sys.platform == "win32":
        found = shutil.which(f"{name}.cmd") or shutil.which(f"{name}.exe")
    return found


_WIN_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _codex_status() -> tuple[bool, bool]:
    """Return ``(cli_available, logged_in)`` for codex."""

    codex_bin = _which("codex")
    if codex_bin is None:
        return False, False
    try:
        proc = subprocess.run(  # noqa: S603 — via shutil.which
            [codex_bin, "login", "status"],
            capture_output=True,
            text=True,
            timeout=3,
            shell=False,
            creationflags=_WIN_NO_WINDOW,
        )
    except (subprocess.TimeoutExpired, OSError):
        return True, False
    text = (proc.stdout or "").lower()
    return True, ("logged in" in text and "not logged" not in text)


def _gemini_status() -> bool:
    """Return whether the gemini CLI is on PATH."""

    return _which("gemini") is not None


def _copilot_status() -> bool:
    """Return whether the gh CLI is installed (Copilot is downloaded on demand)."""

    return _which("gh") is not None


def _view_of(prefs: runtime_preferences.RuntimePreferences) -> RuntimeView:
    codex_avail, codex_in = _codex_status()
    return RuntimeView(
        runtime=prefs.runtime,
        ollama_host=prefs.ollama_host,
        claude_model=prefs.claude_model,
        codex_model=prefs.codex_model,
        gemini_model=prefs.gemini_model,
        ollama_model=prefs.ollama_model,
        codex_cli_available=codex_avail,
        codex_logged_in=codex_in,
        gemini_cli_available=_gemini_status(),
        gemini_api_key_present=bool(os.environ.get("GEMINI_API_KEY")),
        copilot_cli_available=_copilot_status(),
        ollama_api_key_present=bool(os.environ.get("OLLAMA_API_KEY")),
    )


@router.get("", response_model=RuntimeView)
def get_runtime() -> RuntimeView:
    """Read current preferences + availability flags."""

    return _view_of(runtime_preferences.load())


@router.put("", response_model=RuntimeView)
def update_runtime(body: RuntimeUpdate) -> RuntimeView:
    """Patch one or more preference fields (PUT acts as PATCH here)."""

    payload: dict[str, Any] = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(
            status_code=400, detail="empty body — at least one field required"
        )
    new = runtime_preferences.patch(payload)
    return _view_of(new)
