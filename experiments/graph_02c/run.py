"""Deterministic 02c driver (speca#157 Step 3).

Ties Steps 1-2 into a runnable, LLM-free 02c: build the client symbol index
once, resolve every property to a ``code_scope`` by rule, and apply the
confidence gate. High/medium-confidence resolutions are emitted directly;
low-confidence ones are flagged ``needs_llm_fallback`` so the 02c phase runs the
existing LLM resolver on *only that tail* — which guarantees system recall >=
the pure-LLM baseline (a resolution is never silently dropped), at a fraction of
the cost.

Output mirrors Phase 02c: each property gains ``code_scope`` (CodeScope-shaped).
``report`` gives the confidence distribution + fallback rate, the numbers the
accuracy gate (Step 4) asserts in CI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .resolver import resolve
from .symbols import SymbolIndex, build_index

# confidence -> whether the deterministic result is accepted (else LLM fallback)
_ACCEPT = {"high", "medium"}


@dataclass
class RunReport:
    n: int
    resolved: int                 # deterministically accepted (high+medium)
    fallback: int                 # low -> needs the LLM
    by_confidence: dict[str, int] = field(default_factory=dict)
    skipped_langs: list[str] = field(default_factory=list)

    @property
    def fallback_rate(self) -> float:
        return round(self.fallback / self.n, 4) if self.n else 0.0

    @property
    def resolved_rate(self) -> float:
        return round(self.resolved / self.n, 4) if self.n else 0.0


def run_02c(
    repo_path: str | Path,
    properties: list[dict[str, Any]],
    index: SymbolIndex | None = None,
) -> tuple[list[dict[str, Any]], RunReport]:
    """Resolve properties to code_scope over a client repo (no LLM).

    Returns (02c items, report). Each item = the property + ``code_scope``.
    Low-confidence items carry ``resolution_status = "needs_llm_fallback"`` so
    the caller can run the LLM 02c on just those.
    """
    index = index or build_index(repo_path)
    items: list[dict[str, Any]] = []
    by_conf: dict[str, int] = {"high": 0, "medium": 0, "low": 0}

    for prop in properties:
        r = resolve(prop, index)
        by_conf[r.confidence] = by_conf.get(r.confidence, 0) + 1
        code_scope = dict(r.code_scope)
        if r.confidence not in _ACCEPT:
            # never drop it — hand this one to the LLM tail
            code_scope["resolution_status"] = "needs_llm_fallback"
        item = dict(prop)
        item["code_scope"] = code_scope
        item["x_02c_confidence"] = r.confidence
        item["x_02c_matched_seeds"] = r.matched_seeds
        items.append(item)

    n = len(properties)
    resolved = by_conf["high"] + by_conf["medium"]
    report = RunReport(
        n=n,
        resolved=resolved,
        fallback=by_conf["low"],
        by_confidence=by_conf,
        skipped_langs=sorted(index.skipped_langs),
    )
    return items, report


def load_properties(path: str | Path) -> list[dict[str, Any]]:
    import json
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return doc.get("properties", []) if isinstance(doc, dict) else list(doc)


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="deterministic graph-based 02c (speca#157)")
    ap.add_argument("--repo", required=True, help="client source tree")
    ap.add_argument("--01e", dest="e01", required=True, help="01e_PARTIAL_*.json")
    ap.add_argument("--out", help="write 02c_PARTIAL JSON here")
    args = ap.parse_args()

    props = load_properties(args.e01)
    items, rep = run_02c(args.repo, props)
    print(
        f"02c(graph): n={rep.n} resolved={rep.resolved} ({rep.resolved_rate}) "
        f"fallback={rep.fallback} ({rep.fallback_rate}) by_conf={rep.by_confidence}"
        + (f" skipped_langs={rep.skipped_langs}" if rep.skipped_langs else "")
    )
    if args.out:
        Path(args.out).write_text(
            json.dumps({"results": items}, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"wrote {args.out}")
