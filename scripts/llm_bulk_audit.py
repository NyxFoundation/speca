"""Bulk LLM audit: send top 2000 past findings through Claude to check applicability to Chainlink V2.

Approach:
  1. Collect top findings from all CSV pattern searches (score-sorted)
  2. Deduplicate by contest+issue_id
  3. Batch 20 per LLM call
  4. Ask: "Does this vulnerability exist in Chainlink V2?"
  5. Collect actionable results
"""

import csv
import json
import os
import subprocess
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

csv.field_size_limit(sys.maxsize)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "benchmarks", "data", "defi_audit_reports")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
CLAUDE_EXE = r"C:\Users\shieru_k\AppData\Roaming\npm\claude.cmd"

BATCH_SIZE = 20
MAX_FINDINGS = 2000
TARGET_BATCHES = MAX_FINDINGS // BATCH_SIZE  # 100

# All patterns to search
ALL_PATTERNS = {
    "dutch_auction_rounding": {
        "keywords": [
            {"group": "auction", "terms": ["dutch auction", "auction price", "descending"]},
            {"group": "math", "terms": ["round", "truncat", "precision", "division", "zero price", "underflow", "overflow"]},
        ],
        "min_groups": 2,
        "priority": 1,  # higher = more relevant
    },
    "auction_timing_griefing": {
        "keywords": [
            {"group": "auction", "terms": ["auction"]},
            {"group": "timing", "terms": ["block.timestamp", "timing", "front-run", "frontrun", "grief", "dos", "delay", "expire"]},
        ],
        "min_groups": 2,
        "priority": 2,
    },
    "auction_settlement_reentrancy": {
        "keywords": [
            {"group": "auction", "terms": ["auction", "settlement", "bid"]},
            {"group": "reentrancy", "terms": ["reentran", "re-entran", "callback", "cross-function"]},
        ],
        "min_groups": 2,
        "priority": 2,
    },
    "fee_on_transfer": {
        "keywords": [
            {"group": "token", "terms": ["fee-on-transfer", "fee on transfer", "deflationary", "rebas", "tax token"]},
            {"group": "impact", "terms": ["balance", "amount", "less than", "shortfall", "mismatch", "incorrect"]},
        ],
        "min_groups": 2,
        "priority": 1,
    },
    "token_donation_inflation": {
        "keywords": [
            {"group": "donation", "terms": ["donat", "direct transfer", "inflate", "inflation attack"]},
            {"group": "impact", "terms": ["balance", "manipulat", "accounting", "share", "first deposit"]},
        ],
        "min_groups": 2,
        "priority": 2,
    },
    "oracle_decimal_mismatch": {
        "keywords": [
            {"group": "oracle", "terms": ["oracle", "chainlink", "price feed", "price"]},
            {"group": "decimals", "terms": ["decimal", "precision", "scaling", "normali", "1e18", "1e8", "1e6"]},
        ],
        "min_groups": 2,
        "priority": 2,
    },
    "oracle_staleness_fallback": {
        "keywords": [
            {"group": "oracle", "terms": ["oracle", "chainlink", "price feed", "data feed", "aggregator"]},
            {"group": "staleness", "terms": ["stale", "staleness", "threshold", "freshness", "heartbeat", "fallback"]},
        ],
        "min_groups": 2,
        "priority": 3,
    },
    "eip1271_reentrancy": {
        "keywords": [
            {"group": "sig", "terms": ["isvalidsignature", "eip-1271", "eip1271", "signature valid"]},
            {"group": "vuln", "terms": ["reentran", "state", "view", "external call", "callback"]},
        ],
        "min_groups": 2,
        "priority": 1,
    },
    "order_replay": {
        "keywords": [
            {"group": "order", "terms": ["order", "nonce", "replay"]},
            {"group": "vuln", "terms": ["replay", "invalidat", "reuse", "duplicate", "double"]},
        ],
        "min_groups": 2,
        "priority": 1,
    },
    "pause_bypass": {
        "keywords": [
            {"group": "pause", "terms": ["pause", "whennotpaused", "unpause", "emergency"]},
            {"group": "bypass", "terms": ["bypass", "circumvent", "still callable", "not protected", "missing"]},
        ],
        "min_groups": 2,
        "priority": 1,
    },
    "performupkeep_manipulation": {
        "keywords": [
            {"group": "keeper", "terms": ["performupkeep", "checkupkeep", "keeper", "automation", "upkeep"]},
            {"group": "vuln", "terms": ["manipulat", "data", "bypass", "arbitrary", "unchecked", "performdata"]},
        ],
        "min_groups": 2,
        "priority": 3,
    },
    "multicall_callback_abuse": {
        "keywords": [
            {"group": "multicall", "terms": ["multicall", "callback", "delegatecall", "arbitrary call"]},
            {"group": "abuse", "terms": ["drain", "steal", "approv", "bypass", "unauthor", "exploit"]},
        ],
        "min_groups": 2,
        "priority": 2,
    },
    "approval_migration": {
        "keywords": [
            {"group": "approval", "terms": ["approv", "allowance", "permit"]},
            {"group": "lifecycle", "terms": ["migrat", "upgrad", "revok", "reset", "stale", "residual", "old"]},
        ],
        "min_groups": 2,
        "priority": 2,
    },
    "cowswap_gpv2": {
        "keywords": [
            {"group": "cow", "terms": ["cowswap", "cow swap", "gpv2", "cow protocol", "gnosis protocol"]},
            {"group": "any", "terms": ["settlement", "solver", "order", "exploit", "slippage", "signature"]},
        ],
        "min_groups": 2,
        "priority": 3,
    },
}

CHAINLINK_V2_CONTEXT = """## TARGET: Chainlink Payment Abstraction V2

### Contracts (in-scope):
1. **BaseAuction.sol** — Dutch auction selling protocol tokens (USDC/WETH) for LINK
   - `bid()`: permissionless via AUCTION_BIDDER_ROLE, reentrancy guard (s_entered), calculates assetOutAmount via oracle prices
   - `performUpkeep()`: AUCTION_WORKER_ROLE, starts/ends auctions atomically in batch loop
   - `_getAssetOutAmount()`: linear price decay with mulDivUp (rounds UP = favors protocol)
   - `checkUpkeep()`: view, uses balanceOf() for auction eligibility
2. **GPV2CompatibleAuction.sol** — Extends BaseAuction for CowSwap EIP-1271 settlement
   - `isValidSignature()`: view, validates GPv2Order at SETTLEMENT TIME (current price/timestamp)
   - `_onAuctionStart()`: forceApprove(vaultRelayer, balanceOf)
   - `_onAuctionEnd()`: forceApprove(vaultRelayer, 0)
3. **AuctionBidder.sol** — Wrapper for bidding with arbitrary solution execution
   - `bid()`: AUCTION_BIDDER_ROLE, encodes solution as callback data
   - `auctionCallback()`: decodes + executes _multiCall(calls), then forceApprove(amountOut)
4. **PriceManager.sol** — Dual oracle (Data Streams primary + Chainlink feed fallback)
   - `transmit()`: PRICE_ADMIN_ROLE, stores prices with timestamp
   - `_getAssetPrice()`: staleness check, decimal normalization
5. **Caller.sol** — Low-level call execution for _multiCall
6. **FeeAggregator.sol** — CCIP bridge, transferForSwap pulls tokens to auction
7. **WorkflowRouter.sol** — Permissioned multi-call with allowlisted targets/selectors

### Defenses:
- Global reentrancy guard (s_entered) on bid() + isValidSignature()
- SafeERC20 everywhere, forceApprove (not approve)
- whenNotPaused on all critical paths
- AccessControlDefaultAdminRules
- Constructor-based (non-upgradeable, no proxy)
- GPv2 domainSeparator + filledAmount for replay prevention
- _whenNoLiveAuctions for config changes
- Oracle decimal normalization on both paths
- Tokens: USDC (6 dec), WETH (18 dec), LINK (18 dec) — standard ERC20, no FOT

### KNOWN FINDINGS (already discovered):
- H-01: _multiCall in auctionCallback allows AUCTION_BIDDER_ROLE to bypass trust boundary
- M-01: Oracle staleness causes permissionless DoS on bid/performUpkeep
- M-03: Single feed revert in loop causes cross-asset DoS (no try-catch)
- M-02: Shared stalenessThreshold undermines dual-oracle fallback (Low)
- M-07: Future timestamp extends staleness window (Low, PRICE_ADMIN trusted)
- M-14: Stale approval after _setAuction migration (Low, residual ≈ 0)"""


def search_all_csvs(pattern_config):
    """Search CSV files for a pattern."""
    csv_files = [
        (os.path.join(DATA_DIR, "code4rena_all_issues.csv"), "code4rena"),
        (os.path.join(DATA_DIR, "sherlock_all_issues.csv"), "sherlock"),
        (os.path.join(DATA_DIR, "codehawks_all_issues.csv"), "codehawks"),
    ]
    matches = []
    for csv_path, source in csv_files:
        if not os.path.exists(csv_path):
            continue
        try:
            with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = row.get("title", "")
                    desc = row.get("description", "")[:2000]
                    text = (title + " " + desc).lower()
                    severity = row.get("severity", "").strip().lower()
                    if severity not in ("high", "medium", "3 (high)", "2 (med risk)"):
                        continue
                    matched = sum(
                        1 for kg in pattern_config["keywords"]
                        if any(t in text for t in kg["terms"])
                    )
                    if matched >= pattern_config["min_groups"]:
                        matches.append({
                            "source": source,
                            "contest": row.get("contest_name", row.get("contest_repo", "")),
                            "issue_id": row.get("issue_id", ""),
                            "severity": row.get("severity", "").strip(),
                            "title": title[:200],
                            "description": desc[:400],
                            "score": matched + pattern_config.get("priority", 0),
                        })
        except Exception as e:
            print(f"  Error: {e}", flush=True)
    return matches


def collect_top_findings():
    """Collect and deduplicate top findings across all patterns."""
    all_findings = []
    seen = set()

    for pat_id, config in ALL_PATTERNS.items():
        print(f"  Searching {pat_id}...", flush=True)
        matches = search_all_csvs(config)
        for m in matches:
            key = f"{m['source']}:{m['contest']}:{m['issue_id']}"
            if key not in seen:
                seen.add(key)
                m["pattern"] = pat_id
                all_findings.append(m)

    # Sort by score desc, then High before Medium
    sev_order = {"high": 0, "3 (high)": 0, "medium": 1, "2 (med risk)": 1}
    all_findings.sort(key=lambda x: (-x["score"], sev_order.get(x["severity"].lower(), 2)))

    return all_findings[:MAX_FINDINGS]


def call_claude(prompt):
    """Call Claude Sonnet."""
    try:
        result = subprocess.run(
            [CLAUDE_EXE, "--output-format", "json", "--model", "claude-sonnet-4-20250514", "-p"],
            input=prompt.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            shell=True,
        )
        stdout_text = result.stdout.decode("utf-8", errors="replace")
        if result.returncode != 0:
            return None
        try:
            output = json.loads(stdout_text)
            text = output.get("result", "") if isinstance(output, dict) else stdout_text
        except json.JSONDecodeError:
            text = stdout_text

        # Extract JSON array
        if isinstance(text, str):
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return []
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"  Error: {e}", flush=True)
        return None


def build_audit_prompt(batch, batch_idx, total_batches):
    """Build prompt for auditing a batch of findings against Chainlink V2."""
    summaries = []
    for i, f in enumerate(batch):
        summaries.append(
            f"[{i+1}] {f['severity']} | {f['source']}/{f['contest']} {f['issue_id']} | Pattern: {f['pattern']}\n"
            f"Title: {f['title']}\n"
            f"Desc: {f['description'][:300]}"
        )

    findings_block = "\n\n".join(summaries)

    return f"""You are a smart contract security auditor. For each historical finding below, determine if the SAME or SIMILAR vulnerability could exist in Chainlink V2.

{CHAINLINK_V2_CONTEXT}

## HISTORICAL FINDINGS (Batch {batch_idx+1}/{total_batches}):
{findings_block}

## TASK:
For each finding, answer: Does this vulnerability pattern exist in Chainlink V2, considering its specific defenses?

Return ONLY a JSON array. Each element:
- "index": finding number [1-{len(batch)}]
- "applicable": true/false
- "confidence": "high"/"medium"/"low"
- "reason": 1 sentence why it applies or doesn't
- "new_finding": true only if this reveals a vulnerability NOT in the known findings list

Only mark applicable=true if you are reasonably confident the pattern applies despite the listed defenses.
Return ONLY the JSON array, no markdown fences."""

    return prompt


def main():
    print("=" * 60, flush=True)
    print("BULK LLM AUDIT: 2000 findings x Chainlink V2", flush=True)
    print("=" * 60, flush=True)

    # Phase 1: Collect
    print("\nPhase 1: Collecting top findings from CSVs...", flush=True)
    findings = collect_top_findings()
    print(f"  Collected {len(findings)} deduplicated findings", flush=True)

    # Phase 2: Batch + LLM
    print(f"\nPhase 2: LLM audit ({len(findings)} findings, batch={BATCH_SIZE})...", flush=True)

    all_applicable = []
    total_batches = (len(findings) + BATCH_SIZE - 1) // BATCH_SIZE
    start_time = time.time()

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(findings))
        batch = findings[start:end]

        elapsed = time.time() - start_time
        eta = (elapsed / max(batch_idx, 1)) * (total_batches - batch_idx) if batch_idx > 0 else 0
        print(f"  Batch {batch_idx+1}/{total_batches} (findings {start+1}-{end}) "
              f"[{elapsed:.0f}s elapsed, ~{eta:.0f}s remaining]...", flush=True)

        prompt = build_audit_prompt(batch, batch_idx, total_batches)
        results = call_claude(prompt)

        if results is None:
            print(f"    FAILED (timeout/error), skipping", flush=True)
            continue

        for r in results:
            if r.get("applicable"):
                idx = r.get("index", 0) - 1
                if 0 <= idx < len(batch):
                    finding = batch[idx]
                    all_applicable.append({
                        "source": finding["source"],
                        "contest": finding["contest"],
                        "issue_id": finding["issue_id"],
                        "severity": finding["severity"],
                        "title": finding["title"],
                        "pattern": finding["pattern"],
                        "confidence": r.get("confidence", "unknown"),
                        "reason": r.get("reason", ""),
                        "new_finding": r.get("new_finding", False),
                    })

        # Progress stats
        if (batch_idx + 1) % 10 == 0:
            print(f"    --- {len(all_applicable)} applicable so far ---", flush=True)

    # Phase 3: Results
    total_time = time.time() - start_time
    new_findings = [a for a in all_applicable if a.get("new_finding")]
    high_conf = [a for a in all_applicable if a.get("confidence") == "high"]

    print(f"\n{'=' * 60}", flush=True)
    print("RESULTS", flush=True)
    print(f"{'=' * 60}", flush=True)
    print(f"Total findings audited: {len(findings)}", flush=True)
    print(f"Total batches: {total_batches}", flush=True)
    print(f"Time: {total_time:.0f}s ({total_time/60:.1f}min)", flush=True)
    print(f"Applicable: {len(all_applicable)}", flush=True)
    print(f"  High confidence: {len(high_conf)}", flush=True)
    print(f"  NEW findings (not in known list): {len(new_findings)}", flush=True)

    if new_findings:
        print(f"\n*** NEW FINDINGS ***", flush=True)
        for nf in new_findings:
            print(f"  [{nf['severity']}] {nf['source']}/{nf['contest']} {nf['issue_id']}: {nf['title'][:80]}", flush=True)
            print(f"    Pattern: {nf['pattern']} | Confidence: {nf['confidence']}", flush=True)
            print(f"    Reason: {nf['reason']}", flush=True)

    # Save
    output = {
        "summary": {
            "findings_audited": len(findings),
            "batches": total_batches,
            "time_seconds": round(total_time),
            "applicable_count": len(all_applicable),
            "high_confidence_count": len(high_conf),
            "new_findings_count": len(new_findings),
        },
        "new_findings": new_findings,
        "all_applicable": all_applicable,
    }

    out_file = os.path.join(OUTPUT_DIR, "bulk_llm_audit_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {out_file}", flush=True)


if __name__ == "__main__":
    main()
