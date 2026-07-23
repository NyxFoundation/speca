"""Ground-truth benchmark for graph-based deterministic 02c (speca#157).

02c resolves a property to a `code_scope` (file / symbol / line locations). To
guarantee the graph resolver's accuracy we measure it against ground truth:
the `code_path` recorded on real Phase 03 findings — `file::Symbol::Lstart-end`
— which is where the audited property's relevant code actually lives.

`load_ground_truth()` mines those pairs from committed 03 fixtures. NOTE: the
committed set is thin (nethermind / C# only); the full accuracy guarantee needs
this benchmark widened to the 6 client languages (see speca#157 Step 1) by
running the LLM 02c to produce reference code_scopes per client.
"""
from __future__ import annotations

import glob
import json
import re
from dataclasses import dataclass
from pathlib import Path

_FIXTURES = Path(__file__).resolve().parents[3] / "cli/test/fixtures/sherlock-rq1"

# file::Symbol.path::Lstart-end   (Lstart-end optional; symbol optional)
_CODE_PATH = re.compile(
    r"^(?P<file>[^:]+)"
    r"(?:::(?P<symbol>[^:]+?))?"
    r"(?:::L(?P<start>\d+)(?:-(?P<end>\d+))?)?$"
)


@dataclass(frozen=True)
class GroundTruth:
    client: str
    property_id: str
    file: str
    symbol: str | None
    line_start: int | None
    line_end: int | None
    raw: str


def parse_code_path(raw: str) -> GroundTruth | None:
    m = _CODE_PATH.match(raw.strip())
    if not m or not m.group("file"):
        return None
    s, e = m.group("start"), m.group("end")
    return GroundTruth(
        client="", property_id="",
        file=m.group("file").strip(),
        symbol=(m.group("symbol") or "").strip() or None,
        line_start=int(s) if s else None,
        line_end=int(e) if e else (int(s) if s else None),
        raw=raw,
    )


def _iter_findings(path: str):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return
    if isinstance(d, list):
        items = d
    else:
        items = d.get("results") or next(
            (v for v in d.values() if isinstance(v, list)), []
        )
    yield from items


def load_ground_truth(fixtures_dir: Path = _FIXTURES) -> list[GroundTruth]:
    """Mine (property_id -> code_path) pairs from committed 03 fixtures."""
    out: list[GroundTruth] = []
    for f in sorted(glob.glob(str(fixtures_dir / "*/03_PARTIAL_*.json"))):
        client = Path(f).parent.name
        for finding in _iter_findings(f):
            cp = finding.get("code_path")
            pid = finding.get("property_id")
            if not (isinstance(cp, str) and "::" in cp and pid):
                continue
            gt = parse_code_path(cp)
            if gt:
                out.append(
                    GroundTruth(
                        client=client, property_id=str(pid),
                        file=gt.file, symbol=gt.symbol,
                        line_start=gt.line_start, line_end=gt.line_end, raw=cp,
                    )
                )
    return out


if __name__ == "__main__":
    gt = load_ground_truth()
    from collections import Counter
    print(f"ground-truth pairs: {len(gt)}")
    print("by client:", Counter(g.client for g in gt).most_common())
    print("languages:", Counter(g.file.rsplit('.', 1)[-1] for g in gt if '.' in g.file).most_common())
