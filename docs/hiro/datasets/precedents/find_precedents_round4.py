"""Round 4: Unexplored attack surface precedent search targeting Chainlink Payment Abstraction V2.

Searches for 12 new vulnerability patterns across 3 audit CSV databases.
"""

import csv
import json
import os
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

csv.field_size_limit(sys.maxsize)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "benchmarks", "data", "defi_audit_reports")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

# ============================================================
# 12 NEW patterns for Round 4
# ============================================================
PATTERNS = {
    "erc20_return_value": {
        "desc": "Tokens that return false instead of reverting on transfer failure - silent transfer failures",
        "keywords": [
            {"group": "return", "terms": ["return", "return value", "bool", "returns false"]},
            {"group": "transfer", "terms": ["transfer", "transferfrom", "safetransfer", "erc20"]},
            {"group": "silent", "terms": ["false", "silent", "unchecked", "ignored", "not checked", "no check"]},
        ],
        "min_groups": 2,
    },
    "order_struct_validation": {
        "desc": "Incomplete validation of order/struct fields allowing manipulation of trade parameters",
        "keywords": [
            {"group": "order", "terms": ["order", "struct", "gpv2", "cowswap", "swap order", "trade"]},
            {"group": "field", "terms": ["field", "parameter", "member", "property", "value"]},
            {"group": "validation", "terms": ["validation", "missing", "unchecked", "unvalidated", "not verified", "manipulat"]},
        ],
        "min_groups": 2,
    },
    "batch_processing_order": {
        "desc": "Order-dependent batch processing where reordering changes outcome or allows extraction",
        "keywords": [
            {"group": "batch", "terms": ["batch", "loop", "iterate", "array", "list", "multiple"]},
            {"group": "order", "terms": ["order", "ordering", "sequence", "first", "last", "reorder"]},
            {"group": "dependent", "terms": ["dependent", "affect", "impact", "outcome", "result", "different", "manipulat"]},
        ],
        "min_groups": 2,
    },
    "allowlist_race": {
        "desc": "Adding/removing assets from allowlist during active auction state causes inconsistency",
        "keywords": [
            {"group": "allowlist", "terms": ["allowlist", "whitelist", "allow list", "white list", "approved", "registered"]},
            {"group": "remove", "terms": ["remove", "delist", "revoke", "delete", "unregister", "disable"]},
            {"group": "active", "terms": ["active", "ongoing", "in progress", "during", "while", "pending", "race"]},
        ],
        "min_groups": 2,
    },
    "receiver_validation": {
        "desc": "Missing or weak receiver address validation - zero address, self-transfer, or contract check",
        "keywords": [
            {"group": "receiver", "terms": ["receiver", "recipient", "destination", "to address", "target"]},
            {"group": "address", "terms": ["address", "addr", "account"]},
            {"group": "validation", "terms": ["zero", "address(0)", "zero address", "validation", "missing", "unchecked", "invalid", "self"]},
        ],
        "min_groups": 2,
    },
    "price_feed_manipulation": {
        "desc": "Oracle price manipulation via flash loans, liquidity attacks, or TWAP manipulation",
        "keywords": [
            {"group": "price", "terms": ["price", "oracle", "feed", "chainlink", "data feed"]},
            {"group": "manipulate", "terms": ["manipulat", "inflat", "deflat", "artificial", "skew", "attack"]},
            {"group": "flash", "terms": ["flash", "loan", "liquidity", "pool", "twap", "spot", "sandwich"]},
        ],
        "min_groups": 2,
    },
    "approval_amount_desync": {
        "desc": "Approval amount doesn't match actual transferable amount - desync between approve and transfer",
        "keywords": [
            {"group": "approval", "terms": ["approval", "approve", "allowance", "forceapprove"]},
            {"group": "amount", "terms": ["amount", "balance", "value", "quantity"]},
            {"group": "mismatch", "terms": ["mismatch", "desync", "incorrect", "wrong", "exceed", "insufficient", "more than", "less than", "not enough"]},
        ],
        "min_groups": 2,
    },
    "auction_state_transition": {
        "desc": "Invalid state transitions in auction lifecycle - bid after end, start during active, etc.",
        "keywords": [
            {"group": "auction", "terms": ["auction", "sale", "dutch", "liquidat"]},
            {"group": "state", "terms": ["state", "status", "phase", "lifecycle", "stage"]},
            {"group": "transition", "terms": ["transition", "invalid", "illegal", "unexpected", "wrong state", "after end", "before start", "closed", "already"]},
        ],
        "min_groups": 2,
    },
    "multicall_delegation": {
        "desc": "delegatecall/multicall allowing privilege escalation or context confusion",
        "keywords": [
            {"group": "multicall", "terms": ["multicall", "multi call", "delegatecall", "delegate call", "batch call"]},
            {"group": "delegate", "terms": ["delegat", "context", "msg.sender", "caller", "authority"]},
            {"group": "privilege", "terms": ["privilege", "escalat", "bypass", "unauthorized", "impersonat", "spoof", "elevat"]},
        ],
        "min_groups": 2,
    },
    "view_function_manipulation": {
        "desc": "View functions returning manipulable data used for critical decisions",
        "keywords": [
            {"group": "view", "terms": ["view", "pure", "getter", "checkupkeep", "getprice", "read-only"]},
            {"group": "manipulate", "terms": ["manipulat", "inflat", "stale", "outdated", "incorrect", "unreliable"]},
            {"group": "decision", "terms": ["decision", "used by", "relied", "depend", "based on", "calculate", "determine"]},
        ],
        "min_groups": 2,
    },
    "partial_fill_accounting": {
        "desc": "Accounting errors with partial order fills - remaining amounts tracked incorrectly",
        "keywords": [
            {"group": "partial", "terms": ["partial", "partially", "incomplete", "fraction"]},
            {"group": "fill", "terms": ["fill", "filled", "execute", "settle", "swap"]},
            {"group": "accounting", "terms": ["accounting", "remaining", "leftover", "balance", "track", "update", "incorrect", "mismatch"]},
        ],
        "min_groups": 2,
    },
    "token_sweep_leftover": {
        "desc": "Leftover tokens stuck or extractable after operations - dust remaining in contract",
        "keywords": [
            {"group": "leftover", "terms": ["leftover", "remaining", "residual", "dust", "stuck", "stranded"]},
            {"group": "sweep", "terms": ["sweep", "recover", "rescue", "extract", "withdraw", "drain", "collect"]},
            {"group": "token", "terms": ["token", "erc20", "balance", "fund", "asset"]},
        ],
        "min_groups": 2,
    },
}

# CSV column mapping per source
CSV_CONFIGS = {
    "sherlock": {
        "file": "sherlock_all_issues.csv",
        "title_col": "title",
        "desc_col": "description",
        "severity_col": "severity",
        "contest_col": "contest_title",
        "id_col": "issue_id",
        "valid_severities": {"high", "medium"},
    },
    "codehawks": {
        "file": "codehawks_all_issues.csv",
        "title_col": "title",
        "desc_col": "description",
        "severity_col": "severity",
        "contest_col": "contest_name",
        "id_col": "finding_id",
        "valid_severities": {"high", "medium"},
    },
    "code4rena": {
        "file": "code4rena_all_issues.csv",
        "title_col": "title",
        "desc_col": "description",
        "severity_col": "severity",
        "contest_col": "contest_name",
        "id_col": "issue_id",
        "valid_severities": {"high", "medium", "3 (high)", "2 (med risk)"},
    },
}


def search_csv(csv_path, source_name, cfg, pattern_config):
    """Search a single CSV for matches against a pattern."""
    matches = []
    try:
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = row.get(cfg["title_col"], "")
                desc = row.get(cfg["desc_col"], "")[:3000]
                text = (title + " " + desc).lower()
                severity = row.get(cfg["severity_col"], "").strip().lower()

                if severity not in cfg["valid_severities"]:
                    continue

                matched_groups = 0
                matched_names = []
                for kw_group in pattern_config["keywords"]:
                    if any(term in text for term in kw_group["terms"]):
                        matched_groups += 1
                        matched_names.append(kw_group["group"])

                if matched_groups >= pattern_config["min_groups"]:
                    matches.append({
                        "source": source_name,
                        "contest": row.get(cfg["contest_col"], ""),
                        "issue_id": row.get(cfg["id_col"], ""),
                        "severity": row.get(cfg["severity_col"], ""),
                        "title": title,
                        "description": desc[:600],
                        "matched_groups": matched_groups,
                        "matched_group_names": matched_names,
                        "url": row.get("source_url", ""),
                    })
    except Exception as e:
        print(f"  Error reading {csv_path}: {e}", flush=True)
    return matches


def search_all_csvs(pattern_config):
    """Search all 3 CSVs (sherlock first, then codehawks, then code4rena) and return sorted results."""
    all_matches = []
    for source_name in ["sherlock", "codehawks", "code4rena"]:
        cfg = CSV_CONFIGS[source_name]
        csv_path = os.path.join(DATA_DIR, cfg["file"])
        if os.path.exists(csv_path):
            print(f"    Searching {source_name}...", end="", flush=True)
            matches = search_csv(csv_path, source_name, cfg, pattern_config)
            print(f" {len(matches)} hits", flush=True)
            all_matches.extend(matches)

    sev_order = {"high": 0, "3 (high)": 0, "medium": 1, "2 (med risk)": 1}
    all_matches.sort(key=lambda x: (-x["matched_groups"], sev_order.get(x["severity"].lower(), 2)))
    return all_matches


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 70, flush=True)
    print("ROUND 4: Unexplored attack surface precedent search", flush=True)
    print(f"Patterns: {len(PATTERNS)}", flush=True)
    print("=" * 70, flush=True)

    all_results = {}

    for pattern_id, config in PATTERNS.items():
        print(f"\n--- {pattern_id} ---", flush=True)
        print(f"  {config['desc'][:90]}", flush=True)
        t0 = time.time()
        matches = search_all_csvs(config)
        elapsed = time.time() - t0
        top15 = matches[:15]
        print(f"  Total: {len(matches)} matches, keeping top {len(top15)} ({elapsed:.1f}s)", flush=True)
        all_results[pattern_id] = {
            "description": config["desc"],
            "total_matches": len(matches),
            "top_matches": top15,
        }

        for i, m in enumerate(top15[:5]):
            groups_str = "+".join(m["matched_group_names"])
            print(f"  [{i+1}] [{m['severity']}] {m['source']}/{m['contest']} "
                  f"{m['issue_id']}: {m['title'][:70]} ({groups_str})", flush=True)

    # Save results
    output_path = os.path.join(OUTPUT_DIR, "precedent_round4_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {output_path}", flush=True)

    # Print summary table
    print(f"\n{'=' * 70}", flush=True)
    print("ROUND 4 SUMMARY", flush=True)
    print(f"{'=' * 70}", flush=True)
    print(f"{'Pattern':<30} {'Total':>6} {'High':>5} {'Med':>5} {'3-grp':>6}", flush=True)
    print("-" * 55, flush=True)
    for pid, data in all_results.items():
        matches = data["top_matches"]
        highs = sum(1 for m in matches if m["severity"].lower() in ("high", "3 (high)"))
        meds = sum(1 for m in matches if m["severity"].lower() in ("medium", "2 (med risk)"))
        three_grp = sum(1 for m in matches if m["matched_groups"] >= 3)
        print(f"  {pid:<28} {data['total_matches']:>6} {highs:>5} {meds:>5} {three_grp:>6}", flush=True)

    grand_total = sum(d["total_matches"] for d in all_results.values())
    print(f"\n  Grand total matches: {grand_total}", flush=True)
    print(f"\nOutput: {output_path}", flush=True)


if __name__ == "__main__":
    main()
