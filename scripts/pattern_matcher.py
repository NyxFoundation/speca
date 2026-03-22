#!/usr/bin/env python3
"""
Pattern Matcher — match past DeFi vulnerability patterns against a Solidity codebase.

Loads CSV findings (with column normalization), extracts Solidity features via regex,
scores each pattern against the target code using a 4-component scoring system, and
outputs ranked results as JSON or CSV.

Usage:
    uv run python3 scripts/pattern_matcher.py \
      --target-dir 2026-03-chainlink/src \
      --csv outputs/past_defi_patterns.csv \
      --format json \
      --output outputs/pattern_match_results.json \
      --top-n 30
"""

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Pattern taxonomy: map DeFi attack pattern names to Solidity code signatures
# ---------------------------------------------------------------------------

PATTERN_SIGNATURES: dict[str, list[str]] = {
    "reentrancy+callback/hook": [r"\.call\{", r"Callback", r"onERC", r"tokensReceived"],
    "dutch+auction": [r"auction", r"[Dd]utch", r"price.*[Mm]ultiplier", r"decay"],
    "balance+stale/race": [r"balanceOf\(address\(this\)\)", r"\.slot0", r"totalSupply"],
    "price+oracle+swap": [r"latestRoundData", r"getAssetPrice", r"oracle", r"priceFeed"],
    "approval+frontrun/drain": [r"\.approve\(", r"forceApprove", r"allowance", r"type\(uint256\)\.max"],
    "EIP-1271/isValidSignature": [r"isValidSignature", r"EIP1271", r"IERC1271"],
    "keeper/upkeep/automation": [r"checkUpkeep", r"performUpkeep", r"onReport"],
    "settlement+solver/batch": [r"settle", r"GPv2", r"[Ss]olver", r"[Ss]ettlement"],
    "bid+callback/auction/flash": [r"\.bid\(", r"[Cc]allback", r"flash"],
    "cowswap/gpv2": [r"GPv2", r"CowSwap", r"[Cc]ow[Pp]rotocol"],
    "settlement+order": [r"[Oo]rder.*[Ss]ettle", r"settlement.*order"],
    "timestamp+manipulation": [r"block\.timestamp", r"block\.number"],
    "encode+collision/packed/abi": [r"abi\.encode", r"abi\.decode", r"encodePacked"],
    "view+manipulation/return": [r"function.*view.*returns", r"staticcall"],
    "safeTransfer+before/hook/reentrant": [r"safeTransfer", r"safeTransferFrom"],
    "loop+gas/DOS/unbounded": [r"for\s*\(", r"while\s*\(", r"\.length\b"],
    "decimals+mismatch/precision/loss": [r"decimals", r"10\s*\*\*", r"mulDiv"],
    "price+sandwich/frontrun/MEV": [r"getAmountsOut", r"swap\(", r"slot0"],
    "order+cancel/invalidate/replay/frontrun": [r"invalidate", r"cancel.*[Oo]rder", r"nonce"],
    "mapping+delete/clear/reset": [r"delete\s+s_", r"delete\s+mapping"],
    "balance+sweep": [r"balanceOf.*safeTransfer", r"sweep", r"withdraw.*all"],
    "callback+arbitrary/untrusted/malicious": [r"\.call\(", r"_multiCall", r"_call\("],
    "approval+infinite+drain/steal": [r"type\(uint256\)\.max", r"MAX_UINT"],
    "auction+grief/dos/block/prevent": [r"[Aa]uction", r"minBid", r"minAuctionSize"],
    "permit+replay/frontrun": [r"permit\(", r"PERMIT_TYPEHASH", r"nonces"],
    "receive+ether/native/fallback": [r"receive\(\)", r"fallback\(\)", r"payable", r"msg\.value"],
    "flash+loan/mint/attack": [r"flashLoan", r"flashMint", r"IERC3156"],
    "delegatecall+proxy/upgrade": [r"delegatecall", r"_implementation\(\)", r"upgradeTo"],
    "selfdestruct+proxy/destroy": [r"selfdestruct", r"SELFDESTRUCT"],
}

# Column normalization map: CSV column names -> canonical names
COLUMN_ALIASES: dict[str, str] = {
    "keyword_matched": "pattern_matched",
    "keyword": "pattern_matched",
    "pattern": "pattern_matched",
    "severity_level": "severity",
    "vuln_type": "vulnerability_type",
    "vuln_category": "vulnerability_type",
    "desc": "description",
    "source_url": "url",
    "link": "url",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single finding loaded from CSV."""
    pattern_matched: str = ""
    title: str = ""
    severity: str = ""
    vulnerability_type: str = ""
    description: str = ""
    url: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class SolidityFeatures:
    """Features extracted from a Solidity codebase."""
    function_sigs: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    external_calls: list[str] = field(default_factory=list)
    state_vars: list[str] = field(default_factory=list)
    access_control: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    raw_content: str = ""
    file_count: int = 0


@dataclass
class MatchResult:
    """Score result for a single pattern against the codebase."""
    pattern: str
    total_score: float
    pattern_match_score: float
    keyword_overlap_score: float
    mechanism_score: float
    specificity_bonus: float
    matched_signatures: list[str]
    matched_files: list[str]
    finding_count: int
    sample_titles: list[str]


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _normalize_columns(row: dict) -> dict:
    """Normalize CSV column names to canonical names."""
    normalized = {}
    for key, value in row.items():
        clean_key = key.strip().lower().replace(" ", "_")
        canonical = COLUMN_ALIASES.get(clean_key, clean_key)
        normalized[canonical] = value.strip() if isinstance(value, str) else value
    return normalized


def load_csv_findings(csv_paths: list[Path]) -> list[Finding]:
    """Load findings from one or more CSV files with column normalization."""
    findings: list[Finding] = []
    known_fields = {f.name for f in Finding.__dataclass_fields__.values() if f.name != "extra"}

    for csv_path in csv_paths:
        if not csv_path.exists():
            print(f"  [warn] CSV not found, skipping: {csv_path}", file=sys.stderr)
            continue

        with open(csv_path, "r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                norm = _normalize_columns(row)
                kwargs = {}
                extra = {}
                for k, v in norm.items():
                    if k in known_fields:
                        kwargs[k] = v
                    else:
                        extra[k] = v
                kwargs["extra"] = extra
                findings.append(Finding(**kwargs))

    return findings


# ---------------------------------------------------------------------------
# Solidity feature extraction
# ---------------------------------------------------------------------------

# Compiled regex patterns for feature extraction
_RE_FUNC_SIG = re.compile(
    r"function\s+(\w+)\s*\([^)]*\)\s*(?:external|public|internal|private|view|pure|payable|virtual|override|\s)*",
    re.MULTILINE,
)
_RE_MODIFIER = re.compile(r"modifier\s+(\w+)\s*\(", re.MULTILINE)
_RE_EXTERNAL_CALL = re.compile(
    r"(\w+(?:\.\w+)*)\s*\.\s*(call|delegatecall|staticcall|transfer|send)\s*[\({]",
    re.MULTILINE,
)
_RE_STATE_VAR = re.compile(
    r"^\s+(\w+(?:\[\w+\])*)\s+(?:public|private|internal|immutable|constant)?\s*(\w+)\s*[;=]",
    re.MULTILINE,
)
_RE_ACCESS_CONTROL = re.compile(
    r"(onlyOwner|onlyRole|require\s*\(\s*msg\.sender|_checkRole|hasRole|Ownable|AccessControl)",
    re.MULTILINE,
)
_RE_IMPORT = re.compile(r'import\s+[^;]+from\s+"([^"]+)"', re.MULTILINE)
_RE_IMPORT_SIMPLE = re.compile(r'import\s+"([^"]+)"', re.MULTILINE)


def extract_solidity_features(target_dir: Path) -> SolidityFeatures:
    """Recursively scan a directory for .sol files and extract features."""
    features = SolidityFeatures()
    sol_files = sorted(target_dir.rglob("*.sol"))
    features.file_count = len(sol_files)

    chunks: list[str] = []
    for sol_file in sol_files:
        try:
            content = sol_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"  [warn] cannot read {sol_file}: {exc}", file=sys.stderr)
            continue

        chunks.append(content)
        rel = str(sol_file.relative_to(target_dir))

        for m in _RE_FUNC_SIG.finditer(content):
            features.function_sigs.append(f"{rel}::{m.group(1)}")

        for m in _RE_MODIFIER.finditer(content):
            features.modifiers.append(f"{rel}::{m.group(1)}")

        for m in _RE_EXTERNAL_CALL.finditer(content):
            features.external_calls.append(f"{rel}::{m.group(1)}.{m.group(2)}")

        for m in _RE_STATE_VAR.finditer(content):
            features.state_vars.append(f"{rel}::{m.group(2)}")

        for m in _RE_ACCESS_CONTROL.finditer(content):
            features.access_control.append(f"{rel}::{m.group(1)}")

        for m in _RE_IMPORT.finditer(content):
            features.imports.append(m.group(1))
        for m in _RE_IMPORT_SIMPLE.finditer(content):
            features.imports.append(m.group(1))

    features.raw_content = "\n".join(chunks)

    # Deduplicate imports
    features.imports = sorted(set(features.imports))

    return features


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _pattern_match_score(pattern_name: str, features: SolidityFeatures) -> tuple[float, list[str], list[str]]:
    """
    Component 1: pattern signature match (0-50).
    Returns (score, matched_signatures, matched_files).
    """
    signatures = PATTERN_SIGNATURES.get(pattern_name)
    if not signatures:
        return 0.0, [], []

    matched_sigs: list[str] = []
    matched_files: set[str] = set()
    raw = features.raw_content

    for sig_re in signatures:
        try:
            compiled = re.compile(sig_re)
        except re.error:
            continue
        if compiled.search(raw):
            matched_sigs.append(sig_re)
            # Find which files contain this pattern
            for entry in features.function_sigs + features.external_calls + features.state_vars:
                parts = entry.split("::", 1)
                if len(parts) == 2:
                    fname = parts[0]
                    if fname not in matched_files:
                        # Check the raw content per-file would be expensive;
                        # approximate by checking if the file has related features
                        matched_files.add(fname)

    if not signatures:
        return 0.0, matched_sigs, sorted(matched_files)

    ratio = len(matched_sigs) / len(signatures)
    score = ratio * 50.0
    return round(score, 2), matched_sigs, sorted(matched_files)[:10]


def _keyword_overlap_score(finding: Finding, features: SolidityFeatures) -> float:
    """
    Component 2: keyword overlap between finding text and codebase (0-25).
    """
    # Combine finding text
    text = " ".join([
        finding.pattern_matched,
        finding.title,
        finding.description,
        finding.vulnerability_type,
    ]).lower()

    # Extract meaningful keywords (3+ chars, no common words)
    stopwords = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "has",
        "her", "was", "one", "our", "out", "this", "that", "with", "from",
        "they", "been", "have", "will", "each", "make", "when", "could",
        "into", "than", "its", "over", "such", "should", "would", "there",
        "their", "what", "about", "which", "were", "some", "these", "other",
        "function", "contract", "returns", "address", "uint256", "bool",
    }
    words = set(re.findall(r"[a-z][a-z0-9_]{2,}", text))
    keywords = words - stopwords

    if not keywords:
        return 0.0

    raw_lower = features.raw_content.lower()
    hits = sum(1 for kw in keywords if kw in raw_lower)

    ratio = hits / len(keywords) if keywords else 0
    return round(min(ratio * 25.0, 25.0), 2)


def _mechanism_score(pattern_name: str, features: SolidityFeatures) -> float:
    """
    Component 3: mechanism presence (0-15).
    Checks whether the codebase has the underlying mechanisms the attack relies on.
    """
    mechanisms: dict[str, list[str]] = {
        "reentrancy": [r"\.call\{", r"\.call\("],
        "oracle": [r"oracle", r"priceFeed", r"latestRoundData"],
        "flash": [r"flashLoan", r"flash", r"IERC3156"],
        "auction": [r"auction", r"bid"],
        "approval": [r"\.approve\(", r"allowance"],
        "delegation": [r"delegatecall", r"proxy"],
        "permit": [r"permit\(", r"nonces"],
        "loop": [r"for\s*\(", r"while\s*\("],
        "encoding": [r"abi\.encode", r"abi\.decode"],
        "transfer": [r"safeTransfer", r"\.transfer\("],
        "callback": [r"Callback", r"onERC", r"tokensReceived"],
        "sweep": [r"sweep", r"withdraw"],
        "settlement": [r"settle", r"[Ss]ettlement"],
        "timestamp": [r"block\.timestamp", r"block\.number"],
        "decimals": [r"decimals", r"10\s*\*\*"],
    }

    # Find which mechanisms are relevant to this pattern
    pattern_lower = pattern_name.lower()
    relevant: list[str] = []
    for mech_name, _ in mechanisms.items():
        if mech_name in pattern_lower:
            relevant.append(mech_name)

    # Also check for pattern-adjacent mechanisms
    pattern_parts = re.split(r"[+/]", pattern_lower)
    for mech_name, _ in mechanisms.items():
        for part in pattern_parts:
            if part in mech_name or mech_name in part:
                if mech_name not in relevant:
                    relevant.append(mech_name)

    if not relevant:
        return 0.0

    raw = features.raw_content
    hits = 0
    for mech_name in relevant:
        regexes = mechanisms[mech_name]
        for r_str in regexes:
            try:
                if re.search(r_str, raw):
                    hits += 1
                    break
            except re.error:
                continue

    ratio = hits / len(relevant) if relevant else 0
    return round(ratio * 15.0, 2)


def _specificity_bonus(pattern_name: str, findings: list[Finding], features: SolidityFeatures) -> float:
    """
    Component 4: specificity bonus (0-10).
    Rewards patterns that are highly specific to the codebase (rare pattern + strong code match).
    """
    signatures = PATTERN_SIGNATURES.get(pattern_name, [])
    if not signatures:
        return 0.0

    raw = features.raw_content

    # Count exact matches across signatures
    total_matches = 0
    for sig_re in signatures:
        try:
            total_matches += len(re.findall(sig_re, raw))
        except re.error:
            continue

    # More matches = more specific relevance, but cap the bonus
    if total_matches == 0:
        return 0.0

    # Scale: 1-5 matches -> 2-5 pts, 6-20 -> 5-8 pts, 20+ -> 8-10 pts
    if total_matches <= 5:
        return round(1.0 + total_matches * 0.8, 2)
    elif total_matches <= 20:
        return round(5.0 + (total_matches - 5) * 0.2, 2)
    else:
        return min(10.0, round(8.0 + (total_matches - 20) * 0.05, 2))


def score_pattern(
    pattern_name: str,
    findings_for_pattern: list[Finding],
    features: SolidityFeatures,
) -> MatchResult:
    """Score a single pattern against the extracted codebase features."""
    pm_score, matched_sigs, matched_files = _pattern_match_score(pattern_name, features)
    kw_score = max(
        (_keyword_overlap_score(f, features) for f in findings_for_pattern),
        default=0.0,
    )
    mech = _mechanism_score(pattern_name, features)
    spec = _specificity_bonus(pattern_name, findings_for_pattern, features)

    total = round(pm_score + kw_score + mech + spec, 2)

    sample_titles = [f.title for f in findings_for_pattern[:5] if f.title]

    return MatchResult(
        pattern=pattern_name,
        total_score=total,
        pattern_match_score=pm_score,
        keyword_overlap_score=kw_score,
        mechanism_score=mech,
        specificity_bonus=spec,
        matched_signatures=matched_sigs,
        matched_files=matched_files,
        finding_count=len(findings_for_pattern),
        sample_titles=sample_titles,
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def group_findings_by_pattern(findings: list[Finding]) -> dict[str, list[Finding]]:
    """Group findings by their pattern_matched field."""
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        key = f.pattern_matched.strip()
        if not key:
            continue
        groups.setdefault(key, []).append(f)
    return groups


def run_matching(
    target_dir: Path,
    csv_paths: list[Path],
    min_score: float = 0.0,
    top_n: Optional[int] = None,
) -> list[dict]:
    """Full matching pipeline: load CSVs, extract features, score, rank."""
    # Load findings
    findings = load_csv_findings(csv_paths)
    print(f"Loaded {len(findings)} findings from {len(csv_paths)} CSV(s)", file=sys.stderr)

    # Extract Solidity features
    features = extract_solidity_features(target_dir)
    print(
        f"Extracted features from {features.file_count} .sol files: "
        f"{len(features.function_sigs)} functions, "
        f"{len(features.modifiers)} modifiers, "
        f"{len(features.external_calls)} external calls, "
        f"{len(features.state_vars)} state vars",
        file=sys.stderr,
    )

    # Group findings by pattern
    groups = group_findings_by_pattern(findings)
    print(f"Found {len(groups)} distinct patterns in findings", file=sys.stderr)

    # Also score patterns from taxonomy that may not be in CSV
    all_patterns = set(groups.keys()) | set(PATTERN_SIGNATURES.keys())

    # Score each pattern
    results: list[MatchResult] = []
    for pattern in sorted(all_patterns):
        pattern_findings = groups.get(pattern, [])
        result = score_pattern(pattern, pattern_findings, features)
        if result.total_score >= min_score:
            results.append(result)

    # Sort by total score descending
    results.sort(key=lambda r: r.total_score, reverse=True)

    if top_n is not None:
        results = results[:top_n]

    return [asdict(r) for r in results]


def write_output(results: list[dict], fmt: str, output_path: Optional[Path]) -> None:
    """Write results to file or stdout."""
    if fmt == "json":
        text = json.dumps(results, indent=2, ensure_ascii=False)
    elif fmt == "csv":
        if not results:
            text = ""
        else:
            import io
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=results[0].keys())
            writer.writeheader()
            for row in results:
                flat = {
                    k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                    for k, v in row.items()
                }
                writer.writerow(flat)
            text = buf.getvalue()
    else:
        print(f"Unknown format: {fmt}", file=sys.stderr)
        sys.exit(1)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        print(f"Wrote {len(results)} results to {output_path}", file=sys.stderr)
    else:
        sys.stdout.write(text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Match DeFi vulnerability patterns against a Solidity codebase."
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        required=True,
        help="Path to the Solidity source directory to scan.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        nargs="+",
        required=True,
        help="One or more CSV files containing past findings.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        help="Output format (default: json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout).",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum total score to include in results (default: 0).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Return only the top N results.",
    )

    args = parser.parse_args()

    if not args.target_dir.is_dir():
        print(f"Error: --target-dir is not a directory: {args.target_dir}", file=sys.stderr)
        sys.exit(1)

    results = run_matching(
        target_dir=args.target_dir,
        csv_paths=args.csv,
        min_score=args.min_score,
        top_n=args.top_n,
    )

    write_output(results, args.format, args.output)


if __name__ == "__main__":
    main()
