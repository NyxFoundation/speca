#!/usr/bin/env python3
"""
Unified Phase Runner - Makefile Replacement

Handles all pipeline logic, including dependency checking, cleanup, and execution.

Usage:
    # Run a single phase (with automatic cleanup and resume)
    python3 scripts/run_phase.py --phase 01b --workers 4
    
    # Run all phases up to a target
    python3 scripts/run_phase.py --target 03 --workers 4
    
    # Force re-execution (ignore resume)
    python3 scripts/run_phase.py --phase 01b --force
    
    # Show cleanup summary without executing
    python3 scripts/run_phase.py --phase 01b --cleanup-dry-run
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import create_orchestrator
from orchestrator.archiver import Archiver
from orchestrator.base import PhaseAbortError
from orchestrator.config import get_phase_config, get_phase_chain, PHASE_CONFIGS, resolve_pattern
from orchestrator.json_events import JsonEventEmitter
from orchestrator.paths import get_output_root
from orchestrator.phase0_runner import get_phase0_runner, is_phase0
from orchestrator.resume import ResumeManager


# ---------------------------------------------------------------------------
# Run-id generation helpers
# ---------------------------------------------------------------------------

def _get_short_sha() -> str:
    """Return the first 7 chars of HEAD in the speca repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        if result.returncode == 0:
            return result.stdout.strip()[:7]
    except Exception:
        pass
    return ""


def _derive_spec_slug() -> str:
    """Derive a spec slug from BUG_BOUNTY_SCOPE.json, SPEC_URLS, or 'unknown'."""
    output_root = get_output_root()

    # 1. Try BUG_BOUNTY_SCOPE.json
    scope_path = output_root / "BUG_BOUNTY_SCOPE.json"
    if scope_path.exists():
        try:
            with open(scope_path, encoding="utf-8") as f:
                scope = json.load(f)
            # Look for a program name or similar field
            name = (
                scope.get("program_name")
                or scope.get("name")
                or scope.get("target")
                or ""
            )
            if name:
                return _slugify(str(name), 40)
        except Exception:
            pass
        # File exists but we couldn't get a name — still use a hash so it's stable
        try:
            content = scope_path.read_bytes()
            return "scope-" + hashlib.sha256(content).hexdigest()[:6]
        except Exception:
            pass

    # 2. Try SPEC_URLS env or first entry
    spec_urls = os.environ.get("SPEC_URLS", "")
    if spec_urls:
        first_url = spec_urls.split(",")[0].strip()
        if first_url:
            # Use the last meaningful path segment
            stem = Path(first_url.rstrip("/")).name or Path(first_url.rstrip("/")).parent.name
            if stem:
                return _slugify(stem, 40)

    return "unknown"


def _slugify(text: str, max_len: int = 40) -> str:
    """Convert *text* to ``[a-z0-9-]+`` slug (max *max_len* chars)."""
    # Normalize unicode to ASCII approximation by encoding + ignoring errors
    try:
        text = text.encode("ascii", errors="ignore").decode("ascii")
    except Exception:
        pass
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "unknown"


def make_run_id(
    spec_slug: str | None = None,
    sha: str | None = None,
    nonce: str | None = None,
) -> str:
    """Generate a run-id in the format ``<ts>-<sha>-<spec-slug>-<nonce>``.

    ``<ts>`` uses ``YYYY-MM-DDTHH-MM-SSZ`` (hyphens instead of colons so the
    string is a valid path segment on Windows and all POSIX systems). The
    trailing ``<nonce>`` is 4 random hex chars so two invocations within the
    same second on the same commit and slug never collide on disk.

    When the speca git sha is unavailable (no .git, detached state, etc.),
    the sha segment is filled with 7 random hex chars so the run-id still
    matches the documented shape and remains unique across invocations.
    """
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    resolved_sha = sha if sha is not None else _get_short_sha()
    if not resolved_sha:
        # No git context — use a hex placeholder so the run-id keeps its shape.
        resolved_sha = secrets.token_hex(4)[:7]
    slug = spec_slug if spec_slug is not None else _derive_spec_slug()
    resolved_nonce = nonce if nonce is not None else secrets.token_hex(2)
    return f"{ts}-{resolved_sha}-{slug}-{resolved_nonce}"


def _build_env_snapshot(phases: list[str]) -> dict:
    """Capture a sanitised snapshot of the runtime environment."""
    return {
        "KEYWORDS": os.environ.get("KEYWORDS", ""),
        "SPEC_URLS": os.environ.get("SPEC_URLS", ""),
        "SPECA_OUTPUT_DIR": os.environ.get("SPECA_OUTPUT_DIR", ""),
        "ORCHESTRATOR_RUNNER": os.environ.get("ORCHESTRATOR_RUNNER", "claude"),
        "phases": phases,
    }


# Default configuration (migrated from Makefile)
DEFAULT_KEYWORDS = "geth,ethereum client,execution specs,EIP"
DEFAULT_SPEC_URLS = "https://ethereum.github.io/execution-specs/src/,https://geth.ethereum.org/docs"


def _finalize_01a_state() -> None:
    """Consolidate the latest 01a PARTIAL into outputs/<root>/01a_STATE.json.

    Phase 01a is single-batch (one seed item) and the worker writes the result
    to 01a_PARTIAL_W0B0_<ts>.json wrapped as ``{"items": [<phase01a_state>]}``.
    Downstream phases (01b) expect the unwrapped payload at 01a_STATE.json.
    """
    output_root = get_output_root()
    state_path = output_root / "01a_STATE.json"
    partials = sorted(output_root.glob("01a_PARTIAL_*.json"))
    if not partials:
        return
    latest = partials[-1]
    try:
        with open(latest, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: failed to read {latest} for 01a finalization: {e}", file=sys.stderr)
        return

    payload = data
    if isinstance(data, dict) and isinstance(data.get("items"), list) and data["items"]:
        payload = data["items"][0]

    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"Warning: failed to write {state_path}: {e}", file=sys.stderr)
        return

    print(f"  ✓ Wrote 01a_STATE.json from {latest.name} ({len(payload.get('found_specs', []))} specs)")


def check_dependencies(phase_id: str) -> bool:
    """Check if all dependencies for a phase are met."""
    config = get_phase_config(phase_id)
    if not config.input_patterns:
        return True
    
    # Special case for 01a which has no input file dependencies in config but conceptually depends on nothing
    if phase_id == "01a":
        return True

    for pattern in config.input_patterns:
        # Simple glob check for now
        # We need to handle glob patterns that might be empty if optional,
        # but generally input_patterns imply requirement.
        # Note: glob() returns a generator, list() consumes it.
        resolved = resolve_pattern(pattern)
        # Path(".").glob() rejects absolute patterns on Python 3.12+
        # (NotImplementedError: Non-relative patterns are unsupported).
        # SPECA_OUTPUT_DIR is often absolute (e.g. when speca-cli passes
        # --output-dir as an absolute path), so split off the anchor and
        # glob from the parent directly.
        resolved_path = Path(resolved)
        if resolved_path.is_absolute():
            anchor = resolved_path.parts[0]
            relative = Path(*resolved_path.parts[1:])
            matches = list(Path(anchor).glob(str(relative)))
        else:
            matches = list(Path(".").glob(resolved))
        if not matches:
            # Check if it's a "worker-sharded" pattern (contains *)
            # If so, it might be that the previous phase produced nothing, 
            # which might be valid or might be an error.
            # For now, strict check: if input pattern yields nothing, it's a dependency failure.
            print(f"❌ Error: Dependency not met for phase {phase_id}. Missing input: {pattern}", file=sys.stderr)
            print(f"   Please run phase(s) {config.depends_on} first.", file=sys.stderr)
            return False
    return True


def run_cleanup(phase_id: str, dry_run: bool = True) -> bool:
    """Run cleanup for incomplete batches and their logs."""
    # Phase 0 outputs are singleton files (no PARTIAL/_QUEUE_ pattern), so the
    # ResumeManager's batch-level cleanup logic does not apply. Simply skip.
    if is_phase0(phase_id):
        if dry_run:
            print(f"Snapshot cleanup check for {phase_id}: phase 0 has no batches.")
        return False
    config = get_phase_config(phase_id)
    resume_manager = ResumeManager(config)
    summary = resume_manager.get_cleanup_summary()
    
    if summary["incomplete_batches"] == 0:
        if dry_run:
            print(f"Snapshot cleanup check for {phase_id}: No incomplete batches found.")
        return False
    
    print(f"\n{'='*60}")
    print(f"Cleanup Summary for Phase {phase_id}")
    print(f"{'='*60}")
    print(f"Found {summary['incomplete_batches']} incomplete batches.")
    
    if dry_run:
        print("Dry run mode: no files will be deleted.")
        print("Run without --cleanup-dry-run to actually delete these files.")
    else:
        print("Deleting incomplete batches and logs...")
        deleted = resume_manager.cleanup_incomplete_batches(dry_run=False)
        print(f"Deleted {len(deleted['batches'])} batch directories and {len(deleted['logs'])} log files.")
    
    return True


def patch_target_info(target_layer: str | None, out_of_scope_layers: list[str] | None) -> None:
    """Merge optional scope metadata into outputs/TARGET_INFO.json (in-place).

    Called before Phase 02c runs. Safe to call even if the file does not yet
    exist (writes nothing in that case) or if both arguments are None (no-op).
    """
    if not target_layer and not out_of_scope_layers:
        return

    target_info_path = get_output_root() / "TARGET_INFO.json"
    if not target_info_path.exists():
        print(
            f"⚠️  {target_info_path} not found — skipping --target-layer / "
            "--out-of-scope-layers injection. Run phase 02c setup first.",
            file=sys.stderr,
        )
        return

    with target_info_path.open() as f:
        info = json.load(f)

    if target_layer:
        info["target_layer"] = target_layer
    if out_of_scope_layers:
        info["out_of_scope_spec_layers"] = out_of_scope_layers

    with target_info_path.open("w") as f:
        json.dump(info, f, indent=2)

    print(f"  target_layer           = {info.get('target_layer', '(not set)')}")
    print(f"  out_of_scope_spec_layers = {info.get('out_of_scope_spec_layers', [])}")


async def run_phase(
    phase_id: str,
    num_workers: int,
    max_concurrent: int,
    force: bool,
    target_layer: str | None = None,
    out_of_scope_layers: list[str] | None = None,
    min_severity: str | None = None,
    model: str | None = None,
    emitter: JsonEventEmitter | None = None,
    archiver: Archiver | None = None,
) -> bool:
    """Run a single phase with all checks and cleanup."""
    emitter = emitter or JsonEventEmitter(enabled=False)
    start_time = time.time()
    emitter.emit(
        "phase-started",
        phase=phase_id,
        workers=num_workers,
        max_concurrent=max_concurrent,
        force=force,
        model=model,
    )

    print(f"\n{'#'*60}")
    print(f"# Starting Phase {phase_id}")
    print(f"{'#'*60}")

    # Phase 0 (setup) runs synchronously and outside the async batch
    # pipeline. We dispatch to phase0_runner here so that the rest of this
    # function (cleanup, orchestrator, circuit breaker, ...) stays unchanged
    # for 01a..04. See scripts/orchestrator/phase0_runner.py.
    if is_phase0(phase_id):
        try:
            runner = get_phase0_runner(phase_id, output_dir=get_output_root())
            rc = runner.run()
        except Exception as exc:  # noqa: BLE001 — surface any subprocess error
            import traceback
            traceback.print_exc()
            duration = round(time.time() - start_time, 2)
            emitter.emit(
                "phase-failed",
                phase=phase_id,
                reason=f"{type(exc).__name__}: {exc}",
                duration_s=duration,
            )
            return False

        duration = round(time.time() - start_time, 2)
        if rc == 0:
            emitter.emit(
                "phase-completed", phase=phase_id, duration_s=duration, total_results=0
            )
            return True
        emitter.emit(
            "phase-failed",
            phase=phase_id,
            reason=f"phase0 runner exit code {rc}",
            duration_s=duration,
        )
        return False

    # Set default environment variables for 01a if not set
    if phase_id == "01a":
        # Resume short-circuit: if STATE.json already exists and --force was
        # not requested, skip 01a entirely. The orchestrator's per-item resume
        # logic does not reliably detect 01a completion (id_field=url vs the
        # synthetic seed item's id), so we gate on the consolidated artefact.
        state_path = get_output_root() / "01a_STATE.json"
        if state_path.exists() and not force:
            print(f"  ✓ 01a_STATE.json already exists, skipping. Use --force to re-run.")
            duration = round(time.time() - start_time, 2)
            emitter.emit("phase-completed", phase=phase_id, duration_s=duration, total_results=0)
            return True

        if "KEYWORDS" not in os.environ:
            print(f"Using default KEYWORDS: {DEFAULT_KEYWORDS}")
            os.environ["KEYWORDS"] = DEFAULT_KEYWORDS
        if "SPEC_URLS" not in os.environ:
            print(f"Using default SPEC_URLS: {DEFAULT_SPEC_URLS}")
            os.environ["SPEC_URLS"] = DEFAULT_SPEC_URLS

    # 1. Check dependencies
    if not check_dependencies(phase_id):
        emitter.emit(
            "phase-failed",
            phase=phase_id,
            reason="dependency check failed",
            duration_s=round(time.time() - start_time, 2),
        )
        return False

    # 2. Automatic cleanup of incomplete batches
    if force:
        print(f"Force mode: Cleaning up ALL previous outputs for phase {phase_id}...")
        resume_manager = ResumeManager(get_phase_config(phase_id))
        resume_manager.cleanup_all_outputs(dry_run=False)
    else:
        run_cleanup(phase_id, dry_run=False)

    # 2b. Inject scope metadata into TARGET_INFO for Phase 02c
    if phase_id == "02c":
        patch_target_info(target_layer, out_of_scope_layers)

    # 3. Run the orchestrator
    orchestrator = None
    try:
        # Set FORCE_EXECUTE for the orchestrator if --force is used
        if force:
            os.environ["FORCE_EXECUTE"] = "1"
        elif "FORCE_EXECUTE" in os.environ:
            # Clear it if not requested, to avoid accidental persistence from outer shell
            del os.environ["FORCE_EXECUTE"]

        orchestrator = create_orchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)

        # Override model from CLI if provided
        if model is not None:
            prev = orchestrator.config.model
            orchestrator.config.model = model
            print(f"  --model override: {prev} -> {model}")

        # Record model and rendered prompt in the archive
        if archiver is not None:
            effective_model = orchestrator.config.model or ""
            archiver.set_model(phase_id, effective_model)
            try:
                prompt_path = Path(orchestrator.config.prompt_path)
                if prompt_path.exists():
                    prompt_text = prompt_path.read_text(encoding="utf-8")
                    archiver.record_prompt(phase_id, prompt_text)
            except Exception as _arc_e:
                print(f"[Archiver] warning: could not record prompt for {phase_id}: {_arc_e}", file=sys.stderr)

        # Override min_severity from CLI if provided
        if min_severity is not None and orchestrator.config.min_severity is not None:
            print(f"  --min-severity override: {orchestrator.config.min_severity} -> {min_severity}")
            orchestrator.config.min_severity = min_severity
        elif min_severity is not None:
            # Phase doesn't have min_severity configured — set it anyway
            orchestrator.config.min_severity = min_severity
            print(f"  --min-severity set: {min_severity}")

        await orchestrator.run()
        duration = round(time.time() - start_time, 2)

        # Phase 01a finalization: consolidate the latest PARTIAL into 01a_STATE.json.
        # The 01a config declares output_pattern=01a_STATE.json and 01b's
        # input_patterns=[01a_STATE.json], but the runner only writes
        # 01a_PARTIAL_*.json. Without this consolidation step downstream phases
        # can't find their input.
        if phase_id == "01a":
            _finalize_01a_state()

        emitter.emit(
            "phase-completed",
            phase=phase_id,
            duration_s=duration,
            total_results=len(getattr(orchestrator, "results", []) or []),
        )
        return True
    except PhaseAbortError as e:
        duration = round(time.time() - start_time, 2)
        # Distinguish budget / circuit-breaker aborts from other PhaseAbortError
        # cases (e.g. failed_batches) by inspecting orchestrator state. The
        # orchestrator sets these flags before raising PhaseAbortError, so they
        # are reliable here.
        if orchestrator is not None and getattr(orchestrator, "_budget_exceeded", False):
            cost_stats = orchestrator.cost_tracker.get_stats() if orchestrator.cost_tracker else {}
            emitter.emit(
                "budget-exceeded",
                phase=phase_id,
                cost_usd=cost_stats.get("total_cost_usd"),
                max_budget_usd=cost_stats.get("max_budget_usd"),
                duration_s=duration,
            )
        elif orchestrator is not None and getattr(orchestrator, "_circuit_breaker_tripped", False):
            cb_stats = await orchestrator.circuit_breaker.get_stats()
            emitter.emit(
                "circuit-breaker-tripped",
                phase=phase_id,
                reason=str(e),
                stats=cb_stats,
                duration_s=duration,
            )
        emitter.emit(
            "phase-failed",
            phase=phase_id,
            reason=str(e),
            duration_s=duration,
        )
        print(f"Phase {phase_id} aborted: {e}", file=sys.stderr)
        return False
    except Exception as e:
        import traceback
        traceback.print_exc()
        duration = round(time.time() - start_time, 2)
        emitter.emit(
            "phase-failed",
            phase=phase_id,
            reason=f"{type(e).__name__}: {e}",
            duration_s=duration,
        )
        print(f"Error running phase {phase_id}: {e}", file=sys.stderr)
        return False


async def run_pipeline(
    phases: list[str],
    num_workers: int,
    max_concurrent: int,
    force: bool,
    stop_on_failure: bool = True,
    target_layer: str | None = None,
    out_of_scope_layers: list[str] | None = None,
    min_severity: str | None = None,
    model: str | None = None,
    target_phase: str | None = None,
    emitter: JsonEventEmitter | None = None,
    archiver: Archiver | None = None,
) -> dict[str, bool]:
    """Run a pipeline of multiple phases."""
    emitter = emitter or JsonEventEmitter(enabled=False)
    results = {}
    for phase_id in phases:
        # When --target + --force, only force-clean the target phase, not upstream
        phase_force = force and (target_phase is None or phase_id == target_phase)
        success = await run_phase(
            phase_id, num_workers, max_concurrent, phase_force,
            target_layer=target_layer,
            out_of_scope_layers=out_of_scope_layers,
            min_severity=min_severity,
            model=model,
            emitter=emitter,
            archiver=archiver,
        )
        results[phase_id] = success
        if not success and stop_on_failure:
            print(f"\n❌ Pipeline stopped due to failure in phase {phase_id}.", file=sys.stderr)
            break
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Unified phase runner for security audit pipeline (Makefile replacement)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    
    phase_group = parser.add_mutually_exclusive_group(required=True)
    phase_group.add_argument("--phase", nargs="+", help="Specific phase(s) to run (e.g. 01a 01b)")
    phase_group.add_argument("--target", help="Target phase (runs all dependencies up to this phase)")
    
    parser.add_argument("--force", action="store_true", help="Force re-execution, ignoring resume state")
    parser.add_argument("--cleanup-dry-run", action="store_true", help="Show what would be cleaned up without executing")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--max-concurrent", type=int, default=8, help="Max concurrent Claude executions")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: 'outputs'). Also settable via SPECA_OUTPUT_DIR env var. "
             "Enables parallel instances with isolated output directories.",
    )

    # Phase 02c: target metadata for scope filtering
    parser.add_argument(
        "--target-layer",
        help="Functional layer of the target repo (e.g. 'consensus', 'execution', 'l2-node'). "
             "Written into outputs/TARGET_INFO.json when phase 02c is included.",
    )
    parser.add_argument(
        "--out-of-scope-layers",
        nargs="+",
        metavar="LAYER",
        help="Spec layers to mark as out_of_scope for this target (e.g. 'execution'). "
             "Written into outputs/TARGET_INFO.json when phase 02c is included.",
    )

    # Model override
    parser.add_argument(
        "--model",
        default=None,
        help="Override the Claude model for all phases in this run. "
             "Accepts any model string supported by Claude CLI (e.g. 'claude-3-5-sonnet-20241022', 'sonnet'). "
             "Default comes from PhaseConfig.",
    )

    # Severity gate
    parser.add_argument(
        "--min-severity",
        choices=["Critical", "High", "Medium", "Low", "Informational"],
        default=None,
        help="Override min_severity for phases that support severity gating (e.g. phase 02). "
             "Properties below this threshold are skipped. Default comes from PhaseConfig.",
    )

    # Phase 01a: discovery seed inputs
    parser.add_argument(
        "--keywords",
        default=None,
        help="Comma-separated keywords used by Phase 01a's spec-discovery skill. "
             "Sets the KEYWORDS env var; if neither --keywords nor $KEYWORDS is set, "
             "the Ethereum-default seeds are used. Pass an explicit value when running "
             "against a non-Ethereum target (e.g. 'litecoin,scrypt,LTC').",
    )
    parser.add_argument(
        "--spec-urls",
        default=None,
        help="Comma-separated seed URLs to crawl in Phase 01a. Sets the SPEC_URLS env var; "
             "if neither --spec-urls nor $SPEC_URLS is set, the Ethereum-default URLs are used. "
             "Pass explicit URLs when running against a non-Ethereum target.",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit pipeline-level events as NDJSON on stdout (one JSON object per line). "
             "Decorative output is redirected to stderr. Intended for speca-cli, CI scripts, "
             "and other automated consumers. See scripts/orchestrator/json_events.py for the "
             "event schema.",
    )

    # Archive flags
    parser.add_argument(
        "--archive-root",
        default=None,
        help="Root directory for run archives (default: <repo>/.speca/runs). "
             "Also settable via SPECA_ARCHIVE_ROOT env var.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Disable run archiving entirely. Outputs still land in outputs/ as usual.",
    )

    args = parser.parse_args()

    # In --json mode, route all decorative output (including the orchestrator's
    # own print() calls) to stderr so stdout stays NDJSON-only. The emitter
    # captures the *real* stdout via sys.__stdout__ so events still go there.
    if args.json:
        sys.stdout = sys.stderr

    emitter = JsonEventEmitter(enabled=args.json)

    # Set output directory early, before any orchestrator import evaluates paths
    if args.output_dir:
        os.environ["SPECA_OUTPUT_DIR"] = args.output_dir

    # Promote --keywords / --spec-urls into the env for Phase 01a. CLI flags
    # take precedence over an inherited env value so a single command line
    # is fully reproducible without remembering shell-level exports.
    if args.keywords:
        os.environ["KEYWORDS"] = args.keywords
    if args.spec_urls:
        os.environ["SPEC_URLS"] = args.spec_urls

    # Determine execution order
    if args.target:
        phases = get_phase_chain(args.target)
    else:
        # Flatten list if nargs=+ was used (['01a', '01b'])
        phases = args.phase

    # --- Archiver setup ---
    archiver: Archiver | None = None
    if not args.no_archive:
        # Determine archive root: CLI flag > env var > default
        archive_root_str = (
            args.archive_root
            or os.environ.get("SPECA_ARCHIVE_ROOT")
            or str(Path(__file__).resolve().parent.parent / ".speca" / "runs")
        )
        archive_root = Path(archive_root_str)
        # SPECA_RUN_ID lets CI / replay pin a deterministic id; otherwise we
        # generate one with a random nonce.
        run_id = os.environ.get("SPECA_RUN_ID") or make_run_id()
        archiver = Archiver(run_id, archive_root)
        # Write env snapshot
        archiver.set_env_snapshot(_build_env_snapshot(phases))
        archiver.set_commit(_get_short_sha())
        print(f"  Archive: {archiver.run_dir}")
    else:
        print(f"  Archive: disabled (--no-archive)")

    print(f"Configuration:")
    print(f"  Workers: {args.workers}")
    print(f"  Max Concurrent: {args.max_concurrent}")
    print(f"  Force: {args.force}")
    print(f"  Output Dir: {get_output_root()}")
    print(f"  Phases: {phases}")
    if args.model:
        print(f"  Model: {args.model}")
    if args.min_severity:
        print(f"  Min Severity: {args.min_severity}")

    if args.cleanup_dry_run:
        print("\nRunning cleanup dry-run...")
        for phase_id in phases:
            run_cleanup(phase_id, dry_run=True)
        return

    print(f"\nPipeline execution starting...")

    pipeline_start = time.time()
    emitter.emit(
        "pipeline-started",
        phases=phases,
        workers=args.workers,
        max_concurrent=args.max_concurrent,
        force=args.force,
    )

    pipeline_exc: BaseException | None = None
    results: dict[str, bool] = {}
    try:
        results = asyncio.run(
            run_pipeline(
                phases,
                args.workers,
                args.max_concurrent,
                args.force,
                target_layer=args.target_layer,
                out_of_scope_layers=args.out_of_scope_layers,
                min_severity=args.min_severity,
                model=args.model,
                target_phase=args.target if args.target else None,
                emitter=emitter,
                archiver=archiver,
            )
        )
    except BaseException as _pipe_err:
        # Catch BaseException so KeyboardInterrupt / SystemExit / asyncio
        # cancellation still trigger archive finalize. The original is
        # re-raised below with traceback preserved.
        pipeline_exc = _pipe_err
    finally:
        # Finalize the archive *always* — even on Ctrl-C, even if finalize
        # itself raises. A swallowed finalize-error must never shadow the
        # original pipeline traceback.
        if archiver is not None:
            try:
                if pipeline_exc is None and (not results or all(results.values())):
                    archiver.finalize("ok")
                else:
                    reason = (
                        str(pipeline_exc)
                        if pipeline_exc is not None
                        else "one or more phases failed"
                    )
                    archiver.finalize("error", reason=reason)
            except Exception as _fin_err:
                print(
                    f"[Archiver] warning: finalize failed: {_fin_err}",
                    file=sys.stderr,
                )

    if pipeline_exc is not None:
        # Preserve the original traceback rather than wrapping with str().
        raise pipeline_exc

    emitter.emit(
        "pipeline-completed",
        phases=phases,
        results=results,
        duration_s=round(time.time() - pipeline_start, 2),
    )

    print(f"\n{'='*60}")
    print("Pipeline Summary")
    print(f"{'='*60}")
    all_success = True
    for phase_id in phases:
        if phase_id in results:
            success = results[phase_id]
            status = "Success" if success else "Failed"
            print(f"  Phase {phase_id}: {status}")
            if not success:
                all_success = False
        else:
             print(f"  Phase {phase_id}: Skipped/Not reached")


    if not all_success:
        sys.exit(1)

if __name__ == "__main__":
    main()
