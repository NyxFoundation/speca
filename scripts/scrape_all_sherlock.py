"""Scrape ALL FINISHED Sherlock contests for HIGH-severity findings.

Fetches contest details from Sherlock API, then HIGH+Reward issues from
GitHub judging repos. Caches per-contest and exports comprehensive CSV.

Usage:
    python3 scripts/scrape_all_sherlock.py
    python3 scripts/scrape_all_sherlock.py --limit 50
    python3 scripts/scrape_all_sherlock.py --csv-only   # just rebuild CSV from cache
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

# Fix Windows encoding
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

API_BASE = "https://audits.sherlock.xyz/api"
OUTPUT_DIR = Path("data/sherlock")
CSV_OUT = Path("data/sherlock/all_sherlock_highs.csv")


def fetch_all_finished_contests() -> list[dict]:
    """Fetch all FINISHED contest IDs from Sherlock API."""
    contests = []
    page = 1
    while True:
        r = httpx.get(f"{API_BASE}/contests", params={"page": page}, timeout=30)
        r.raise_for_status()
        data = r.json()
        for item in data.get("items", []):
            if item.get("status") == "FINISHED":
                contests.append({"id": item["id"], "title": item.get("title", "")})
        if not data.get("has_next"):
            break
        page += 1
    return contests


def fetch_contest_detail(contest_id: int) -> dict:
    r = httpx.get(f"{API_BASE}/contests/{contest_id}", timeout=30)
    r.raise_for_status()
    return r.json()


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


def extract_patterns(body: str) -> str:
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
        ("erc4626", "ERC4626"),
        ("erc20", "ERC20"),
        ("permit", "Permit"),
        ("slippage", "Slippage"),
        ("mev", "MEV"),
        ("cross-chain", "Cross-chain"),
        ("bridge", "Bridge"),
        ("governance", "Governance"),
        ("timelock", "Timelock"),
        ("delegation", "Delegation"),
        ("staking", "Staking"),
        ("reward", "Reward"),
        ("fee", "Fee"),
    ]
    found = []
    for keyword, category in patterns:
        if keyword in body_lower:
            found.append(category)
    return ", ".join(found[:4]) if found else "Other"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max new contests to scrape (0=all)")
    parser.add_argument("--csv-only", action="store_true", help="Just rebuild CSV from cache")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.csv_only:
        print("Fetching FINISHED contest list...")
        contests = fetch_all_finished_contests()
        print(f"Total FINISHED contests: {len(contests)}")

        scraped = 0
        for contest in contests:
            cid = contest["id"]
            cache_path = OUTPUT_DIR / f"contest_{cid}_highs.json"
            if cache_path.exists():
                continue

            if args.limit and scraped >= args.limit:
                print(f"Reached limit of {args.limit}")
                break

            print(f"\n[{cid}] {contest['title'][:40]}...", flush=True)
            try:
                detail = fetch_contest_detail(cid)
            except Exception as e:
                print(f"  Error fetching detail: {e}")
                continue

            judging_repo = detail.get("judging_repo_name")
            if not judging_repo:
                # Save empty cache to skip next time
                cache_path.write_text(json.dumps({
                    "contest_id": cid,
                    "contest_title": contest["title"],
                    "issues": [],
                    "no_judging_repo": True,
                }, indent=2))
                print(f"  No judging repo, skipping")
                scraped += 1
                continue

            try:
                issues = fetch_high_issues(judging_repo)
            except Exception as e:
                print(f"  Error fetching issues: {e}")
                continue

            cache_data = {
                "contest_id": cid,
                "contest_title": contest["title"],
                "judging_repo": judging_repo,
                "issues": issues,
            }
            cache_path.write_text(
                json.dumps(cache_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            scraped += 1
            time.sleep(1)

        print(f"\nScraped {scraped} new contests")

    # Build comprehensive CSV from ALL cached files
    print("\nBuilding CSV from all cached data...")
    all_rows = []
    for f in sorted(OUTPUT_DIR.iterdir()):
        if not f.name.endswith("_highs.json"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for issue in data.get("issues", []):
            body = issue.get("body", "") or ""
            all_rows.append({
                "contest_id": data.get("contest_id", ""),
                "contest_title": data.get("contest_title", ""),
                "issue_number": issue["number"],
                "title": issue["title"],
                "author": issue.get("author", ""),
                "labels": "; ".join(issue.get("labels", [])),
                "pattern": extract_patterns(body),
                "body_preview": body[:500].replace("\n", " "),
                "body_full": body[:5000].replace("\n", " "),
            })

    if all_rows:
        with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "contest_id", "contest_title", "issue_number", "title",
                "author", "labels", "pattern", "body_preview", "body_full",
            ])
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"Wrote {len(all_rows)} HIGH findings to {CSV_OUT}")
    else:
        print("No findings collected")

    from collections import Counter
    pattern_counts = Counter()
    for row in all_rows:
        for p in row["pattern"].split(", "):
            pattern_counts[p] += 1
    print(f"\n=== Pattern Distribution ({len(all_rows)} total HIGHs) ===")
    for pattern, count in pattern_counts.most_common(25):
        print(f"  {count:>4}  {pattern}")


if __name__ == "__main__":
    main()
