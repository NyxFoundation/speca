#!/usr/bin/env python3
"""
Tests for scripts/pattern_matcher.py

Run with:
    uv run python3 -m pytest tests/test_pattern_matcher.py -v
"""

import csv
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from pattern_matcher import (
    Finding,
    SolidityFeatures,
    _keyword_overlap_score,
    _mechanism_score,
    _normalize_columns,
    _pattern_match_score,
    _specificity_bonus,
    extract_solidity_features,
    group_findings_by_pattern,
    load_csv_findings,
    run_matching,
    score_pattern,
    write_output,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SOLIDITY = """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@chainlink/contracts/src/v0.8/interfaces/AggregatorV3Interface.sol";

contract Vault {
    mapping(address => uint256) public balances;
    address public owner;
    AggregatorV3Interface public priceFeed;
    uint256 public totalSupply;

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
        totalSupply += msg.value;
    }

    function withdraw(uint256 amount) external {
        require(balances[msg.sender] >= amount, "insufficient");
        balances[msg.sender] -= amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "transfer failed");
    }

    function getPrice() public view returns (uint256) {
        (, int256 price, , , ) = priceFeed.latestRoundData();
        return uint256(price);
    }

    function sweep(address token) external onlyOwner {
        uint256 bal = IERC20(token).balanceOf(address(this));
        IERC20(token).safeTransfer(owner, bal);
    }

    function batchProcess(address[] calldata users) external {
        for (uint256 i = 0; i < users.length; i++) {
            // process
        }
    }

    receive() external payable {}
}
"""

SAMPLE_CSV_ROWS = [
    {
        "keyword_matched": "reentrancy+callback/hook",
        "title": "Reentrancy via callback in withdraw",
        "severity": "High",
        "description": "The withdraw function sends ether before updating state, allowing reentrancy via callback.",
        "url": "https://example.com/1",
    },
    {
        "keyword_matched": "price+oracle+swap",
        "title": "Oracle manipulation via flash loan",
        "severity": "High",
        "description": "Price oracle can be manipulated by flash loan to extract value.",
        "url": "https://example.com/2",
    },
    {
        "keyword_matched": "balance+sweep",
        "title": "Unrestricted sweep drains contract",
        "severity": "Medium",
        "description": "Sweep function can drain all tokens if access control is bypassed.",
        "url": "https://example.com/3",
    },
    {
        "keyword_matched": "loop+gas/DOS/unbounded",
        "title": "Unbounded loop causes DOS",
        "severity": "Medium",
        "description": "Loop over unbounded array can cause out-of-gas, blocking execution.",
        "url": "https://example.com/4",
    },
]


@pytest.fixture
def sol_dir(tmp_path: Path) -> Path:
    """Create a temp directory with a sample Solidity file."""
    sol_file = tmp_path / "Vault.sol"
    sol_file.write_text(SAMPLE_SOLIDITY, encoding="utf-8")
    return tmp_path


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    """Create a temp CSV file with sample findings."""
    csv_path = tmp_path / "findings.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SAMPLE_CSV_ROWS[0].keys())
        writer.writeheader()
        writer.writerows(SAMPLE_CSV_ROWS)
    return csv_path


@pytest.fixture
def features(sol_dir: Path) -> SolidityFeatures:
    """Extract features from sample Solidity."""
    return extract_solidity_features(sol_dir)


# ---------------------------------------------------------------------------
# CSV loading tests
# ---------------------------------------------------------------------------

class TestCSVLoading:
    def test_load_basic(self, csv_file: Path):
        findings = load_csv_findings([csv_file])
        assert len(findings) == 4

    def test_column_normalization(self, csv_file: Path):
        """keyword_matched should be normalized to pattern_matched."""
        findings = load_csv_findings([csv_file])
        assert findings[0].pattern_matched == "reentrancy+callback/hook"
        assert findings[1].pattern_matched == "price+oracle+swap"

    def test_load_multiple_csvs(self, tmp_path: Path):
        """Loading from two CSV files merges findings."""
        csv1 = tmp_path / "a.csv"
        csv2 = tmp_path / "b.csv"
        for p, rows in [(csv1, SAMPLE_CSV_ROWS[:2]), (csv2, SAMPLE_CSV_ROWS[2:])]:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
        findings = load_csv_findings([csv1, csv2])
        assert len(findings) == 4

    def test_missing_csv_skipped(self, tmp_path: Path):
        """Non-existent CSV is skipped with a warning."""
        findings = load_csv_findings([tmp_path / "nonexistent.csv"])
        assert findings == []

    def test_extra_columns_preserved(self, tmp_path: Path):
        """Extra columns go into the 'extra' dict."""
        csv_path = tmp_path / "extra.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["keyword_matched", "title", "custom_field"])
            writer.writeheader()
            writer.writerow({"keyword_matched": "test", "title": "Test", "custom_field": "val"})
        findings = load_csv_findings([csv_path])
        assert findings[0].extra["custom_field"] == "val"

    def test_normalize_columns(self):
        row = {"Keyword_Matched": "foo", "Severity_Level": "High", "Desc": "bar"}
        norm = _normalize_columns(row)
        assert norm["pattern_matched"] == "foo"
        assert norm["severity"] == "High"
        assert norm["description"] == "bar"


# ---------------------------------------------------------------------------
# Solidity feature extraction tests
# ---------------------------------------------------------------------------

class TestFeatureExtraction:
    def test_file_count(self, features: SolidityFeatures):
        assert features.file_count == 1

    def test_function_sigs(self, features: SolidityFeatures):
        func_names = [s.split("::")[-1] for s in features.function_sigs]
        assert "deposit" in func_names
        assert "withdraw" in func_names
        assert "getPrice" in func_names
        assert "sweep" in func_names
        assert "batchProcess" in func_names

    def test_modifiers(self, features: SolidityFeatures):
        mod_names = [s.split("::")[-1] for s in features.modifiers]
        assert "onlyOwner" in mod_names

    def test_external_calls(self, features: SolidityFeatures):
        # msg.sender.call{ should be detected
        call_strs = " ".join(features.external_calls)
        assert "call" in call_strs

    def test_access_control(self, features: SolidityFeatures):
        ac_strs = " ".join(features.access_control)
        assert "onlyOwner" in ac_strs or "require" in ac_strs

    def test_imports(self, features: SolidityFeatures):
        assert any("openzeppelin" in i for i in features.imports)
        assert any("chainlink" in i for i in features.imports)

    def test_raw_content(self, features: SolidityFeatures):
        assert "latestRoundData" in features.raw_content
        assert "balanceOf" in features.raw_content

    def test_empty_dir(self, tmp_path: Path):
        features = extract_solidity_features(tmp_path)
        assert features.file_count == 0
        assert features.function_sigs == []


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------

class TestScoring:
    def test_pattern_match_reentrancy(self, features: SolidityFeatures):
        """Reentrancy pattern should match .call{ and Callback-related sigs."""
        score, matched, _ = _pattern_match_score("reentrancy+callback/hook", features)
        assert score > 0
        assert any(".call" in s for s in matched)

    def test_pattern_match_oracle(self, features: SolidityFeatures):
        score, matched, _ = _pattern_match_score("price+oracle+swap", features)
        assert score > 0
        assert any("latestRoundData" in s for s in matched)

    def test_pattern_match_unknown(self, features: SolidityFeatures):
        """Unknown pattern returns zero."""
        score, matched, _ = _pattern_match_score("nonexistent+pattern", features)
        assert score == 0
        assert matched == []

    def test_keyword_overlap(self, features: SolidityFeatures):
        finding = Finding(
            pattern_matched="test",
            title="Reentrancy in withdraw via callback",
            description="withdraw function sends ether before updating balances state",
        )
        score = _keyword_overlap_score(finding, features)
        assert score > 0

    def test_mechanism_reentrancy(self, features: SolidityFeatures):
        score = _mechanism_score("reentrancy+callback/hook", features)
        assert score > 0

    def test_mechanism_oracle(self, features: SolidityFeatures):
        score = _mechanism_score("price+oracle+swap", features)
        # oracle mechanism should be detected via latestRoundData / priceFeed
        assert score > 0

    def test_mechanism_irrelevant(self, features: SolidityFeatures):
        """Pattern with no matching mechanism keywords should score 0."""
        score = _mechanism_score("nonexistent+xyz", features)
        assert score == 0

    def test_specificity_bonus(self, features: SolidityFeatures):
        bonus = _specificity_bonus("reentrancy+callback/hook", [], features)
        # .call{ appears at least once, so bonus > 0
        assert bonus > 0

    def test_specificity_bonus_unknown(self, features: SolidityFeatures):
        bonus = _specificity_bonus("nonexistent+pattern", [], features)
        assert bonus == 0

    def test_full_score_reentrancy(self, features: SolidityFeatures):
        findings = [
            Finding(
                pattern_matched="reentrancy+callback/hook",
                title="Reentrancy via callback in withdraw",
                description="The withdraw function sends ether before updating state.",
            )
        ]
        result = score_pattern("reentrancy+callback/hook", findings, features)
        assert result.total_score > 0
        assert result.pattern_match_score >= 0
        assert result.keyword_overlap_score >= 0
        assert result.mechanism_score >= 0
        assert result.specificity_bonus >= 0
        # Total = sum of components
        expected = (
            result.pattern_match_score
            + result.keyword_overlap_score
            + result.mechanism_score
            + result.specificity_bonus
        )
        assert abs(result.total_score - expected) < 0.1

    def test_score_bounds(self, features: SolidityFeatures):
        """All score components stay within their specified bounds."""
        for pattern in [
            "reentrancy+callback/hook",
            "price+oracle+swap",
            "loop+gas/DOS/unbounded",
            "balance+sweep",
        ]:
            result = score_pattern(pattern, [], features)
            assert 0 <= result.pattern_match_score <= 50
            assert 0 <= result.keyword_overlap_score <= 25
            assert 0 <= result.mechanism_score <= 15
            assert 0 <= result.specificity_bonus <= 10
            assert 0 <= result.total_score <= 100


# ---------------------------------------------------------------------------
# Grouping tests
# ---------------------------------------------------------------------------

class TestGrouping:
    def test_group_by_pattern(self, csv_file: Path):
        findings = load_csv_findings([csv_file])
        groups = group_findings_by_pattern(findings)
        assert "reentrancy+callback/hook" in groups
        assert "price+oracle+swap" in groups
        assert len(groups["reentrancy+callback/hook"]) == 1

    def test_empty_pattern_skipped(self):
        findings = [Finding(pattern_matched="", title="no pattern")]
        groups = group_findings_by_pattern(findings)
        assert groups == {}


# ---------------------------------------------------------------------------
# Integration / pipeline tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_run_matching(self, sol_dir: Path, csv_file: Path):
        results = run_matching(sol_dir, [csv_file])
        assert isinstance(results, list)
        assert len(results) > 0
        # Results are sorted descending by total_score
        scores = [r["total_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_run_matching_min_score(self, sol_dir: Path, csv_file: Path):
        results = run_matching(sol_dir, [csv_file], min_score=999)
        assert results == []

    def test_run_matching_top_n(self, sol_dir: Path, csv_file: Path):
        results = run_matching(sol_dir, [csv_file], top_n=2)
        assert len(results) <= 2

    def test_json_output(self, sol_dir: Path, csv_file: Path, tmp_path: Path):
        results = run_matching(sol_dir, [csv_file], top_n=5)
        out_path = tmp_path / "out.json"
        write_output(results, "json", out_path)
        loaded = json.loads(out_path.read_text(encoding="utf-8"))
        assert len(loaded) == len(results)

    def test_csv_output(self, sol_dir: Path, csv_file: Path, tmp_path: Path):
        results = run_matching(sol_dir, [csv_file], top_n=5)
        out_path = tmp_path / "out.csv"
        write_output(results, "csv", out_path)
        text = out_path.read_text(encoding="utf-8")
        assert "total_score" in text
        assert "pattern" in text


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_utf8_content(self, tmp_path: Path):
        """Handles UTF-8 content (Japanese comments) without errors."""
        sol_file = tmp_path / "Unicode.sol"
        sol_file.write_text(
            "// コメント\ncontract Unicode { function test() external {} }\n",
            encoding="utf-8",
        )
        features = extract_solidity_features(tmp_path)
        assert features.file_count == 1
        func_names = [s.split("::")[-1] for s in features.function_sigs]
        assert "test" in func_names

    def test_no_sol_files(self, tmp_path: Path):
        """Empty directory produces zero features."""
        (tmp_path / "readme.txt").write_text("not solidity")
        features = extract_solidity_features(tmp_path)
        assert features.file_count == 0

    def test_malformed_csv(self, tmp_path: Path):
        """Handles CSV with missing columns gracefully."""
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("title\nSome finding\n", encoding="utf-8")
        findings = load_csv_findings([csv_path])
        assert len(findings) == 1
        assert findings[0].title == "Some finding"
        assert findings[0].pattern_matched == ""
