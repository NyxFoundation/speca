"""Resolution-accuracy metric for graph-based 02c (speca#157).

Given a resolver's produced ``code_scope`` (a set of file/symbol/line
locations) and the ground-truth location of a property, score whether the
resolver *found* the right code. Recall is the load-bearing number: 02c must
not miss the code an audit needs (a missed location = a missed finding
downstream), so we optimise for recall and track precision as the cost of
over-resolution.

A location "hits" the ground truth when the FILE matches (basename or suffix
path) AND (the symbol matches OR the line range overlaps). File-only match is a
weaker "file_hit" reported separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .benchmark import GroundTruth


def _file_match(gt_file: str, loc_file: str) -> bool:
    if not gt_file or not loc_file:
        return False
    gt_file, loc_file = gt_file.replace("\\", "/"), loc_file.replace("\\", "/")
    if gt_file == loc_file:
        return True
    # basename match, or one path is a suffix of the other (repo-root differences)
    if gt_file.rsplit("/", 1)[-1] == loc_file.rsplit("/", 1)[-1]:
        return True
    return gt_file.endswith(loc_file) or loc_file.endswith(gt_file)


def _symbol_match(gt_symbol: str | None, loc_symbol: str | None) -> bool:
    if not gt_symbol or not loc_symbol:
        return False
    g = gt_symbol.split(".")[-1].lower()
    ls = loc_symbol.split(".")[-1].lower()
    return g == ls or g in loc_symbol.lower() or ls in gt_symbol.lower()


def _line_overlap(gt: GroundTruth, ls: int | None, le: int | None) -> bool:
    if gt.line_start is None or ls is None:
        return False
    le = le if le is not None else ls
    return not (le < gt.line_start or ls > (gt.line_end or gt.line_start))


def _locations(code_scope: Any) -> list[dict]:
    if isinstance(code_scope, dict):
        return code_scope.get("locations") or []
    return getattr(code_scope, "locations", []) or []


@dataclass
class Score:
    hit: bool          # file AND (symbol OR line) — the property is resolved
    file_hit: bool     # file matched (weaker)
    n_locations: int   # resolver locations (precision proxy)


def score_one(gt: GroundTruth, code_scope: Any) -> Score:
    locs = _locations(code_scope)
    file_hit = hit = False
    for loc in locs:
        lf = loc.get("file") or loc.get("path") or ""
        lsym = loc.get("symbol") or loc.get("name")
        lr = loc.get("line_range") or {}
        ls = lr.get("start") if lr else (loc.get("line_start") or loc.get("start_line"))
        le = lr.get("end") if lr else (loc.get("line_end") or loc.get("end_line"))
        if _file_match(gt.file, lf):
            file_hit = True
            if _symbol_match(gt.symbol, lsym) or _line_overlap(gt, ls, le):
                hit = True
                break
    return Score(hit=hit, file_hit=file_hit, n_locations=len(locs))


@dataclass
class Report:
    n: int
    recall: float          # fraction hit (file AND symbol/line)
    file_recall: float     # fraction file_hit
    avg_locations: float   # mean resolver locations per property (precision proxy)
    misses: list[str]      # property_ids not hit


def evaluate(pairs: Iterable[tuple[GroundTruth, Any]]) -> Report:
    pairs = list(pairs)
    n = len(pairs)
    if n == 0:
        return Report(0, 0.0, 0.0, 0.0, [])
    scores = [(gt, score_one(gt, cs)) for gt, cs in pairs]
    hits = sum(1 for _, s in scores if s.hit)
    file_hits = sum(1 for _, s in scores if s.file_hit)
    locs = sum(s.n_locations for _, s in scores)
    misses = [gt.property_id for gt, s in scores if not s.hit]
    return Report(
        n=n,
        recall=round(hits / n, 4),
        file_recall=round(file_hits / n, 4),
        avg_locations=round(locs / n, 2),
        misses=misses,
    )
