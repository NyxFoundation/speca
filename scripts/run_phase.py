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
import json
import sys
import os
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import create_orchestrator
from orchestrator.base import PhaseAbortError
from orchestrator.config import get_phase_config, get_phase_chain, PHASE_CONFIGS
from orchestrator.resume import ResumeManager


# Default configuration (migrated from Makefile)
DEFAULT_KEYWORDS = "geth,ethereum client,execution specs,EIP"
DEFAULT_SPEC_URLS = "https://ethereum.github.io/execution-specs/src/,https://geth.ethereum.org/docs"


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
        matches = list(Path(".").glob(pattern))
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

    target_info_path = Path("outputs/TARGET_INFO.json")
    if not target_info_path.exists():
        print(
            "⚠️  outputs/TARGET_INFO.json not found — skipping --target-layer / "
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
) -> bool:
    """Run a single phase with all checks and cleanup."""
    print(f"\n{'#'*60}")
    print(f"# Starting Phase {phase_id}")
    print(f"{'#'*60}")

    # Set default environment variables for 01a if not set
    if phase_id == "01a":
        if "KEYWORDS" not in os.environ:
            print(f"Using default KEYWORDS: {DEFAULT_KEYWORDS}")
            os.environ["KEYWORDS"] = DEFAULT_KEYWORDS
        if "SPEC_URLS" not in os.environ:
            print(f"Using default SPEC_URLS: {DEFAULT_SPEC_URLS}")
            os.environ["SPEC_URLS"] = DEFAULT_SPEC_URLS

    # 1. Check dependencies
    if not check_dependencies(phase_id):
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
    try:
        # Set FORCE_EXECUTE for the orchestrator if --force is used
        if force:
            os.environ["FORCE_EXECUTE"] = "1"
        elif "FORCE_EXECUTE" in os.environ:
            # Clear it if not requested, to avoid accidental persistence from outer shell
            del os.environ["FORCE_EXECUTE"]
            
        orchestrator = create_orchestrator(phase_id, num_workers, max_concurrent)

        # Override min_severity from CLI if provided
        if min_severity is not None and orchestrator.config.min_severity is not None:
            print(f"  --min-severity override: {orchestrator.config.min_severity} -> {min_severity}")
            orchestrator.config.min_severity = min_severity
        elif min_severity is not None:
            # Phase doesn't have min_severity configured — set it anyway
            orchestrator.config.min_severity = min_severity
            print(f"  --min-severity set: {min_severity}")

        await orchestrator.run()
        return True
    except PhaseAbortError as e:
        print(f"Phase {phase_id} aborted: {e}", file=sys.stderr)
        return False
    except Exception as e:
        import traceback
        traceback.print_exc()
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
    target_phase: str | None = None,
) -> dict[str, bool]:
    """Run a pipeline of multiple phases."""
    results = {}
    for phase_id in phases:
        # When --target + --force, only force-clean the target phase, not upstream
        phase_force = force and (target_phase is None or phase_id == target_phase)
        success = await run_phase(
            phase_id, num_workers, max_concurrent, phase_force,
            target_layer=target_layer,
            out_of_scope_layers=out_of_scope_layers,
            min_severity=min_severity,
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

    # Severity gate
    parser.add_argument(
        "--min-severity",
        choices=["Critical", "High", "Medium", "Low", "Informational"],
        default=None,
        help="Override min_severity for phases that support severity gating (e.g. phase 02). "
             "Properties below this threshold are skipped. Default comes from PhaseConfig.",
    )

    args = parser.parse_args()
    
    # Determine execution order
    if args.target:
        phases = get_phase_chain(args.target)
    else:
        # Flatten list if nargs=+ was used (['01a', '01b'])
        phases = args.phase
        
    print(f"Configuration:")
    print(f"  Workers: {args.workers}")
    print(f"  Max Concurrent: {args.max_concurrent}")
    print(f"  Force: {args.force}")
    print(f"  Phases: {phases}")
    if args.min_severity:
        print(f"  Min Severity: {args.min_severity}")

    if args.cleanup_dry_run:
        print("\nRunning cleanup dry-run...")
        for phase_id in phases:
            run_cleanup(phase_id, dry_run=True)
        return

    print(f"\nPipeline execution starting...")
    
    results = asyncio.run(
        run_pipeline(
            phases,
            args.workers,
            args.max_concurrent,
            args.force,
            target_layer=args.target_layer,
            out_of_scope_layers=args.out_of_scope_layers,
            min_severity=args.min_severity,
            target_phase=args.target if args.target else None,
        )
    )
    
    print(f"\n{'='*60}")
    print("Pipeline Summary")
    print(f"{'='*60}")
    all_success = True
    for phase_id in phases:
        if phase_id in results:
            success = results[phase_id]
            status = "✅ Success" if success else "❌ Failed"
            print(f"  Phase {phase_id}: {status}")
            if not success:
                all_success = False
        else:
             print(f"  Phase {phase_id}: ⏭️  Skipped/Not reached")

    
    if not all_success:
        sys.exit(1)

if __name__ == "__main__":
    main()
