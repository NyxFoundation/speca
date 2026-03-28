#!/usr/bin/env python3
"""
Filter C4/Sherlock/CodeHawks CSVs for token sale / launchpad / IDO / auction
contests similar to Legion Protocol.

Outputs: outputs/legion_similar_issues.csv (High/Medium only, primary issues)
"""

import csv
import sys
import re
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

csv.field_size_limit(10 * 1024 * 1024)  # 10MB

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "benchmarks" / "data" / "defi_audit_reports"
OUT = ROOT / "outputs" / "legion_similar_issues.csv"

# Keywords that indicate a similar protocol (token sale, launchpad, IDO, sealed bid, vesting)
CONTEST_KEYWORDS = re.compile(
    r"sale|launchpad|ido\b|token.?launch|presale|pre.?sale|fundrais|"
    r"sealed.?bid|auction|vesting|vest\b|cliff|tge\b|"
    r"raise|capital.?raise|crowdsale|crowd.?fund|"
    r"merkle|allowlist|whitelist|eligib|"
    r"soulbound|sbt\b|position.?manager|"
    r"refund|claim.?token|token.?alloc|"
    r"eip.?1167|minimal.?proxy|clone|"
    r"signature.?replay|sig.?reuse|nonce|"
    r"invest|investor",
    re.IGNORECASE,
)

# Issue-level keywords for vulnerability patterns relevant to Legion
ISSUE_KEYWORDS = re.compile(
    r"signature|replay|nonce|expir|deadline|"
    r"merkle|proof|allowlist|whitelist|"
    r"refund|claim|vest|tge|alloc|"
    r"reentrancy|reentran|"
    r"front.?run|sandwich|mev|"
    r"access.?control|permiss|modifier|"
    r"overflow|underflow|precision|round|"
    r"fee|drain|steal|loss|"
    r"proxy|clone|initiali[sz]|"
    r"pause|unpause|cancel|"
    r"transfer|position|soulbound|"
    r"sealed.?bid|auction|bid.?reveal|"
    r"erc20|safeTransfer|approve",
    re.IGNORECASE,
)


def process_c4(writer, stats):
    path = DATA_DIR / "code4rena_all_issues.csv"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return
    print(f"  Reading {path.name}...")
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sev = row.get("severity", "").strip()
            if sev not in ("High", "Medium"):
                continue
            # Primary issues only
            is_primary = row.get("is_primary", "").lower() in ("true", "1", "yes")
            quality = row.get("quality", "").lower()
            if not is_primary and quality != "satisfactory":
                continue
            contest = row.get("contest_name", "") + " " + row.get("contest_repo", "")
            title = row.get("title", "")
            desc = row.get("description", "")[:3000]
            text = contest + " " + title + " " + desc
            # Match on contest OR issue keywords
            if CONTEST_KEYWORDS.search(text) and ISSUE_KEYWORDS.search(title + " " + desc):
                writer.writerow({
                    "source": "code4rena",
                    "contest": row.get("contest_name", ""),
                    "severity": sev,
                    "title": title[:200],
                    "description": desc[:2000],
                    "url": row.get("source_url", ""),
                })
                stats["c4"] += 1


def process_sherlock(writer, stats):
    path = DATA_DIR / "sherlock_all_issues.csv"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return
    print(f"  Reading {path.name}...")
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sev = row.get("severity", "").strip()
            if sev not in ("High", "Medium"):
                continue
            contest = row.get("contest_title", "")
            title = row.get("title", "")
            desc = row.get("description", "")[:3000]
            text = contest + " " + title + " " + desc
            if CONTEST_KEYWORDS.search(text) and ISSUE_KEYWORDS.search(title + " " + desc):
                writer.writerow({
                    "source": "sherlock",
                    "contest": contest,
                    "severity": sev,
                    "title": title[:200],
                    "description": desc[:2000],
                    "url": row.get("source_url", ""),
                })
                stats["sherlock"] += 1


def process_codehawks(writer, stats):
    path = DATA_DIR / "codehawks_all_issues.csv"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return
    print(f"  Reading {path.name}...")
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sev = row.get("severity", "").strip()
            if sev not in ("High", "Medium"):
                continue
            contest = row.get("contest_name", "")
            title = row.get("title", "")
            desc = row.get("description", "")[:3000]
            text = contest + " " + title + " " + desc
            if CONTEST_KEYWORDS.search(text) and ISSUE_KEYWORDS.search(title + " " + desc):
                writer.writerow({
                    "source": "codehawks",
                    "contest": contest,
                    "severity": sev,
                    "title": title[:200],
                    "description": desc[:2000],
                    "url": row.get("source_url", ""),
                })
                stats["codehawks"] += 1


def main():
    print("=== Legion類似コンテスト フィルタリング ===")
    stats = {"c4": 0, "sherlock": 0, "codehawks": 0}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["source", "contest", "severity", "title", "description", "url"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        process_c4(writer, stats)
        process_sherlock(writer, stats)
        process_codehawks(writer, stats)

    total = sum(stats.values())
    print(f"\n=== 完了 ===")
    print(f"  Code4rena: {stats['c4']}")
    print(f"  Sherlock:  {stats['sherlock']}")
    print(f"  CodeHawks: {stats['codehawks']}")
    print(f"  合計: {total} issues → {OUT}")


if __name__ == "__main__":
    main()
