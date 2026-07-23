"""Accuracy gate for graph-based 02c (speca#157 Step 4).

Builds the symbol index over a benchmark repo, resolves each benchmark property,
and scores it against the expected code location. Prints the accuracy report and
EXITS NON-ZERO if it falls below the gate — so CI blocks a regression in the
deterministic resolver's recall (or a blow-up in the LLM-fallback rate).

The recall gate is what makes "accuracy guaranteed" concrete: combined with the
runtime fallback (low-confidence -> LLM), a passing gate means the deterministic
tier resolves >= RECALL_MIN of properties itself, and the rest fall back (never
dropped), so system recall >= the LLM baseline at a bounded LLM cost.

    python -m orchestrator.graph_02c.eval_cli \
        [--repo <dir>] [--bench <bench.json>] \
        [--recall-min 0.9] [--fallback-max 0.34]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .benchmark import GroundTruth
from .metric import evaluate
from .resolver import resolve
from .symbols import build_index

_HERE = Path(__file__).resolve().parent
_DEFAULT_REPO = _HERE / "fixtures" / "bench_repo"
_DEFAULT_BENCH = _HERE / "fixtures" / "bench.json"


def run(repo: Path, bench_path: Path) -> dict:
    index = build_index(repo)
    cases = json.loads(bench_path.read_text(encoding="utf-8"))["cases"]
    pairs = []
    fallback = 0
    for c in cases:
        prop, exp = c["property"], c["expect"]
        r = resolve(prop, index)
        if r.confidence == "low":
            fallback += 1
        gt = GroundTruth(
            client="bench", property_id=prop["property_id"],
            file=exp["file"], symbol=exp.get("symbol"),
            line_start=exp.get("line_start"), line_end=exp.get("line_end"),
            raw=str(exp),
        )
        pairs.append((gt, r.code_scope))
    rep = evaluate(pairs)
    n = len(cases)
    return {
        "n": n,
        "recall": rep.recall,
        "file_recall": rep.file_recall,
        "fallback_rate": round(fallback / n, 4) if n else 0.0,
        "avg_locations": rep.avg_locations,
        "misses": rep.misses,
        "skipped_langs": sorted(index.skipped_langs),
        "n_symbols": len(index.symbols),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=_DEFAULT_REPO)
    ap.add_argument("--bench", type=Path, default=_DEFAULT_BENCH)
    ap.add_argument("--recall-min", type=float, default=0.9)
    ap.add_argument("--fallback-max", type=float, default=0.34)
    args = ap.parse_args(argv)

    res = run(args.repo, args.bench)
    print(json.dumps(res, indent=2, ensure_ascii=False))

    ok = True
    if res["recall"] < args.recall_min:
        print(f"GATE FAIL: recall {res['recall']} < {args.recall_min}", file=sys.stderr)
        ok = False
    if res["fallback_rate"] > args.fallback_max:
        print(f"GATE FAIL: fallback_rate {res['fallback_rate']} > {args.fallback_max}", file=sys.stderr)
        ok = False
    if res["skipped_langs"]:
        print(f"WARN: skipped languages (grammar unavailable): {res['skipped_langs']}", file=sys.stderr)
    print("GATE OK" if ok else "GATE FAIL", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
