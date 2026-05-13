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

Retention: there is no automatic GC. Logs grow proportional to API turns
and accumulate forever under ``.speca/runs/``. The ``speca corpus gc``
subcommand (out of scope for this PR, tracked under issue #32 follow-ups)
will provide the cleanup story; until then, operators should periodically
prune ``.speca/runs/`` manually.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
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

        # Eagerly create the directory skeleton so callers don't have to worry.
        # Done before manifest load so the load path can access run_dir.
        for sub in ("inputs", "prompts", "phases", "final"):
            (self.run_dir / sub).mkdir(parents=True, exist_ok=True)

        # Per-phase last-seen cumulative cost. record_cost receives a
        # monotonically increasing cumulative figure from CostTracker after
        # every batch; we add only the delta so the manifest total reflects
        # the true cumulative, not sum-of-cumulatives.
        #
        # NOTE: when resuming an existing manifest (cross-invocation re-entry
        # with the same SPECA_RUN_ID), the current process starts a fresh
        # CostTracker per phase, so prev=0 on the first snapshot of the
        # second invocation is correct — the delta machinery then accumulates
        # this invocation's contribution on top of the loaded total.
        self._phase_cost_seen: dict[str, float] = {}

        # Manifest is kept in memory and written atomically on finalize().
        # If an existing manifest.json is present (re-entry with the same
        # SPECA_RUN_ID across separate `--phase` invocations), load it so
        # phases_completed / cost_usd_total / model / prompt_shas / etc.
        # accumulate across invocations instead of being overwritten.
        existing_path = self.run_dir / "manifest.json"
        loaded = False
        if existing_path.exists():
            try:
                with open(existing_path, encoding="utf-8") as f:
                    existing = json.load(f)
                self._manifest = RunManifest.model_validate(existing)
                # Mid-run we don't want a stale ended_at confusing readers
                # — clear it so this invocation's finalize() sets a fresh one.
                self._manifest.ended_at = None
                loaded = True
            except (OSError, ValueError) as e:
                # Corrupt / unreadable manifest — fall through to a fresh one
                # but warn so the operator notices the lost provenance.
                print(
                    f"[Archiver] warning: existing manifest at {existing_path} "
                    f"is unreadable ({e}); starting a fresh manifest.",
                    file=sys.stderr,
                )

        if not loaded:
            # started_at uses timezone-aware UTC so it round-trips through JSON.
            self._manifest = RunManifest(
                run_id=run_id,
                started_at=datetime.now(timezone.utc),
            )

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

    def record_graphs_dir(self, phase: str, src_dir: Path | str) -> int:
        """Recursively mirror a batch graphs directory into the archive.

        Used by Phase 01b's collector: subgraphs (``.mmd`` + any sibling
        files) live under ``outputs/graphs/batch_w<W>b<B>_<ts>/<spec>/`` and
        are written by the worker (not by the collector itself), so the
        usual ``record_partial`` hook doesn't reach them. This walks the
        batch directory and hard-links every file into
        ``phases/<phase>/graphs/<batch-dir-name>/<relative-path>``.

        Returns the number of files mirrored (useful for tests / metrics).
        """
        src = Path(src_dir)
        if not src.exists() or not src.is_dir():
            return 0
        dest_root = self.run_dir / "phases" / phase / "graphs" / src.name
        mirrored = 0
        for path in src.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(src)
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._mirror_file(path, dest)
            mirrored += 1
        return mirrored

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

        ``snapshot['total_cost_usd']`` is treated as the **cumulative** cost
        for *this phase* (CostTracker is per-phase and monotonically
        increasing). The manifest total is updated by the delta since the
        last snapshot for this phase, so multi-batch invocations don't
        compound (N batches would otherwise over-count by a factor of
        ~N(N+1)/2).
        """
        cost_dir = self.run_dir / "phases" / phase
        cost_dir.mkdir(parents=True, exist_ok=True)
        cost_path = cost_dir / "cost.json"

        usd = float(snapshot.get("total_cost_usd", 0.0))
        # Hold the lock across the file write *and* the manifest mutation:
        # on Windows, concurrent ``os.replace`` calls into the same
        # destination can fail with ``PermissionError(13)`` even when each
        # writer uses a unique temp file. Serialising the rename also keeps
        # cost.json and the in-memory manifest mutually consistent.
        with self._lock:
            _atomic_write_json(cost_path, snapshot)

            # CostTracker reports a per-phase cumulative figure that is
            # monotonically non-decreasing. We add only the positive delta
            # since the last seen snapshot, so multi-batch invocations don't
            # compound. `max(0, ...)` is belt-and-braces: if a snapshot ever
            # regresses (a bug elsewhere), we refuse to subtract from the
            # manifest rather than silently masking it.
            prev = self._phase_cost_seen.get(phase, 0.0)
            delta = max(0.0, usd - prev)
            self._phase_cost_seen[phase] = max(prev, usd)
            self._manifest.cost_usd_total += delta
            if phase not in self._manifest.phases_completed:
                self._manifest.phases_completed.append(phase)

    def set_env_snapshot(self, env_data: dict[str, Any]) -> None:
        """Write ``inputs/env.json`` with a snapshot of the run environment."""
        env_path = self.run_dir / "inputs" / "env.json"
        _atomic_write_json(env_path, env_data)

    def set_spec_sources(self, urls: list[str]) -> None:
        """Record spec source URLs in the manifest (replace)."""
        with self._lock:
            self._manifest.spec_sources = list(urls)

    def add_spec_sources(self, urls: list[str]) -> None:
        """Merge spec source URLs into the manifest, preserving insertion order.

        Use this instead of ``set_spec_sources`` when the archive may already
        carry sources from a prior invocation (re-entry with the same
        ``SPECA_RUN_ID``). Duplicates are deduplicated.
        """
        with self._lock:
            seen = {u: None for u in self._manifest.spec_sources}
            for u in urls:
                if u not in seen:
                    seen[u] = None
            self._manifest.spec_sources = list(seen.keys())

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
        """Hard-link *src* to *dest*; fall back to copy2 on OSError.

        Short-circuits when *dest* already exists (the archive is
        append-only, so re-mirroring the same partial on a re-run is a
        no-op rather than a noisy copy2 overwrite).
        """
        if not src.exists():
            print(
                f"[Archiver] warning: source file not found, skipping: {src}",
                file=sys.stderr,
            )
            return
        if dest.exists():
            return
        try:
            os.link(str(src), str(dest))
        except FileExistsError:
            # Lost a race against a concurrent writer for the same (phase,
            # filename) — they already produced a valid hard-link. Don't
            # downgrade it to a copy.
            return
        except OSError:
            # Cross-fs, Windows ACL, etc. — use copy. Re-check existence to
            # avoid clobbering a winning concurrent hard-link with a copy.
            if dest.exists():
                return
            shutil.copy2(str(src), str(dest))


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _atomic_write_json(path: Path, data: Any) -> None:
    """Write *data* as JSON to *path* atomically via a unique temp file.

    The temp filename is unique per call (``tempfile.mkstemp`` in the same
    directory), so concurrent writers to the same *path* never share an
    intermediate file. The final rename (``os.replace``) is atomic on POSIX
    and Windows, so a partial write is never visible to readers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # tempfile.mkstemp creates the file with mode 0600 and an O_EXCL flag,
    # guaranteeing the path is unique across processes/threads.
    fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp = Path(tmp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
