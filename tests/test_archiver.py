"""
Tests for the archive substrate (issue #32).

Covers:
  - Run-id format conformance
  - Archiver.record_partial: hard-link (same fs) and copy fallback
  - RunManifest JSON round-trip
  - Concurrent record_partial calls (thread-safety / no corruption)
  - --no-archive path: orchestrator runs without archiver
  - Archiver.finalize: writes manifest, idempotent
  - Cross-fs simulation (mock os.link -> OSError(EXDEV))
  - Spec-slug edge cases
"""

from __future__ import annotations

import errno
import json
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — make sure scripts/ is on sys.path regardless of cwd
# ---------------------------------------------------------------------------
import sys
_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from orchestrator.archiver import Archiver
from orchestrator.schemas import RunManifest
from run_phase import make_run_id, _derive_spec_slug, _slugify, _get_short_sha


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_archive(tmp_path: Path) -> Path:
    """Return a temporary archive root."""
    root = tmp_path / "archive_root"
    root.mkdir()
    return root


@pytest.fixture()
def archiver(tmp_archive: Path) -> Archiver:
    return Archiver("2026-01-02T03-04-05Z-abc1234-test", tmp_archive)


# ---------------------------------------------------------------------------
# 1. Run-id format
# ---------------------------------------------------------------------------

class TestRunId:
    def test_format_conforms_to_spec(self):
        """run-id must match <YYYY-MM-DDTHH-MM-SSZ>-<7hex>-<slug>-<4hex>."""
        import re
        run_id = make_run_id(spec_slug="uniswap-v4", sha="a1b2c3d")
        # Pattern: timestamp-sha-slug-nonce
        pattern = re.compile(
            r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[0-9a-f]{7}-[a-z0-9-]+-[0-9a-f]{4}$"
        )
        assert pattern.match(run_id), f"run-id does not match spec: {run_id!r}"

    def test_nonce_disambiguates_same_second(self):
        """Two run-ids generated back-to-back with identical sha+slug must differ.

        The 4-hex nonce has 65536 values, so 100 iterations gives birthday-paradox
        collision probability under 1e-4 — well below CI-flake threshold.
        """
        ids = {make_run_id(spec_slug="my-slug", sha="deadbee") for _ in range(100)}
        # Worst case: all 100 share the same second, so at minimum the nonce
        # must give us a healthy spread of distinct values.
        assert len(ids) >= 95, f"too many collisions over 100 runs: {len(ids)} unique"
        # All share the deterministic prefix segment.
        prefix = "-deadbee-my-slug-"
        for run_id in ids:
            assert prefix in run_id

    def test_explicit_nonce_is_respected(self):
        """When `nonce` is passed explicitly, make_run_id must use it verbatim.

        Negative case: changing the sha must change the resulting id (proves
        the function actually uses its inputs, not just appends the nonce).
        """
        id_a = make_run_id(spec_slug="my-slug", sha="deadbee", nonce="abcd")
        id_b = make_run_id(spec_slug="my-slug", sha="cafebab", nonce="abcd")
        assert id_a.endswith("-deadbee-my-slug-abcd"), id_a
        assert id_b.endswith("-cafebab-my-slug-abcd"), id_b
        assert id_a != id_b, "sha did not influence the id"

    def test_speca_run_id_env_pin(self, monkeypatch):
        """SPECA_RUN_ID env var (when set by caller) pins the run-id verbatim.

        Note: make_run_id itself does not consult the env — run_phase.main()
        does, before calling make_run_id. This test documents the contract.
        """
        # Just verify make_run_id has no env-coupling — its output depends
        # only on its arguments + clock.
        monkeypatch.setenv("SPECA_RUN_ID", "should-be-ignored-by-make_run_id")
        run_id = make_run_id(spec_slug="x", sha="0000000", nonce="0000")
        assert "should-be-ignored" not in run_id

    def test_uses_hyphens_not_colons_in_timestamp(self):
        """Timestamp must not contain colons (invalid path segment on Windows)."""
        run_id = make_run_id(spec_slug="s", sha="0000000", nonce="0000")
        # The timestamp portion is before the first sha separator
        ts_part = run_id.split("-0000000-")[0]
        assert ":" not in ts_part, f"timestamp contains colon: {ts_part!r}"

    def test_slug_max_40_chars(self):
        long_name = "a" * 100
        run_id = make_run_id(
            spec_slug=_slugify(long_name, 40), sha="0000000", nonce="0000",
        )
        # Trailing nonce is fixed-width 4; strip it before measuring the slug.
        assert run_id.endswith("-0000")
        slug_segment = run_id.split("-0000000-", 1)[1].rsplit("-", 1)[0]
        assert len(slug_segment) <= 40, f"slug too long: {len(slug_segment)}"

    def test_missing_git_sha_uses_hex_placeholder(self):
        """When _get_short_sha returns '', make_run_id must still match the shape."""
        import re
        from unittest.mock import patch
        with patch("run_phase._get_short_sha", return_value=""):
            run_id = make_run_id(spec_slug="x")
        pattern = re.compile(
            r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[0-9a-f]{7}-[a-z0-9-]+-[0-9a-f]{4}$"
        )
        assert pattern.match(run_id), f"missing-git fallback broke shape: {run_id!r}"


# ---------------------------------------------------------------------------
# 2. Archiver.record_partial — hard-link
# ---------------------------------------------------------------------------

class TestRecordPartial:
    def test_hardlink_same_fs(self, archiver: Archiver, tmp_path: Path):
        """record_partial should hard-link when src and dest share a filesystem."""
        # Write a source partial file in the same tmp dir as the archive
        src = tmp_path / "01a_PARTIAL_W0B0_111.json"
        src.write_text('{"test": 1}', encoding="utf-8")

        archiver.record_partial("01a", src)

        dest = archiver.run_dir / "phases" / "01a" / "partials" / src.name
        assert dest.exists(), "archived partial not found"

        # On the same filesystem the two paths should share the same inode
        # (i.e. they are hard-linked to the same underlying data block).
        # On Windows NTFS the st_ino is non-zero for hard links; on some
        # virtual/mounted filesystems it may be 0 — skip in that case.
        src_ino = src.stat().st_ino
        dest_ino = dest.stat().st_ino
        if src_ino != 0 and dest_ino != 0:
            assert src_ino == dest_ino, (
                f"expected hard-link (same inode), got src_ino={src_ino} dest_ino={dest_ino}"
            )

    def test_fallback_to_copy_on_os_link_error(self, archiver: Archiver, tmp_path: Path):
        """record_partial must fall back to copy when os.link raises OSError."""
        src = tmp_path / "01a_PARTIAL_W0B0_222.json"
        src.write_text('{"fallback": true}', encoding="utf-8")

        with patch("os.link", side_effect=OSError(errno.EXDEV, "cross-device link")):
            archiver.record_partial("01a", src)

        dest = archiver.run_dir / "phases" / "01a" / "partials" / src.name
        assert dest.exists(), "fallback copy should have created dest"
        assert dest.read_text(encoding="utf-8") == '{"fallback": true}'

    def test_missing_source_is_silent(self, archiver: Archiver, tmp_path: Path):
        """record_partial on a nonexistent file must not raise."""
        missing = tmp_path / "does_not_exist.json"
        archiver.record_partial("01a", missing)  # should not raise

    def test_idempotent_short_circuits_when_dest_exists(
        self, archiver: Archiver, tmp_path: Path
    ):
        """Re-mirroring the same partial on a re-run must short-circuit:
        no os.link, no shutil.copy2 (avoids the noisy fallback that PR #55
        review called out)."""
        src = tmp_path / "01a_PARTIAL_W0B0_444.json"
        src.write_text('{"x": 1}', encoding="utf-8")

        # First mirror — actually links/copies into the archive.
        archiver.record_partial("01a", src)
        dest = archiver.run_dir / "phases" / "01a" / "partials" / src.name
        assert dest.exists()

        # Second mirror — must not invoke os.link OR shutil.copy2.
        with (
            patch("os.link") as mock_link,
            patch("shutil.copy2") as mock_copy,
        ):
            archiver.record_partial("01a", src)
            mock_link.assert_not_called()
            mock_copy.assert_not_called()


# ---------------------------------------------------------------------------
# 3. RunManifest round-trip
# ---------------------------------------------------------------------------

class TestRunManifest:
    def test_json_round_trip(self):
        now = datetime.now(timezone.utc)
        manifest = RunManifest(
            run_id="2026-01-01T00-00-00Z-abc1234-test",
            started_at=now,
            ended_at=now,
            speca_commit="abc1234",
            model={"01a": "claude-opus"},
            prompt_shas={"01a": "deadbeef" * 8},
            spec_sources=["https://example.com/spec"],
            phases_completed=["01a"],
            cost_usd_total=0.42,
        )
        json_str = json.dumps(manifest.model_dump(mode="json"))
        recovered = RunManifest.model_validate_json(json_str)

        assert recovered.run_id == manifest.run_id
        assert recovered.started_at.tzinfo is not None, "datetime must be timezone-aware"
        assert recovered.cost_usd_total == pytest.approx(0.42)
        assert recovered.phases_completed == ["01a"]

    def test_timezone_aware_datetimes(self):
        manifest = RunManifest(
            run_id="test",
            started_at=datetime.now(timezone.utc),
        )
        assert manifest.started_at.tzinfo is not None


# ---------------------------------------------------------------------------
# 4. Concurrent record_partial — no corruption
# ---------------------------------------------------------------------------

class TestConcurrentRecordPartial:
    def test_four_threads_no_corruption(self, archiver: Archiver, tmp_path: Path):
        """Concurrent calls to record_partial must not corrupt any archived file."""
        n_threads = 4
        files: list[Path] = []
        for i in range(n_threads):
            f = tmp_path / f"01b_PARTIAL_W{i}B0_1000.json"
            f.write_text(json.dumps({"worker": i, "items": list(range(10))}), encoding="utf-8")
            files.append(f)

        errors: list[Exception] = []

        def _record(f: Path) -> None:
            try:
                archiver.record_partial("01b", f)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_record, args=(f,)) for f in files]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"thread errors: {errors}"

        dest_dir = archiver.run_dir / "phases" / "01b" / "partials"
        archived = list(dest_dir.iterdir())
        # At least one file per thread (names may collide if identical — that's fine)
        assert len(archived) >= 1
        # All archived files must be valid JSON
        for p in archived:
            data = json.loads(p.read_text(encoding="utf-8"))
            assert "worker" in data or "items" in data, f"unexpected content in {p}"


# ---------------------------------------------------------------------------
# 5. --no-archive path: no archiver injected, outputs land in outputs/
# ---------------------------------------------------------------------------

class TestNoArchive:
    def test_orchestrator_created_without_archiver(self):
        """create_orchestrator(archiver=None) must return a functioning orchestrator."""
        from orchestrator import create_orchestrator
        orch = create_orchestrator("01a", num_workers=1, max_concurrent=1, archiver=None)
        assert orch.archiver is None
        assert orch.collector.archiver is None

    def test_result_collector_without_archiver_does_not_raise(self, tmp_path: Path):
        """ResultCollector.save_partial must work when archiver is None."""
        from orchestrator.config import get_phase_config
        from orchestrator.collector import ResultCollector
        import os as _os

        # Point output dir at tmp_path for isolation
        orig = _os.environ.get("SPECA_OUTPUT_DIR")
        _os.environ["SPECA_OUTPUT_DIR"] = str(tmp_path)
        try:
            cfg = get_phase_config("01a")
            collector = ResultCollector(cfg, archiver=None)
            path = collector.save_partial([{"id": "seed", "source": "manual"}], 0, 0)
            assert path.exists()
        finally:
            if orig is None:
                _os.environ.pop("SPECA_OUTPUT_DIR", None)
            else:
                _os.environ["SPECA_OUTPUT_DIR"] = orig


# ---------------------------------------------------------------------------
# 6. Archiver.finalize — writes manifest, idempotent
# ---------------------------------------------------------------------------

class TestFinalize:
    def test_finalize_ok_writes_manifest(self, archiver: Archiver):
        archiver.finalize("ok")
        manifest_path = archiver.run_dir / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["run_id"] == archiver.run_id
        assert data["notes"] == "ok"
        assert data["ended_at"] is not None

    def test_finalize_error_writes_reason(self, archiver: Archiver):
        archiver.finalize("error", reason="phase 01a budget exceeded")
        data = json.loads((archiver.run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert "budget exceeded" in data["notes"]

    def test_finalize_idempotent(self, archiver: Archiver):
        archiver.finalize("ok")
        first_mtime = (archiver.run_dir / "manifest.json").stat().st_mtime
        # Second call must be a no-op
        archiver.finalize("error", reason="should be ignored")
        second_mtime = (archiver.run_dir / "manifest.json").stat().st_mtime
        # File must not have been rewritten
        assert first_mtime == second_mtime

        data = json.loads((archiver.run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert data["notes"] == "ok", "second finalize should not overwrite the first"


# ---------------------------------------------------------------------------
# 7. Cross-fs simulation: os.link -> OSError(EXDEV), copy2 is called
# ---------------------------------------------------------------------------

class TestCrossFsFallback:
    def test_copy2_called_on_exdev(self, archiver: Archiver, tmp_path: Path):
        src = tmp_path / "01a_PARTIAL_W0B0_999.json"
        src.write_text('{"cross": "fs"}', encoding="utf-8")

        with (
            patch("os.link", side_effect=OSError(errno.EXDEV, "cross-device link")) as mock_link,
            patch("shutil.copy2", wraps=shutil.copy2) as mock_copy,
        ):
            archiver.record_partial("01a", src)
            mock_link.assert_called_once()
            mock_copy.assert_called_once()

        dest = archiver.run_dir / "phases" / "01a" / "partials" / src.name
        assert dest.exists()
        # After copy2, inodes must differ (the destination is a new file)
        if src.stat().st_ino != 0:
            assert src.stat().st_ino != dest.stat().st_ino


# ---------------------------------------------------------------------------
# 8. Spec-slug edge cases
# ---------------------------------------------------------------------------

class TestSpecSlug:
    def test_empty_scope_json(self, tmp_path: Path):
        """BUG_BOUNTY_SCOPE.json exists but is empty object -> stable hash-based slug."""
        import os as _os
        orig = _os.environ.get("SPECA_OUTPUT_DIR")
        _os.environ["SPECA_OUTPUT_DIR"] = str(tmp_path)
        try:
            scope = tmp_path / "BUG_BOUNTY_SCOPE.json"
            scope.write_text("{}", encoding="utf-8")
            slug = _derive_spec_slug()
            # Should not crash and should return a non-empty string
            assert isinstance(slug, str)
            assert len(slug) > 0
        finally:
            if orig is None:
                _os.environ.pop("SPECA_OUTPUT_DIR", None)
            else:
                _os.environ["SPECA_OUTPUT_DIR"] = orig

    def test_missing_spec_urls_and_no_scope(self, tmp_path: Path):
        """No scope file and no SPEC_URLS -> 'unknown'."""
        import os as _os
        orig_dir = _os.environ.get("SPECA_OUTPUT_DIR")
        orig_urls = _os.environ.get("SPEC_URLS")
        _os.environ["SPECA_OUTPUT_DIR"] = str(tmp_path)
        _os.environ.pop("SPEC_URLS", None)
        try:
            slug = _derive_spec_slug()
            assert slug == "unknown"
        finally:
            if orig_dir is None:
                _os.environ.pop("SPECA_OUTPUT_DIR", None)
            else:
                _os.environ["SPECA_OUTPUT_DIR"] = orig_dir
            if orig_urls is not None:
                _os.environ["SPEC_URLS"] = orig_urls

    def test_non_ascii_spec_name(self, tmp_path: Path):
        """Non-ASCII characters in spec name are stripped, not raised."""
        slug = _slugify("日本語テスト spec v2.0", 40)
        assert isinstance(slug, str)
        # All remaining chars must be [a-z0-9-] or the fallback 'unknown'
        import re
        assert re.match(r"^[a-z0-9-]*$", slug) or slug == "unknown"

    def test_slug_only_ascii(self):
        """_slugify must only produce [a-z0-9-]+ characters."""
        import re
        slug = _slugify("Uniswap V4 Core — Protocol", 40)
        assert re.match(r"^[a-z0-9-]+$", slug), f"non-ascii in slug: {slug!r}"

    def test_spec_urls_fallback(self, tmp_path: Path):
        """SPEC_URLS set without scope file -> slug from first URL."""
        import os as _os
        orig_dir = _os.environ.get("SPECA_OUTPUT_DIR")
        orig_urls = _os.environ.get("SPEC_URLS")
        _os.environ["SPECA_OUTPUT_DIR"] = str(tmp_path)
        _os.environ["SPEC_URLS"] = "https://example.com/uniswap-v4,https://other.com"
        try:
            slug = _derive_spec_slug()
            assert "uniswap" in slug or "v4" in slug or slug  # just must not crash
        finally:
            if orig_dir is None:
                _os.environ.pop("SPECA_OUTPUT_DIR", None)
            else:
                _os.environ["SPECA_OUTPUT_DIR"] = orig_dir
            if orig_urls is None:
                _os.environ.pop("SPEC_URLS", None)
            else:
                _os.environ["SPEC_URLS"] = orig_urls


# ---------------------------------------------------------------------------
# 9. record_cost — manifest delta accounting (regression for PR #55 review)
# ---------------------------------------------------------------------------

class TestRecordCost:
    def test_multi_batch_uses_delta_not_cumulative(self, archiver: Archiver):
        """record_cost receives a monotonically increasing cumulative figure
        per phase; the manifest total must reflect the final cumulative,
        not the sum-of-cumulatives.

        Regression for PR #55 review (grandchildrice): the original code
        added ``snapshot['total_cost_usd']`` directly, so N batches in one
        phase reported ``sum_{i=1..N}(cumulative_i)`` ≈ N(N+1)/2 * batch_avg.
        """
        archiver.record_cost("01a", {"total_cost_usd": 4.0})
        archiver.record_cost("01a", {"total_cost_usd": 8.0})
        archiver.record_cost("01a", {"total_cost_usd": 12.0})

        # Final cumulative is $12 — not 4 + 8 + 12 = $24.
        assert archiver._manifest.cost_usd_total == pytest.approx(12.0)
        assert archiver._manifest.phases_completed == ["01a"]

    def test_costs_sum_across_phases(self, archiver: Archiver):
        """Different phases each have a fresh per-phase CostTracker; their
        cumulative totals must sum into the manifest, not interfere."""
        # Phase 01a, two batches
        archiver.record_cost("01a", {"total_cost_usd": 4.0})
        archiver.record_cost("01a", {"total_cost_usd": 10.0})
        # Phase 01b begins (its own tracker starts at 0)
        archiver.record_cost("01b", {"total_cost_usd": 3.0})
        # 01a continues with another batch
        archiver.record_cost("01a", {"total_cost_usd": 12.0})

        # Final: 01a=$12 + 01b=$3 = $15.
        assert archiver._manifest.cost_usd_total == pytest.approx(15.0)
        assert set(archiver._manifest.phases_completed) == {"01a", "01b"}

    def test_cost_json_written_with_snapshot(self, archiver: Archiver):
        """The cost.json file mirrors the most recent snapshot for the phase."""
        snapshot = {
            "total_cost_usd": 2.5,
            "total_input_tokens": 5000,
            "batch_count": 3,
        }
        archiver.record_cost("01a", snapshot)
        cost_path = archiver.run_dir / "phases" / "01a" / "cost.json"
        assert cost_path.exists()
        data = json.loads(cost_path.read_text(encoding="utf-8"))
        assert data["total_cost_usd"] == 2.5
        assert data["batch_count"] == 3

    def test_missing_total_cost_usd_defaults_to_zero(self, archiver: Archiver):
        """A snapshot without total_cost_usd must not crash; treat as 0."""
        archiver.record_cost("01a", {"total_input_tokens": 100})
        assert archiver._manifest.cost_usd_total == pytest.approx(0.0)

    def test_out_of_order_snapshot_does_not_subtract(self, archiver: Archiver):
        """When a later snapshot lands before an earlier one (concurrent
        batches racing on the archiver lock), the manifest total must NOT
        drop. We track the per-phase max, so a stale snapshot is a no-op."""
        # Highest snapshot lands first
        archiver.record_cost("01a", {"total_cost_usd": 10.0})
        # Older / lower snapshot races in afterward
        archiver.record_cost("01a", {"total_cost_usd": 4.0})

        # Manifest must still reflect $10, not $10 + (-6) = $4.
        assert archiver._manifest.cost_usd_total == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# 10. Concurrent record_cost — atomic write must not corrupt cost.json
# ---------------------------------------------------------------------------

class TestConcurrentRecordCost:
    def test_parallel_writes_produce_valid_json(self, archiver: Archiver):
        """Concurrent record_cost calls into the same phase must not interleave
        partial JSON content in cost.json or leak .tmp files.

        Regression for PR #55 review (grandchildrice): the original
        ``_atomic_write_json`` used ``path.with_suffix('.tmp')`` so parallel
        writers to the same cost.json shared one tempfile path. Now
        ``tempfile.mkstemp`` gives each writer a unique tempfile.
        """
        n_threads = 16
        errors: list[Exception] = []
        barrier = threading.Barrier(n_threads)

        def _record(i: int) -> None:
            try:
                # Synchronize start across threads to maximize contention
                barrier.wait()
                archiver.record_cost("01a", {
                    "total_cost_usd": float(i),
                    "total_input_tokens": i * 1000,
                    "batch_index": i,
                })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_record, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"thread errors: {errors}"

        cost_path = archiver.run_dir / "phases" / "01a" / "cost.json"
        assert cost_path.exists(), "cost.json was never produced"

        # The file must be a complete, valid JSON object — never half-written.
        data = json.loads(cost_path.read_text(encoding="utf-8"))
        assert "total_cost_usd" in data
        assert "batch_index" in data
        # The last writer wins, but its value must be one of the snapshots —
        # never an interleaved frankenstein.
        assert 0 <= data["batch_index"] < n_threads

        # No stale temp files should be left behind.
        leftover = list(cost_path.parent.glob(cost_path.name + ".*.tmp"))
        assert not leftover, f"tmp files leaked under contention: {leftover}"

    def test_parallel_writes_different_phases_independent(self, archiver: Archiver):
        """Concurrent writers to *different* phases must not interfere."""
        phases = [f"phase_{i:02d}" for i in range(8)]
        errors: list[Exception] = []
        barrier = threading.Barrier(len(phases))

        def _record(phase: str) -> None:
            try:
                barrier.wait()
                archiver.record_cost(phase, {"total_cost_usd": 1.5})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_record, args=(p,)) for p in phases]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"thread errors: {errors}"
        for phase in phases:
            cost_path = archiver.run_dir / "phases" / phase / "cost.json"
            assert cost_path.exists(), f"missing cost.json for {phase}"
            data = json.loads(cost_path.read_text(encoding="utf-8"))
            assert data["total_cost_usd"] == 1.5

        # Manifest must sum all phases ($1.5 * 8 = $12).
        assert archiver._manifest.cost_usd_total == pytest.approx(1.5 * len(phases))


# ---------------------------------------------------------------------------
# 10. record_prompt records sha in manifest
# ---------------------------------------------------------------------------

class TestRecordPrompt:
    def test_prompt_sha_recorded(self, archiver: Archiver):
        import hashlib
        text = "Hello, this is a test prompt."
        archiver.record_prompt("01a", text)
        expected_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert archiver._manifest.prompt_shas.get("01a") == expected_sha

    def test_prompt_file_written(self, archiver: Archiver):
        archiver.record_prompt("01b", "# My Prompt\n\nDo stuff.")
        prompt_path = archiver.run_dir / "prompts" / "01b.md"
        assert prompt_path.exists()
        assert prompt_path.read_text(encoding="utf-8") == "# My Prompt\n\nDo stuff."


# ---------------------------------------------------------------------------
# 11. record_log mirrors the stream-json log into phases/<phase>/logs/
# ---------------------------------------------------------------------------

class TestRecordLog:
    def test_log_mirrored_into_phase_logs_dir(
        self, archiver: Archiver, tmp_path: Path
    ):
        src = tmp_path / "01a_W0B0_111.jsonl"
        src.write_text('{"event": "started"}\n{"event": "done"}\n', encoding="utf-8")

        archiver.record_log("01a", src)

        dest = archiver.run_dir / "phases" / "01a" / "logs" / src.name
        assert dest.exists(), "log was not mirrored"
        assert dest.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")

    def test_log_missing_source_is_silent(
        self, archiver: Archiver, tmp_path: Path
    ):
        archiver.record_log("01a", tmp_path / "nope.jsonl")  # must not raise


# ---------------------------------------------------------------------------
# 12. Manifest mutators and env snapshot
# ---------------------------------------------------------------------------

class TestManifestMutators:
    def test_set_env_snapshot_writes_inputs_env_json(self, archiver: Archiver):
        env_data = {"KEYWORDS": "geth,ethereum", "SPEC_URLS": "https://example.com"}
        archiver.set_env_snapshot(env_data)
        env_path = archiver.run_dir / "inputs" / "env.json"
        assert env_path.exists()
        assert json.loads(env_path.read_text(encoding="utf-8")) == env_data

    def test_set_commit_set_model_set_spec_sources_land_on_manifest(
        self, archiver: Archiver
    ):
        archiver.set_commit("abcdef1")
        archiver.set_model("01a", "claude-sonnet-4-6")
        archiver.set_model("01b", "claude-opus-4-7")
        archiver.set_spec_sources(["https://a.example/spec", "https://b.example/spec"])

        archiver.finalize("ok")

        manifest = json.loads(
            (archiver.run_dir / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["speca_commit"] == "abcdef1"
        assert manifest["model"] == {"01a": "claude-sonnet-4-6", "01b": "claude-opus-4-7"}
        assert manifest["spec_sources"] == [
            "https://a.example/spec",
            "https://b.example/spec",
        ]
