"""
Archiver Module — Per-run trace archive substrate.

Creates an append-only directory under ``.speca/runs/<run-id>/`` that
mirrors every partial result, log, rendered prompt, and cost snapshot
produced during a pipeline run.  Hard-links (``os.link``) are used when
source and destination share a filesystem, falling back to ``shutil.copy2``
on ``OSError`` (cross-fs, Windows ACL restrictions, etc.).

The archive is entirely optional: all callers check ``if archiver is not None``
before calling any method, so the existing behaviour is completely unchanged
when the archiver is disabled via ``--no-archive``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import RunManifest


class Archiver:
    """Writes a per-run trace archive to ``<root>/<run_id>/``.

    Constructor:
        run_id: Unique identifier for this run (``<ts>-<sha>-<slug>``).
        root:   Archive root directory (e.g. ``<repo>/.speca/runs``).

    All public methods are **thread-safe**: a single ``threading.Lock``
    serialises manifest mutations.  File I/O itself (hard-link / copy) does
    not require the lock.
    """

    def __init__(self, run_id: str, root: Path | str) -> None:
        self.run_id = run_id
        self.root = Path(root)
        self.run_dir = self.root / run_id
        self._lock = threading.Lock()
        self._finalized = False

        # Manifest is kept in memory and written atomically on finalize().
        # started_at uses timezone-aware UTC so it round-trips through JSON.
        self._manifest = RunManifest(
            run_id=run_id,
            started_at=datetime.now(timezone.utc),
        )

        # Eagerly create the directory skeleton so callers don't have to worry.
        for sub in ("inputs", "prompts", "phases", "final"):
            (self.run_dir / sub).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_partial(self, phase: str, path: Path | str) -> None:
        """Mirror a partial-result file into ``phases/<phase>/partials/``."""
        src = Path(path)
        dest_dir = self.run_dir / "phases" / phase / "partials"
        dest_dir.mkdir(parents=True, exist_ok=True)
        self._mirror_file(src, dest_dir / src.name)

    def record_log(self, phase: str, path: Path | str) -> None:
        """Mirror a stream-json log file into ``phases/<phase>/logs/``."""
        src = Path(path)
        dest_dir = self.run_dir / "phases" / phase / "logs"
        dest_dir.mkdir(parents=True, exist_ok=True)
        self._mirror_file(src, dest_dir / src.name)

    def record_prompt(self, phase: str, text: str) -> None:
        """Write the rendered prompt text to ``prompts/<phase>.md``.

        Also records the SHA-256 of the prompt in the manifest so
        downstream tooling can detect prompt changes across runs.
        """
        prompt_path = self.run_dir / "prompts" / f"{phase}.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(text, encoding="utf-8")

        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            self._manifest.prompt_shas[phase] = sha

    def record_cost(self, phase: str, snapshot: dict[str, Any]) -> None:
        """Write a cost snapshot to ``phases/<phase>/cost.json``.

        Also accumulates ``total_cost_usd`` into the manifest.
        """
        cost_dir = self.run_dir / "phases" / phase
        cost_dir.mkdir(parents=True, exist_ok=True)
        cost_path = cost_dir / "cost.json"

        # Atomic write so concurrent readers always see a complete file.
        _atomic_write_json(cost_path, snapshot)

        usd = float(snapshot.get("total_cost_usd", 0.0))
        with self._lock:
            self._manifest.cost_usd_total += usd
            if phase not in self._manifest.phases_completed:
                self._manifest.phases_completed.append(phase)

    def set_env_snapshot(self, env_data: dict[str, Any]) -> None:
        """Write ``inputs/env.json`` with a snapshot of the run environment."""
        env_path = self.run_dir / "inputs" / "env.json"
        _atomic_write_json(env_path, env_data)

    def set_spec_sources(self, urls: list[str]) -> None:
        """Record spec source URLs in the manifest."""
        with self._lock:
            self._manifest.spec_sources = list(urls)

    def set_commit(self, sha: str) -> None:
        """Record the speca git commit in the manifest."""
        with self._lock:
            self._manifest.speca_commit = sha

    def set_model(self, phase: str, model_name: str) -> None:
        """Record the model used for a phase in the manifest."""
        with self._lock:
            self._manifest.model[phase] = model_name

    def finalize(self, status: str, *, reason: str = "") -> None:
        """Write the final manifest.json and mark the archive as complete.

        Idempotent: subsequent calls are silently ignored (the first call
        wins).  ``status`` should be ``"ok"`` or ``"error"``.
        """
        with self._lock:
            if self._finalized:
                return
            self._finalized = True
            self._manifest.ended_at = datetime.now(timezone.utc)
            if reason:
                self._manifest.notes = f"{status}: {reason}"
            else:
                self._manifest.notes = status
            manifest_dict = self._manifest.model_dump(mode="json")

        manifest_path = self.run_dir / "manifest.json"
        _atomic_write_json(manifest_path, manifest_dict)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _mirror_file(self, src: Path, dest: Path) -> None:
        """Hard-link *src* to *dest*; fall back to copy2 on OSError."""
        if not src.exists():
            print(
                f"[Archiver] warning: source file not found, skipping: {src}",
                file=sys.stderr,
            )
            return
        try:
            os.link(str(src), str(dest))
        except OSError:
            # Cross-fs, Windows ACL, or dest already exists — use copy.
            shutil.copy2(str(src), str(dest))


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _atomic_write_json(path: Path, data: Any) -> None:
    """Write *data* as JSON to *path* atomically via a temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
