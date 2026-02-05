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
import sys
import os
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import create_orchestrator
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


async def run_phase(phase_id: str, num_workers: int, max_concurrent: int, force: bool) -> bool:
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

    # 3. Run the orchestrator
    try:
        # Set FORCE_EXECUTE for the orchestrator if --force is used
        if force:
            os.environ["FORCE_EXECUTE"] = "1"
        elif "FORCE_EXECUTE" in os.environ:
            # Clear it if not requested, to avoid accidental persistence from outer shell
            del os.environ["FORCE_EXECUTE"]
            
        orchestrator = create_orchestrator(phase_id, num_workers, max_concurrent)
        await orchestrator.run()
        return True
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
) -> dict[str, bool]:
    """Run a pipeline of multiple phases."""
    results = {}
    for phase_id in phases:
        success = await run_phase(phase_id, num_workers, max_concurrent, force)
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

    if args.cleanup_dry_run:
        print("\nRunning cleanup dry-run...")
        for phase_id in phases:
            run_cleanup(phase_id, dry_run=True)
        return

    print(f"\nPipeline execution starting...")
    
    results = asyncio.run(
        run_pipeline(phases, args.workers, args.max_concurrent, args.force)
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
