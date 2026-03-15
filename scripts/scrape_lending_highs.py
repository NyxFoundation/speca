"""Scrape HIGH-severity findings from DeFi lending protocol Sherlock contests.

Filters FINISHED contests for lending protocols, fetches HIGH+Reward issues
from GitHub judging repos, and exports to CSV for pattern matching.

Usage:
    python3 scripts/scrape_lending_highs.py
    python3 scripts/scrape_lending_highs.py --all-defi   # include non-lending DeFi too
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

API_BASE = "https://audits.sherlock.xyz/api"
OUTPUT_DIR = Path("data/sherlock")
CSV_OUT = Path("data/sherlock/lending_highs.csv")

# DeFi lending protocol contest IDs (manually curated from contest list)
LENDING_CONTEST_IDS = [
    1209,  # Aave V4
    747,   # Aave v3.3
    59,    # Notional V3
    2,     # Notional
    1001,  # Notional Exponent
    1028,  # Centrifuge Protocol V3.1
    826,   # Extrafi XLend
    466,   # ZeroLend One
    1,     # Sentiment
    41,    # Blueberry
    137,   # Arcadia
    22,    # Isomorph
    32,    # Ajna
    75,    # Ajna Update
    114,   # Ajna #2
    247,   # Exactly Protocol
    741,   # Beraborrow
    1029,  # Malda
    1134,  # Rezerve Money
    124,   # M^0
    11,    # Union Finance
    554,   # Numa
    170,   # Tapioca
    1054,  # Ammplify
    858,   # Burve
    280,   # Zivoe
    180,   # Smilee Finance
    176,   # Rio Network
    101,   # Tokemak
    33,    # UXD Protocol
    13,    # Derby
    8,     # Astaria
    4,     # Knox Finance
    12,    # Illuminate
    16,    # Rage Trade
    70,    # JOJO Exchange
    749,   # Peapods
    964,   # Mellow Flexible Vaults
    832,   # Usual Labs
    575,   # Usual V1
    225,   # PoolTogether
    128,   # Olympus RBS 2.0
    40,    # Carapace
    57,    # Y2K
    29,    # Lyra
    81,    # Index
]

# Broader DeFi (DEX, perps, bridges) for --all-defi
EXTRA_DEFI_IDS = [
    6, 74,    # GMX
    79, 106, 123, 254, 518,  # Perennial
    219,      # Perpetual
    85,       # Symmetrical
    103,      # KyberSwap
    442,      # Velocimeter
    990,      # Cap
    1066,     # Dango DEX
    1102,     # Yield Basis
    1065,     # Neutrl Protocol
    485,      # Avantis
    288,      # dHEDGE
    86, 195,  # Arrakis
    468,      # Flayer
]


def gh_api(endpoint: str, paginate: bool = False) -> list | dict:
    cmd = ["gh", "api", endpoint]
    if paginate:
        cmd.append("--paginate")
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    if result.returncode != 0:
        return [] if paginate else {}
    text = result.stdout.decode("utf-8", errors="replace").strip() if result.stdout else ""
    if not text:
        return [] if paginate else {}
    if paginate:
        merged = []
        for chunk in text.split("\n"):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                parsed = json.loads(chunk)
                if isinstance(parsed, list):
                    merged.extend(parsed)
                else:
                    merged.append(parsed)
            except json.JSONDecodeError:
                pass
        return merged
    return json.loads(text)


def fetch_contest_detail(contest_id: int) -> dict:
    r = httpx.get(f"{API_BASE}/contests/{contest_id}", timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_high_issues(judging_repo: str) -> list[dict]:
    """Fetch HIGH-severity issues with Reward or Has Duplicates label."""
    print(f"  Fetching issues from {judging_repo}...")
    raw = gh_api(
        f"repos/{judging_repo}/issues?state=all&per_page=100&labels=High",
        paginate=True,
    )
    issues = []
    for item in raw:
        if item.get("pull_request"):
            continue
        labels = [l["name"] for l in item.get("labels", [])]
        # Only include rewarded findings (not spam)
        if "Reward" not in labels and "Has Duplicates" not in labels:
            continue
        title = item.get("title", "")
        author = title.split(" - ", 1)[0] if " - " in title else ""
        vuln_title = title.split(" - ", 1)[1] if " - " in title else title
        issues.append({
            "number": item["number"],
            "title": vuln_title,
            "author": author,
            "labels": labels,
            "body": item.get("body", ""),
        })
    print(f"  Found {len(issues)} HIGH+Reward issues")
    return issues


def extract_vulnerability_pattern(body: str) -> str:
    """Extract a short vulnerability category from the issue body."""
    body_lower = body.lower()
    patterns = [
        ("liquidat", "Liquidation"),
        ("oracle", "Oracle"),
        ("price manipul", "Price Manipulation"),
        ("flash loan", "Flash Loan"),
        ("reentrancy", "Reentrancy"),
        ("exchange rate", "Exchange Rate"),
        ("interest", "Interest Rate"),
        ("borrow", "Borrow Logic"),
        ("collateral", "Collateral"),
        ("deposit", "Deposit"),
        ("withdraw", "Withdraw"),
        ("overflow", "Overflow"),
        ("underflow", "Underflow"),
        ("rounding", "Rounding"),
        ("precision", "Precision"),
        ("front-run", "Front-running"),
        ("sandwich", "Sandwich"),
        ("access control", "Access Control"),
        ("reentr", "Reentrancy"),
        ("dos", "DoS"),
        ("drain", "Fund Drain"),
        ("steal", "Fund Theft"),
        ("loss of fund", "Fund Loss"),
        ("bad debt", "Bad Debt"),
        ("insolvency", "Insolvency"),
        ("vault", "Vault"),
        ("share", "Share Manipulation"),
        ("inflation", "Share Inflation"),
        ("first deposit", "First Depositor"),
    ]
    found = []
    for keyword, category in patterns:
        if keyword in body_lower:
            found.append(category)
    return ", ".join(found[:3]) if found else "Other"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-defi", action="store_true", help="Include broader DeFi contests")
    parser.add_argument("--limit", type=int, default=0, help="Max contests to scrape (0=all)")
    args = parser.parse_args()

    contest_ids = list(LENDING_CONTEST_IDS)
    if args.all_defi:
        contest_ids.extend(EXTRA_DEFI_IDS)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []
    scraped = 0

    for cid in contest_ids:
        if args.limit and scraped >= args.limit:
            break

        # Check cache
        cache_path = OUTPUT_DIR / f"contest_{cid}_highs.json"
        if cache_path.exists():
            print(f"[{cid}] cached, loading...")
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            for issue in cached.get("issues", []):
                all_rows.append({
                    "contest_id": cid,
                    "contest_title": cached["contest_title"],
                    "issue_number": issue["number"],
                    "title": issue["title"],
                    "author": issue["author"],
                    "labels": "; ".join(issue["labels"]),
                    "pattern": extract_vulnerability_pattern(issue["body"]),
                    "body_preview": issue["body"][:500].replace("\n", " "),
                })
            scraped += 1
            continue

        print(f"[{cid}] Fetching contest detail...")
        try:
            detail = fetch_contest_detail(cid)
        except Exception as e:
            print(f"  Error: {e}")
            continue

        contest_title = detail.get("title", "Unknown")
        judging_repo = detail.get("judging_repo_name")
        if not judging_repo:
            print(f"  No judging repo for {contest_title}, skipping")
            continue

        issues = fetch_high_issues(judging_repo)

        # Cache
        cache_data = {
            "contest_id": cid,
            "contest_title": contest_title,
            "issues": issues,
        }
        cache_path.write_text(
            json.dumps(cache_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        for issue in issues:
            all_rows.append({
                "contest_id": cid,
                "contest_title": contest_title,
                "issue_number": issue["number"],
                "title": issue["title"],
                "author": issue["author"],
                "labels": "; ".join(issue["labels"]),
                "pattern": extract_vulnerability_pattern(issue["body"]),
                "body_preview": issue["body"][:500].replace("\n", " "),
            })

        scraped += 1
        time.sleep(1)

    # Write CSV
    if all_rows:
        with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "contest_id", "contest_title", "issue_number", "title",
                "author", "labels", "pattern", "body_preview",
            ])
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\nWrote {len(all_rows)} HIGH findings to {CSV_OUT}")
    else:
        print("\nNo findings collected")

    # Print summary
    from collections import Counter
    pattern_counts = Counter(row["pattern"] for row in all_rows)
    print("\n=== Vulnerability Pattern Distribution ===")
    for pattern, count in pattern_counts.most_common(20):
        print(f"  {count:>3}  {pattern}")


if __name__ == "__main__":
    main()
