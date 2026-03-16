"""Scrape HIGH-severity findings from Code4rena DeFi lending contests.

Code4rena findings are public on GitHub: code-423n4/{contest}-findings/issues
Labels: 3 (High Risk), 2 (Med Risk)

Usage:
    python3 scripts/scrape_c4_highs.py
    python3 scripts/scrape_c4_highs.py --limit 20
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

OUTPUT_DIR = Path("data/c4")
CSV_OUT = Path("data/c4/defi_highs.csv")

# DeFi lending/protocol contest repos (manually curated - major ones)
C4_CONTESTS = [
    # Lending protocols
    "2023-05-ajna", "2023-01-ajna", "2024-09-ajna",
    "2023-02-blueberry", "2023-07-blueberry",
    "2022-02-aave-lens", "2023-09-centrifuge",
    "2023-01-timeswap", "2023-06-lybra",
    "2023-02-ethos", "2022-04-abranern",
    "2023-05-venus", "2024-02-spectra",
    "2022-01-trader-joe", "2023-07-moonwell",
    "2023-10-wildcat", "2024-04-dyad",
    "2023-12-ethereumcreditguild", "2024-06-size",
    "2023-01-canto-lending", "2022-12-tigris",
    "2023-05-maia", "2023-07-tapioca",
    "2023-10-ethena", "2024-01-salty",
    # DEX / Perps / DeFi
    "2023-08-dopex", "2023-01-ondo",
    "2023-04-rubicon", "2023-06-dodo",
    "2023-10-party", "2023-08-shell",
    "2024-02-ai-arena", "2023-03-asymmetry",
    "2023-05-juicebox", "2023-08-livepeer",
    "2024-01-curves", "2024-03-revert-lend",
    "2024-04-panoptic", "2024-05-loop",
    "2024-07-basin", "2023-11-shellprotocol",
    "2023-04-eigenlayer", "2024-02-uniswap",
    # Yield / Vault
    "2023-01-popcorn", "2023-02-ethos",
    "2023-06-llama", "2023-09-maia",
    "2024-03-dittoeth", "2024-05-bakerfi",
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


def fetch_c4_highs(contest: str) -> list[dict]:
    """Fetch HIGH (label '3') issues from a Code4rena findings repo."""
    repo = f"code-423n4/{contest}-findings"
    print(f"  Fetching from {repo}...")

    # Try label "3 (High Risk)" first, then "H" for newer format
    raw = gh_api(
        f"repos/{repo}/issues?state=all&per_page=100&labels=3%20(High%20Risk)",
        paginate=True,
    )
    if not raw:
        raw = gh_api(
            f"repos/{repo}/issues?state=all&per_page=100&labels=H",
            paginate=True,
        )
    if not raw:
        # Try just "3"
        raw = gh_api(
            f"repos/{repo}/issues?state=all&per_page=100&labels=3",
            paginate=True,
        )

    issues = []
    for item in raw:
        if item.get("pull_request"):
            continue
        labels = [l["name"] for l in item.get("labels", [])]
        title = item.get("title", "")
        body = item.get("body", "") or ""
        issues.append({
            "number": item["number"],
            "title": title,
            "labels": labels,
            "body": body[:2000],
        })

    print(f"  Found {len(issues)} HIGH issues")
    return issues


def extract_pattern(body: str) -> str:
    body_lower = body.lower()
    patterns = [
        ("liquidat", "Liquidation"),
        ("oracle", "Oracle"),
        ("flash loan", "Flash Loan"),
        ("exchange rate", "Exchange Rate"),
        ("interest", "Interest Rate"),
        ("borrow", "Borrow Logic"),
        ("collateral", "Collateral"),
        ("deposit", "Deposit"),
        ("withdraw", "Withdraw"),
        ("rounding", "Rounding"),
        ("precision", "Precision"),
        ("bad debt", "Bad Debt"),
        ("insolvency", "Insolvency"),
        ("vault", "Vault"),
        ("share", "Share Manipulation"),
        ("inflation", "Share Inflation"),
        ("first deposit", "First Depositor"),
        ("reentrancy", "Reentrancy"),
        ("front-run", "Front-running"),
        ("dos", "DoS"),
        ("drain", "Fund Drain"),
        ("steal", "Fund Theft"),
        ("loss of fund", "Fund Loss"),
    ]
    found = []
    for keyword, category in patterns:
        if keyword in body_lower:
            found.append(category)
    return ", ".join(found[:3]) if found else "Other"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []
    scraped = 0

    for contest in C4_CONTESTS:
        if args.limit and scraped >= args.limit:
            break

        cache_path = OUTPUT_DIR / f"{contest}_highs.json"
        if cache_path.exists():
            print(f"[{contest}] cached")
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            for issue in cached.get("issues", []):
                all_rows.append({
                    "platform": "code4rena",
                    "contest": contest,
                    "issue_number": issue["number"],
                    "title": issue["title"],
                    "labels": "; ".join(issue["labels"]),
                    "pattern": extract_pattern(issue["body"]),
                    "body_preview": issue["body"][:500].replace("\n", " "),
                })
            scraped += 1
            continue

        issues = fetch_c4_highs(contest)
        cache_data = {"contest": contest, "issues": issues}
        cache_path.write_text(
            json.dumps(cache_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        for issue in issues:
            all_rows.append({
                "platform": "code4rena",
                "contest": contest,
                "issue_number": issue["number"],
                "title": issue["title"],
                "labels": "; ".join(issue["labels"]),
                "pattern": extract_pattern(issue["body"]),
                "body_preview": issue["body"][:500].replace("\n", " "),
            })

        scraped += 1
        time.sleep(1)

    if all_rows:
        with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "platform", "contest", "issue_number", "title",
                "labels", "pattern", "body_preview",
            ])
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\nWrote {len(all_rows)} HIGH findings to {CSV_OUT}")

    from collections import Counter
    pattern_counts = Counter(row["pattern"] for row in all_rows)
    print("\n=== Pattern Distribution ===")
    for p, c in pattern_counts.most_common(15):
        print(f"  {c:>3}  {p}")


if __name__ == "__main__":
    main()
