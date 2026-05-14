"""User-selectable runtime preferences for the Chat slice.

CLI spec issue #3 plus the operator memo "speca multi-agent CLI" anticipate
the SPECA web UI driving more than just the Anthropic ``claude`` CLI. This
module is the persistence + selection layer that lets users pick between:

* ``claude`` — the existing path (SDK for API-key users, CLI subprocess
  for claude.ai OAuth subscribers).
* ``codex`` — OpenAI's ``codex`` CLI. Supports both API key and ChatGPT
  plan OAuth (the CLI handles both natively; we just shell out).
* ``ollama`` — Ollama. Talks HTTP, can hit ``https://ollama.com`` (cloud
  with API key) or a self-hosted endpoint (``http://localhost:11434``).

Settings persist to ``~/.speca/runtime.json`` so the choice survives
process restarts. The file is plain JSON, never holds secrets — Ollama's
host is fine in cleartext; the API key lands in the env (``OLLAMA_API_KEY``)
or the dedicated credentials file.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


RuntimeId = Literal["claude", "codex", "gemini", "ollama", "copilot"]
ALL_RUNTIMES: tuple[RuntimeId, ...] = (
    "claude",
    "codex",
    "gemini",
    "ollama",
    "copilot",
)


class RuntimePreferences(BaseModel):
    """User-selectable runtime + ancillary settings."""

    model_config = ConfigDict(extra="ignore")

    runtime: RuntimeId = Field(default="claude")
    # Ollama host, e.g. ``https://ollama.com`` or ``http://localhost:11434``.
    # Stored even when ``runtime != "ollama"`` so a one-click switch back
    # picks up the previous configuration without re-typing.
    ollama_host: str = Field(default="https://ollama.com")
    # Default model id for each runtime; ``None`` means "let the runtime
    # decide" (claude → DEFAULT_MODEL, codex → CLI default, ollama → first
    # available model on the host).
    claude_model: str | None = None
    codex_model: str | None = None
    gemini_model: str | None = None
    ollama_model: str | None = None
    # Copilot has no model selector — the gh copilot CLI picks for us.


_DEFAULT_PATH = Path.home() / ".speca" / "runtime.json"


def _resolve_path(path: Path | None) -> Path:
    return path if path is not None else _DEFAULT_PATH


def load(path: Path | None = None) -> RuntimePreferences:
    """Read preferences from disk; missing / corrupt → defaults."""

    target = _resolve_path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return RuntimePreferences()
    except OSError as exc:
        logger.warning("runtime_prefs: read failed (%s) — using defaults", exc)
        return RuntimePreferences()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "runtime_prefs: %s is not valid JSON (%s) — using defaults", target, exc
        )
        return RuntimePreferences()

    try:
        return RuntimePreferences.model_validate(data)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("runtime_prefs: schema mismatch (%s) — using defaults", exc)
        return RuntimePreferences()


def save(prefs: RuntimePreferences, path: Path | None = None) -> None:
    """Persist preferences atomically (tmp + rename)."""

    target = _resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = prefs.model_dump(mode="json")

    fd, tmp_name = tempfile.mkstemp(
        prefix=".runtime.", suffix=".tmp", dir=str(target.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass
        raise


def patch(
    update: dict[str, Any], path: Path | None = None
) -> RuntimePreferences:
    """Merge ``update`` into current prefs and persist."""

    current = load(path).model_dump()
    current.update({k: v for k, v in update.items() if v is not None})
    new = RuntimePreferences.model_validate(current)
    save(new, path)
    return new
