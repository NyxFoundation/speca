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
from pathlib import Path
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
    # Google Application Default Credentials path — Gemini CLI accepts
    # an OAuth-managed token written by `gcloud auth application-default
    # login`, enabled by setting ``GOOGLE_GENAI_USE_GCA=true``. The
    # SPA's runtime selector treats this as a valid auth source so
    # users on a Google personal account do not need to mint an API key.
    gemini_adc_available: bool
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


def _gemini_adc_available() -> bool:
    """Return True when Google Application Default Credentials are usable.

    Two conditions must both hold:

    1. ``GOOGLE_GENAI_USE_GCA`` is truthy in the server environment.
       Gemini's auth code only consults the ADC when this opt-in is set;
       otherwise it ignores the credentials file entirely.
    2. The ADC JSON file exists (the canonical location is
       ``$CLOUDSDK_CONFIG/application_default_credentials.json``, falling
       back to ``~/.config/gcloud/application_default_credentials.json``
       on POSIX or ``%APPDATA%/gcloud/application_default_credentials.json``
       on Windows).

    Both checks are file-existence only — we never read the token contents
    (the SPA must not see secret material). A user who has run
    ``gcloud auth application-default login`` and exported
    ``GOOGLE_GENAI_USE_GCA=true`` in the shell that started ``speca-web``
    will see ``gemini_adc_available=true`` in the Settings page.
    """

    flag = (os.environ.get("GOOGLE_GENAI_USE_GCA") or "").strip().lower()
    if flag in ("", "0", "false", "no", "off"):
        return False

    # Cross-platform ADC file resolution mirrors gcloud's own search order.
    candidate_paths: list[Path] = []
    cloudsdk = os.environ.get("CLOUDSDK_CONFIG")
    if cloudsdk:
        candidate_paths.append(Path(cloudsdk) / "application_default_credentials.json")
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidate_paths.append(
                Path(appdata) / "gcloud" / "application_default_credentials.json"
            )
    candidate_paths.append(
        Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    )

    return any(p.exists() for p in candidate_paths)


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
        gemini_adc_available=_gemini_adc_available(),
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
