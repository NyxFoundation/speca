#!/usr/bin/env python3
"""RQ1 controlled-baseline runner (issue #102) -- SKELETON.

Runs the three arms (A code-only, B spec-only, C SPECA full) over >=3 seeds on
the same target, holding model / target commit / phase-04 review constant, then
scores per-arm recall against the #107 population-mapping table.

STATUS: skeleton. It documents the exact wiring and orchestration but is NOT yet
executable end-to-end. Two things are required first, and NEITHER has been done
or tested in this repo yet:

  1) Register the two variant audit phases in scripts/orchestrator/config.py so
     `run_phase.py --phase <id>` can drive them. Suggested stubs (mirror the "03"
     PhaseConfig, only deps/inputs/prompt differ):

        "03_codeonly": PhaseConfig(
            phase_id="03_codeonly",
            prompt_path=Path("experiments/rq1_baselines/prompts/audit_code_only.md"),
            output_pattern="outputs/03_PARTIAL_*.json",
            depends_on=[],                      # no spec/property deps
            input_patterns=[],                  # reads target_workspace/ directly
            model="sonnet",
            mcp_servers=[],
        ),
        "03_spec_only": PhaseConfig(
            phase_id="03_spec_only",
            prompt_path=Path("experiments/rq1_baselines/prompts/audit_spec_only.md"),
            output_pattern="outputs/03_PARTIAL_*.json",
            depends_on=["01b"],                 # spec + subgraph, no 01e/02c
            input_patterns=["outputs/01b_PARTIAL_*.json"],
            model="sonnet",
            mcp_servers=[],
        ),

  2) One smoke-test run of each arm on a single target/seed to confirm the
     variant prompts emit the phase-03 finding schema that phase-04 consumes.

Until (1) and (2) are done, treat any numbers this produces as unverified.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = json.loads((HERE / "arms.json").read_text(encoding="utf-8"))


def arm_by_id(arm_id: str) -> dict:
    for a in ARMS["arms"]:
        if a["id"].startswith(arm_id) or a["id"] == arm_id:
            return a
    raise SystemExit(f"unknown arm: {arm_id}")


def run_arm(arm: dict, seed: int, target: str, model: str, dry_run: bool) -> Path:
    """Run one arm at one seed. Each (arm, seed) writes to a disjoint output root
    so arms never thrash the same venv/outputs. Uses SPECA_RUN_ID to pin the
    run-id (see CLAUDE.md) for determinism."""
    out_root = HERE / "runs" / arm["id"] / f"seed{seed}"
    out_root.mkdir(parents=True, exist_ok=True)
    run_id = f"rq1-{arm['id']}-s{seed}"
    for phase in arm["phases"]:
        cmd = [
            sys.executable, "scripts/run_phase.py",
            "--phase", phase,
            "--json",
        ]
        env_note = {
            "SPECA_RUN_ID": run_id,
            "SPECA_OUTPUT_DIR": str(out_root),
            "SPECA_MODEL": model or ARMS["defaults"]["model"],
            "SPECA_TARGET": target,
        }
        print(f"[{arm['id']} seed{seed}] phase {phase}: {' '.join(cmd)}  env={env_note}")
        if dry_run:
            continue
        # NOTE: real execution requires the two variant phases registered (see
        # module docstring). Left as a subprocess call so the wiring is explicit.
        subprocess.run(cmd, check=False, env={**_os_environ(), **env_note})
    return out_root


def _os_environ() -> dict:
    import os
    return dict(os.environ)


def score(_arms, _seeds) -> None:
    """Compute per-arm recall against the #107 population-mapping table.

    Requires outputs/ findings from each run AND the #107 map (72->19->15). Not
    implemented until the #107 table exists (blocked on findings data). Prints the
    intended shape so the metric is unambiguous."""
    print("SCORING (not yet runnable -- needs #107 map + run outputs):")
    print("  per arm: recall = |detected AND 15 H/M/L| / 15, with per-severity split")
    print("  property-only-recoverable = (B OR C) MINUS A, listed by finding name")
    print("  report mean +/- range across seeds; decision rule per README")


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ1 controlled-baseline runner (#102, skeleton)")
    ap.add_argument("--arms", default="A,B,C", help="comma list: A,B,C")
    ap.add_argument("--seeds", type=int, default=ARMS["defaults"]["seeds"])
    ap.add_argument("--target", required=False, help="Sherlock target id")
    ap.add_argument("--model", default=ARMS["defaults"]["model"])
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    ap.add_argument("--score", action="store_true", help="score existing runs and exit")
    args = ap.parse_args()

    if args.score:
        score(args.arms.split(","), args.seeds)
        return 0

    if not args.target:
        ap.error("--target is required unless --score")

    for arm_id in args.arms.split(","):
        arm = arm_by_id(arm_id)
        for seed in range(args.seeds):
            run_arm(arm, seed, args.target, args.model, args.dry_run)
    print("done (dry-run)" if args.dry_run else "done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
