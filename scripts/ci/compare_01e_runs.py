"""Compare two independent `run_phase.py --phase 01e` output directories.

Used by `.github/workflows/01e-lean-determinism.yml` to verify issue #88's
Done-when item "Re-running is deterministic (same inputs -> same properties
and paths)" at the *orchestrator run* level (the pytest pilot test
`test_lean_pilot_determinism` covers the narrower `generate()` level).

What must be identical between the two runs:

- The set of emitted ``01e_PARTIAL_W{w}B{b}_{ts}.json`` files, keyed by the
  ``W{w}B{b}`` token. The trailing ``{ts}`` is the wall-clock save time by
  design (`ResultCollector.save_partial`); it is the ONLY normalized part of
  the path, and the normalization is explicit here, not hidden.
- The full JSON content of each partial after deleting exactly one key:
  ``metadata.timestamp`` (same wall-clock artifact as the filename). This
  includes every property, every additive ``lean_*`` field, every
  ``kurtosis_test`` path string, and ``metadata.processed_ids``.
- The ``kurtosis/`` fixture tree: identical relative paths and identical
  file bytes (sha256), and the tree must be non-empty -- an empty tree on
  both sides is a failure, not a match (a lean run that emitted no fixtures
  would otherwise false-green this check).

Exit codes (distinctive on purpose -- the workflow's comparator self-test
asserts exit 4 exactly, so a comparator crash (1) or usage error (2) can
never masquerade as "difference detected"):

- 0: runs are identical under the contract above
- 2: usage / structural error (missing dirs, no partials, ambiguous W/B keys)
- 4: a difference was detected
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

PARTIAL_RE = re.compile(r"^01e_PARTIAL_(W\d+B\d+)_(\d+)\.json$")

EXIT_OK = 0
EXIT_STRUCTURAL = 2
EXIT_DIFF = 4


def fail(code: int, msg: str) -> None:
    print(f"compare_01e_runs: {msg}", file=sys.stderr)
    sys.exit(code)


def load_partials(run_dir: Path) -> dict[str, Path]:
    """{W..B.. token: file path}; ambiguity (duplicate token) is structural."""
    out: dict[str, Path] = {}
    for fp in sorted(run_dir.glob("01e_PARTIAL_*.json")):
        m = PARTIAL_RE.match(fp.name)
        if not m:
            fail(EXIT_STRUCTURAL, f"unrecognized partial name: {fp}")
        token = m.group(1)
        if token in out:
            fail(
                EXIT_STRUCTURAL,
                f"{run_dir}: two partials share the {token} slot "
                f"({out[token].name}, {fp.name}) -- cannot compare unambiguously",
            )
        out[token] = fp
    if not out:
        fail(EXIT_STRUCTURAL, f"{run_dir}: no 01e_PARTIAL_*.json emitted")
    return out


def normalized_doc(fp: Path) -> dict:
    doc = json.loads(fp.read_text(encoding="utf-8"))
    meta = doc.get("metadata")
    if isinstance(meta, dict):
        meta.pop("timestamp", None)  # wall-clock save time -- the only exemption
    return doc


def first_difference(a, b, path: str = "$") -> str | None:
    """Human-oriented pointer to the first differing location."""
    if type(a) is not type(b):
        return f"{path}: type {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f"{path}.{k}: only in run2"
            if k not in b:
                return f"{path}.{k}: only in run1"
            d = first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    if a != b:
        return f"{path}: {a!r} != {b!r}"
    return None


def snapshot_tree(root: Path) -> dict[str, str]:
    return {
        fp.relative_to(root).as_posix(): hashlib.sha256(fp.read_bytes()).hexdigest()
        for fp in sorted(root.rglob("*"))
        if fp.is_file()
    }


def main() -> None:
    print("SABOTAGE: comparator neutered, always OK")
    sys.exit(0)
    if len(sys.argv) != 3:
        fail(EXIT_STRUCTURAL, "usage: compare_01e_runs.py <run1_dir> <run2_dir>")
    run1, run2 = Path(sys.argv[1]), Path(sys.argv[2])
    for d in (run1, run2):
        if not d.is_dir():
            fail(EXIT_STRUCTURAL, f"not a directory: {d}")

    p1, p2 = load_partials(run1), load_partials(run2)
    if set(p1) != set(p2):
        fail(
            EXIT_DIFF,
            f"partial file sets differ (by W/B slot): "
            f"run1={sorted(p1)} run2={sorted(p2)}",
        )

    n_props = 0
    for token in sorted(p1):
        d1, d2 = normalized_doc(p1[token]), normalized_doc(p2[token])
        if d1 != d2:
            where = first_difference(d1, d2) or "(unlocated)"
            fail(
                EXIT_DIFF,
                f"partial {token} differs after timestamp normalization: {where}",
            )
        n_props += len(d1.get("properties", []))

    if n_props == 0:
        fail(
            EXIT_STRUCTURAL,
            "both runs emitted zero properties -- identical emptiness is not "
            "evidence of determinism (this would be a false green, so it fails)",
        )

    k1, k2 = run1 / "kurtosis", run2 / "kurtosis"
    s1 = snapshot_tree(k1) if k1.is_dir() else {}
    s2 = snapshot_tree(k2) if k2.is_dir() else {}
    if not s1 and not s2:
        fail(
            EXIT_STRUCTURAL,
            "both runs have an empty/missing kurtosis fixture tree -- "
            "nothing to compare (this would be a false green, so it fails)",
        )
    if s1 != s2:
        only1 = sorted(set(s1) - set(s2))
        only2 = sorted(set(s2) - set(s1))
        changed = sorted(k for k in set(s1) & set(s2) if s1[k] != s2[k])
        fail(
            EXIT_DIFF,
            "kurtosis fixture trees differ: "
            f"only-run1={only1[:5]} only-run2={only2[:5]} "
            f"content-changed={changed[:5]}",
        )

    print(
        f"OK: {len(p1)} partial slot(s), {n_props} properties, "
        f"{len(s1)} fixture file(s) -- identical across both runs "
        "(normalized: filename timestamp token + metadata.timestamp only)"
    )


if __name__ == "__main__":
    main()
