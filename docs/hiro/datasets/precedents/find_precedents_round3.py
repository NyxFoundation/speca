"""Round 3: Creative/compound precedent search targeting Chainlink Payment Abstraction V2.

Searches for 12 new vulnerability patterns across 3 audit CSV databases,
then calls Claude Sonnet to analyze top findings against the target code.
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

# ============================================================
# 12 NEW compound search patterns
# ============================================================
PATTERNS = {
    "callback_amount_mismatch": {
        "desc": "safeTransferFrom callback with mismatched amount — attacker receives tokens via callback then underpays on pull",
        "keywords": [
            {"group": "transfer", "terms": ["safetransferfrom", "safetransfer", "transfer"]},
            {"group": "callback", "terms": ["callback", "hook", "oncall", "fallback", "receive"]},
            {"group": "amount", "terms": ["amount", "mismatch", "less than", "incorrect", "wrong amount", "short"]},
        ],
        "min_groups": 2,
    },
    "auction_ending_race": {
        "desc": "Race condition at auction end — last-block bids, front-running auction close, or end-time manipulation",
        "keywords": [
            {"group": "auction", "terms": ["auction", "dutch auction", "bid", "liquidat"]},
            {"group": "ending", "terms": ["end", "close", "expire", "final", "last", "deadline", "finish"]},
            {"group": "race", "terms": ["race", "front-run", "frontrun", "mev", "sandwich", "last block", "timing", "manipulat"]},
        ],
        "min_groups": 2,
    },
    "price_calc_overflow": {
        "desc": "Price calculation edge cases — multiplier overflow/underflow, zero price, or precision loss in price math",
        "keywords": [
            {"group": "price", "terms": ["price", "oracle", "rate", "exchange rate"]},
            {"group": "math", "terms": ["multiplier", "calculat", "formula", "math", "arithmetic", "mulDiv"]},
            {"group": "edge", "terms": ["overflow", "underflow", "zero", "revert", "division by zero", "extreme", "edge case", "precision"]},
        ],
        "min_groups": 2,
    },
    "pause_bypass": {
        "desc": "Pause mechanism bypass — front-running pause, unpausing attack, or operations during paused state",
        "keywords": [
            {"group": "pause", "terms": ["pause", "pausable", "paused", "whennotpaused", "emergency"]},
            {"group": "bypass", "terms": ["bypass", "circumvent", "front-run", "unpause", "skip", "ignore", "during pause"]},
        ],
        "min_groups": 2,
    },
    "balance_diff_accounting": {
        "desc": "Balance before/after accounting mismatch — actual received differs from expected due to fees/rebasing/hooks",
        "keywords": [
            {"group": "balance", "terms": ["balanceof", "balance", "balance before", "balance after"]},
            {"group": "diff", "terms": ["before", "after", "difference", "actual", "received", "delta"]},
            {"group": "issue", "terms": ["mismatch", "incorrect", "less", "more", "fee", "rebase", "deflat", "inflat", "accounting"]},
        ],
        "min_groups": 2,
    },
    "immutable_misconfiguration": {
        "desc": "Immutable variable set wrong at deployment — cannot be changed later, permanently breaks protocol",
        "keywords": [
            {"group": "immutable", "terms": ["immutable", "constructor", "constant", "hardcoded", "deploy"]},
            {"group": "wrong", "terms": ["wrong", "incorrect", "invalid", "misconfigur", "cannot change", "cannot update", "permanent", "stuck"]},
        ],
        "min_groups": 2,
    },
    "forceApprove_edge_cases": {
        "desc": "forceApprove / safeIncreaseAllowance edge cases — approval to wrong address, stale approval, or race",
        "keywords": [
            {"group": "approve", "terms": ["forceapprove", "safeincreaseallowance", "safedecreaseallowance", "approve", "allowance"]},
            {"group": "edge", "terms": ["stale", "race", "front-run", "wrong", "excess", "unlimited", "max", "revoke", "old", "previous", "leftover"]},
        ],
        "min_groups": 2,
    },
    "domain_separator_replay": {
        "desc": "EIP-712 domainSeparator replay — cross-chain signature replay, fork replay, or missing chain ID validation",
        "keywords": [
            {"group": "domain", "terms": ["domainseparator", "domain separator", "eip-712", "eip712", "typehash"]},
            {"group": "replay", "terms": ["replay", "cross-chain", "fork", "chain id", "chainid", "reuse", "duplicate"]},
        ],
        "min_groups": 2,
    },
    "fee_aggregator_transfer": {
        "desc": "Fee aggregator transferForSwap pattern — external pull fails, returns less, or is called with wrong params",
        "keywords": [
            {"group": "fee", "terms": ["fee aggregator", "feeaggregator", "fee collector", "treasury", "transferforswap"]},
            {"group": "transfer", "terms": ["transfer", "pull", "withdraw", "collect", "sweep"]},
            {"group": "issue", "terms": ["fail", "revert", "insufficient", "zero", "empty", "wrong", "partial", "stuck"]},
        ],
        "min_groups": 2,
    },
    "bid_amount_edge": {
        "desc": "Bid with zero/minimum/dust/overflow amount — breaks auction state or extracts value",
        "keywords": [
            {"group": "bid", "terms": ["bid", "auction", "offer", "purchase"]},
            {"group": "amount", "terms": ["amount", "value", "quantity", "size"]},
            {"group": "edge", "terms": ["zero", "minimum", "dust", "overflow", "underflow", "too small", "too large", "max", "type(uint256)"]},
        ],
        "min_groups": 2,
    },
    "callback_griefing": {
        "desc": "Auction/swap callback griefing — callback reverts to block settlement, consume gas, or replay",
        "keywords": [
            {"group": "callback", "terms": ["callback", "hook", "oncall", "fallback", "flash"]},
            {"group": "grief", "terms": ["revert", "fail", "grief", "dos", "block", "gas", "consume", "infinite"]},
            {"group": "context", "terms": ["auction", "swap", "settlement", "liquidat", "flash loan", "lending"]},
        ],
        "min_groups": 2,
    },
    "silent_try_catch": {
        "desc": "try/catch swallowing errors — silent failure hides reverts, leads to incorrect state or lost funds",
        "keywords": [
            {"group": "try", "terms": ["try", "try/catch", "try catch"]},
            {"group": "catch", "terms": ["catch", "silent", "swallow", "ignore", "suppress", "empty catch"]},
            {"group": "impact", "terms": ["fail", "lost", "incorrect", "state", "revert", "error", "funds"]},
        ],
        "min_groups": 2,
    },
}

# CSV column mapping per source
CSV_CONFIGS = {
    "code4rena": {
        "file": "code4rena_all_issues.csv",
        "title_col": "title",
        "desc_col": "description",
        "severity_col": "severity",
        "contest_col": "contest_name",
        "id_col": "issue_id",
        "valid_severities": {"high", "medium", "3 (high)", "2 (med risk)"},
    },
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
    """Search all 3 CSVs and return sorted results."""
    all_matches = []
    for source_name, cfg in CSV_CONFIGS.items():
        csv_path = os.path.join(DATA_DIR, cfg["file"])
        if os.path.exists(csv_path):
            print(f"    Searching {source_name}...", end="", flush=True)
            matches = search_csv(csv_path, source_name, cfg, pattern_config)
            print(f" {len(matches)} hits", flush=True)
            all_matches.extend(matches)

    sev_order = {"high": 0, "3 (high)": 0, "medium": 1, "2 (med risk)": 1}
    all_matches.sort(key=lambda x: (-x["matched_groups"], sev_order.get(x["severity"].lower(), 2)))
    return all_matches


def call_claude(prompt, timeout=180):
    """Call Claude Sonnet via CLI."""
    try:
        result = subprocess.run(
            [CLAUDE_EXE, "--output-format", "json", "--model", "claude-sonnet-4-20250514", "-p"],
            input=prompt.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=True,
        )
        stdout_text = result.stdout.decode("utf-8", errors="replace")
        try:
            output = json.loads(stdout_text)
            return output.get("result", stdout_text) if isinstance(output, dict) else stdout_text
        except json.JSONDecodeError:
            return stdout_text
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ERROR: {e}]"


TARGET_CODE = """## TARGET: Chainlink Payment Abstraction V2

### BaseAuction.sol key code:
- `bid()`: L410-458. s_entered reentrancy guard. Gets price via _getAssetPrice(asset, true).
  Calculates assetOutAmount via _getAssetOutAmount. safeTransfer(asset->bidder) BEFORE callback.
  Then IAuctionCallback(msg.sender).auctionCallback(...). Then safeTransferFrom(assetOut<-bidder).
- `_getAssetOutAmount()`: L777-803. Uses FixedPointMathLib.mulDiv/mulDivUp/mulWadUp.
  priceMultiplier = startingPriceMultiplier - (startingPriceMultiplier-endingPriceMultiplier)*elapsed/duration.
  auctionUsdValue = amountIn.mulDivUp(assetInUsdPrice, 10**decimals).mulWadUp(priceMultiplier).
  return auctionUsdValue.mulDivUp(10**assetOutDecimals, assetOutUsdPrice).
- `performUpkeep()`: L305-370. AUCTION_WORKER_ROLE. Calls feeAggregator.transferForSwap() externally.
  Starts/ends auctions. _onAuctionEnd transfers remaining balance back to feeAggregator.
- `checkUpkeep()`: L216-294. view. Iterates s_allowlistedAssets (EnumerableSet).

### PriceManager.sol key code:
- `_getAssetPrice()`: L372-419. Prioritizes Data Streams price. Falls back to Chainlink data feed.
  Uses SafeCast: answer.toUint256() (reverts on negative). Same stalenessThreshold for both.
- `transmit()`: L133-183. PRICE_ADMIN_ROLE. Checks observationsTimestamp >= block.timestamp - stalenessThreshold.
  No upper bound check on future timestamps. Uses int192->uint256 SafeCast.

### GPV2CompatibleAuction.sol key code:
- `_onAuctionStart()`: forceApprove(vaultRelayer, FULL balanceOf) -- approves entire contract balance.
- `_onAuctionEnd()`: forceApprove(vaultRelayer, 0) -- revokes.
- `isValidSignature()`: validates order at settlement time with current prices.

### AuctionBidder.sol key code:
- `bid()`: AUCTION_BIDDER_ROLE. If solution.length > 0, encodes as callback data.
  Else forceApprove(auction, getAssetOutAmount). After bid, transfers leftover to receiver.
- `auctionCallback()`: Only callable by auction contract. Decodes calls, executes _multiCall(calls).
  Then forceApprove(assetOut, amountOut).
- `_setAuction()`: No approval revocation of old auction.

### Caller.sol:
- `_call()`: Low-level call with returndata.
- `_multiCall()`: Iterates Call[] array, executes each via _call().

### Key facts:
- Tokens: USDC (6 dec), WETH (18 dec), LINK (18 dec) -> assetOut is LINK
- SafeERC20 used everywhere
- ReentrancyGuard via s_entered flag in bid()
- Access roles: DEFAULT_ADMIN_ROLE, AUCTION_WORKER_ROLE, AUCTION_BIDDER_ROLE, PRICE_ADMIN_ROLE, ASSET_ADMIN_ROLE
- CowSwap GPv2 integration: vaultRelayer pulls tokens during settlement
- feeAggregator is external contract that holds collected fees

### KNOWN findings (already found, do NOT re-report):
- H-01: Unrestricted _multiCall in auctionCallback (AUCTION_BIDDER_ROLE escalation)
- M-01: Oracle staleness DoS (permissionless, bid/performUpkeep revert)
- M-02: Shared stalenessThreshold across feeds
- M-03: Single feed revert in loop causes cross-asset DoS
- M-04: QA (AUCTION_WORKER_ROLE trusted)
- M-05: QA (non-economic)
- M-06: QA (exact approve self-protection)
- M-07: Future timestamps in transmit
- M-14: Stale approval after _setAuction"""


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 70, flush=True)
    print("ROUND 3: Creative/compound precedent search", flush=True)
    print(f"Patterns: {len(PATTERNS)}", flush=True)
    print("=" * 70, flush=True)

    all_results = {}
    promising = []

    for pattern_id, config in PATTERNS.items():
        print(f"\n--- {pattern_id} ---", flush=True)
        print(f"  {config['desc'][:90]}", flush=True)
        t0 = time.time()
        matches = search_all_csvs(config)
        elapsed = time.time() - t0
        print(f"  Total: {len(matches)} matches ({elapsed:.1f}s)", flush=True)
        all_results[pattern_id] = {
            "description": config["desc"],
            "total_matches": len(matches),
            "top_matches": matches[:15],
            "llm_analysis": None,
        }

        for i, m in enumerate(matches[:5]):
            groups_str = "+".join(m["matched_group_names"])
            print(f"  [{i+1}] [{m['severity']}] {m['source']}/{m['contest']} "
                  f"{m['issue_id']}: {m['title'][:65]} ({groups_str})", flush=True)

        if len(matches) >= 2:
            promising.append(pattern_id)

    # Save intermediate raw results
    raw_output = os.path.join(OUTPUT_DIR, "precedent_round3_results.json")
    with open(raw_output, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nIntermediate results saved: {raw_output}", flush=True)

    # LLM analysis on promising patterns
    print(f"\n{'=' * 70}", flush=True)
    print(f"LLM ANALYSIS: {len(promising)} patterns with >= 2 matches", flush=True)
    print(f"{'=' * 70}", flush=True)

    for pattern_id in promising:
        data = all_results[pattern_id]
        matches = data["top_matches"]
        if not matches:
            continue

        print(f"\n>>> Analyzing: {pattern_id} ({data['total_matches']} total matches) <<<", flush=True)

        summaries = []
        for i, m in enumerate(matches[:15]):
            summaries.append(
                f"[{i+1}] {m['source']}/{m['contest']} {m['issue_id']} ({m['severity']})\n"
                f"Title: {m['title']}\n"
                f"Desc: {m['description'][:400]}"
            )
        findings_block = "\n\n".join(summaries)

        prompt = f"""You are a smart contract security researcher analyzing Chainlink Payment Abstraction V2 for a competitive audit (Code4rena style).

{TARGET_CODE}

## Pattern being analyzed: {pattern_id}
{PATTERNS[pattern_id]['desc']}

## Historical audit findings matching this pattern ({data['total_matches']} total, top {len(matches)} shown):
{findings_block}

## TASK:
Based on the historical findings above, determine whether the same vulnerability pattern could exist in the Chainlink V2 code. Think step by step:

1. Which specific historical findings are most relevant to Chainlink V2's architecture?
2. Map the vulnerability to EXACT functions in the target code (cite function name + line range).
3. Describe a concrete attack scenario step-by-step.
4. Is this permissionless or does it require a role? (Only permissionless and AUCTION_BIDDER_ROLE attacks are in-scope.)
5. Is this already covered by known findings? If so, which one?
6. Estimate severity: High / Medium / Low / QA / Not Applicable.

IMPORTANT constraints:
- DEFAULT_ADMIN_ROLE, AUCTION_WORKER_ROLE, PRICE_ADMIN_ROLE, ASSET_ADMIN_ROLE are trusted/OOS.
- Only report findings NOT covered by the known findings list above.
- Be specific about code locations. Generic/vague findings are useless.
- If the pattern genuinely does not apply, say "NOT APPLICABLE" and explain why.

Return structured JSON with this format:
{{
  "pattern": "{pattern_id}",
  "applicable": true/false,
  "findings": [
    {{
      "title": "...",
      "severity": "High/Medium/Low/QA",
      "function": "contract.function() L<line>",
      "attack_scenario": "1. ... 2. ... 3. ...",
      "permissionless": true/false,
      "role_required": "none/AUCTION_BIDDER_ROLE",
      "not_covered_by": "explanation of why this is new",
      "confidence": "high/medium/low"
    }}
  ],
  "reasoning": "..."
}}"""

        response = call_claude(prompt, timeout=200)
        all_results[pattern_id]["llm_analysis"] = response
        print(response[:2000] if isinstance(response, str) else str(response)[:2000], flush=True)

    # Save final results
    with open(raw_output, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nFinal results saved: {raw_output}", flush=True)

    # Print summary
    print(f"\n{'=' * 70}", flush=True)
    print("ROUND 3 SUMMARY", flush=True)
    print(f"{'=' * 70}", flush=True)
    for pid, data in all_results.items():
        analysis = data.get("llm_analysis", "")
        status = "ANALYZED" if analysis and "[TIMEOUT]" not in str(analysis) else "SKIPPED/TIMEOUT"
        print(f"  {pid}: {data['total_matches']} matches -> {status}", flush=True)
    print(f"\nOutput: {raw_output}", flush=True)


if __name__ == "__main__":
    main()
