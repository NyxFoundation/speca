"""Tests for the graph-02c eval harness (speca#157 Step 1): benchmark + metric."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.graph_02c.benchmark import GroundTruth, load_ground_truth, parse_code_path  # noqa: E402
from experiments.graph_02c.metric import evaluate, score_one  # noqa: E402


def _cs(*locs):
    return {"locations": [dict(l) for l in locs]}


def test_parse_code_path_full():
    gt = parse_code_path("a/b/File.cs::Class.Method::L77-108")
    assert gt.file == "a/b/File.cs" and gt.symbol == "Class.Method"
    assert gt.line_start == 77 and gt.line_end == 108


def test_parse_code_path_file_only():
    gt = parse_code_path("pkg/foo.go")
    assert gt.file == "pkg/foo.go" and gt.symbol is None and gt.line_start is None


def test_hit_on_symbol_match():
    gt = GroundTruth("c", "P1", "a/File.cs", "Class.Method", 77, 108, "raw")
    cs = _cs({"file": "File.cs", "symbol": "Method"})
    assert score_one(gt, cs).hit is True


def test_hit_on_line_overlap_without_symbol():
    gt = GroundTruth("c", "P1", "a/File.cs", "Class.Method", 77, 108, "raw")
    cs = _cs({"file": "a/File.cs", "line_start": 90, "line_end": 95})
    s = score_one(gt, cs)
    assert s.hit is True and s.file_hit is True


def test_file_hit_but_not_full_hit():
    gt = GroundTruth("c", "P1", "a/File.cs", "Class.Method", 77, 108, "raw")
    cs = _cs({"file": "File.cs", "symbol": "Unrelated", "line_start": 1, "line_end": 5})
    s = score_one(gt, cs)
    assert s.file_hit is True and s.hit is False


def test_miss_on_wrong_file():
    gt = GroundTruth("c", "P1", "a/File.cs", "Method", 77, 108, "raw")
    assert score_one(gt, _cs({"file": "Other.cs", "symbol": "Method"})).hit is False


def test_evaluate_recall_and_misses():
    gt1 = GroundTruth("c", "P1", "F.cs", "M1", 10, 20, "r")
    gt2 = GroundTruth("c", "P2", "G.cs", "M2", 30, 40, "r")
    rep = evaluate([
        (gt1, _cs({"file": "F.cs", "symbol": "M1"})),   # hit
        (gt2, _cs({"file": "Z.cs", "symbol": "M2"})),   # miss (wrong file)
    ])
    assert rep.n == 2 and rep.recall == 0.5 and rep.misses == ["P2"]


def test_load_ground_truth_from_committed_fixtures():
    """The committed benchmark exists and is parseable (thin: nethermind/C#)."""
    gt = load_ground_truth()
    assert len(gt) >= 10, "expected the committed 03 fixtures to yield ground truth"
    assert all(g.file for g in gt)
