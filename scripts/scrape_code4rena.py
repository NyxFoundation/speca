#!/usr/bin/env python3
"""
Scrape all Code4rena (C4) contest findings into a CSV.

Strategy:
1. Read known repos from benchmarks/data/defi_audit_reports/code4rena_metadata.json
2. Also discover repos via GitHub search for recent ones not in metadata
3. For each repo, use `gh issue list` to fetch High and Medium severity issues
4. Parse labels to determine severity, duplicate status, and primary issue status
5. Output to CSV

Label conventions:
  - "3 (High Risk)" = High severity
  - "2 (Med Risk)" = Medium severity
  - "primary issue" = canonical finding (others are duplicates)
  - "duplicate-XXX" = duplicate of issue #XXX
  - "satisfactory" / "unsatisfactory" = judge quality assessment
  - "selected for report" / "confirmed for report" = included in final report

Usage:
    python3 scripts/scrape_code4rena.py [--output PATH] [--severity high,medium] [--max-repos N]
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path


def gh_json(args: list[str], timeout: int = 120) -> list | dict | None:
    """Run a gh command and parse JSON output."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        if result.stderr:
            print(f"  [warn] gh error: {result.stderr[:200]}", file=sys.stderr)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"  [warn] gh failed: {e}", file=sys.stderr)
    return None


def discover_repos() -> list[str]:
    """Get C4 findings repos from metadata + GitHub search."""
    repos = []

    # Load from metadata
    meta_path = Path("benchmarks/data/defi_audit_reports/code4rena_metadata.json")
    if meta_path.exists():
        with open(meta_path) as f:
            data = json.load(f)
        repos = list(data.get("processed_repos", []))
        print(f"  Loaded {len(repos)} repos from metadata", file=sys.stderr)

    # Search for newer repos not in metadata
    print("  Searching GitHub for additional repos...", file=sys.stderr)
    for year in ["2025", "2026"]:
        result = gh_json([
            "api", "search/repositories",
            "-q", f"q=org:code-423n4+{year}+findings+in:name",
            "--jq", ".items[].name"
        ])
        # gh api returns text, not json in this case
        if result is None:
            # Try alternative: list repos
            result2 = subprocess.run(
                ["gh", "repo", "list", "code-423n4",
                 "--limit", "200", "--json", "name",
                 "-q", f".[] | select(.name | contains(\"{year}\")) | select(.name | endswith(\"findings\")) | .name"],
                capture_output=True, text=True, timeout=60
            )
            if result2.returncode == 0:
                for line in result2.stdout.strip().split("\n"):
                    name = line.strip()
                    if name and name not in repos:
                        repos.append(name)
                        print(f"    + discovered: {name}", file=sys.stderr)

    # Filter out very old repos that don't use structured labels (pre-2022)
    # and test/non-contest repos
    skip_patterns = ["2021-", "dev-test", "test-repo"]
    repos = [r for r in repos
             if not any(p in r for p in skip_patterns)]
    print(f"  After filtering pre-2022/test repos: {len(repos)}", file=sys.stderr)

    return repos


def extract_contest_name(repo_name: str) -> str:
    """Extract human-readable contest name from repo name."""
    # e.g., "2024-01-salty-findings" -> "Salty (2024-01)"
    parts = repo_name.replace("-findings", "").split("-", 2)
    if len(parts) >= 3:
        year_month = f"{parts[0]}-{parts[1]}"
        name = parts[2].replace("-", " ").title()
        return f"{name} ({year_month})"
    return repo_name


def scrape_repo(repo_name: str, allowed_severities: set[str]) -> list[dict]:
    """Scrape High/Medium issues from a C4 findings repo."""
    full_repo = f"code-423n4/{repo_name}"
    contest_name = extract_contest_name(repo_name)
    issues = []

    severity_labels = {
        "3 (High Risk)": "High",
        "2 (Med Risk)": "Medium",
    }

    for gh_label, severity in severity_labels.items():
        if severity not in allowed_severities:
            continue

        # Fetch all issues with this severity label
        data = gh_json([
            "issue", "list", "-R", full_repo,
            "--state", "all",
            "--label", gh_label,
            "--limit", "500",
            "--json", "number,title,body,labels"
        ])

        if not data:
            continue

        for issue in data:
            labels = [l.get("name", "") for l in issue.get("labels", [])]

            # Determine if primary or duplicate
            is_primary = "primary issue" in labels or "selected for report" in labels
            is_duplicate = any("duplicate" in l for l in labels)
            is_invalid = "invalid" in labels

            if is_invalid:
                continue

            # Find duplicate root
            dup_of = ""
            for l in labels:
                if l.startswith("duplicate-"):
                    dup_of = l.replace("duplicate-", "#")
                    break

            # Quality
            quality = ""
            if "satisfactory" in labels:
                quality = "satisfactory"
            elif "unsatisfactory" in labels:
                quality = "unsatisfactory"

            body = (issue.get("body", "") or "")

            issues.append({
                "contest_repo": repo_name,
                "contest_name": contest_name,
                "issue_id": f"#{issue['number']}",
                "severity": severity,
                "title": issue.get("title", ""),
                "description": body[:15000],  # truncate very long bodies
                "source_url": f"https://github.com/{full_repo}/issues/{issue['number']}",
                "is_primary": is_primary,
                "is_duplicate": is_duplicate,
                "duplicate_of": dup_of,
                "quality": quality,
                "labels": ", ".join(labels),
            })

    return issues


def main():
    parser = argparse.ArgumentParser(description="Scrape Code4rena findings to CSV")
    parser.add_argument("--output", default="benchmarks/data/defi_audit_reports/code4rena_all_issues.csv")
    parser.add_argument("--severity", default="high,medium",
                        help="Comma-separated severities (default: high,medium)")
    parser.add_argument("--max-repos", type=int, default=0,
                        help="Max repos to process (0=all)")
    parser.add_argument("--primary-only", action="store_true",
                        help="Only include primary/selected-for-report issues (skip duplicates)")
    args = parser.parse_args()

    allowed_severities = {s.strip().capitalize() for s in args.severity.split(",")}

    print("Step 1: Discovering repos...", file=sys.stderr)
    repos = discover_repos()
    print(f"  Total repos: {len(repos)}", file=sys.stderr)

    if args.max_repos > 0:
        repos = repos[:args.max_repos]

    all_issues = []
    failed_repos = []

    print(f"\nStep 2: Scraping {len(repos)} repos...", file=sys.stderr)
    for idx, repo in enumerate(repos):
        print(f"  [{idx+1}/{len(repos)}] {repo}...",
              file=sys.stderr, end="", flush=True)

        issues = scrape_repo(repo, allowed_severities)

        if args.primary_only:
            issues = [i for i in issues if i["is_primary"]]

        if issues:
            all_issues.extend(issues)
            h = sum(1 for i in issues if i["severity"] == "High")
            m = sum(1 for i in issues if i["severity"] == "Medium")
            print(f" {len(issues)} issues (H:{h} M:{m})", file=sys.stderr)
        else:
            print(" [0 issues or failed]", file=sys.stderr)
            failed_repos.append(repo)

        # Rate limit: GitHub API allows 5000 requests/hour
        time.sleep(0.5)

    # Write CSV
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "contest_repo", "contest_name", "issue_id", "severity",
        "title", "description", "source_url",
        "is_primary", "is_duplicate", "duplicate_of", "quality", "labels"
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(all_issues)

    # Summary
    high_count = sum(1 for i in all_issues if i["severity"] == "High")
    med_count = sum(1 for i in all_issues if i["severity"] == "Medium")
    primary_count = sum(1 for i in all_issues if i["is_primary"])
    print(f"\nDone! Wrote {len(all_issues)} issues to {output_path}", file=sys.stderr)
    print(f"  High: {high_count}, Medium: {med_count}", file=sys.stderr)
    print(f"  Primary issues: {primary_count}", file=sys.stderr)
    print(f"  From {len(repos) - len(failed_repos)}/{len(repos)} repos", file=sys.stderr)
    if failed_repos:
        print(f"  Failed repos: {len(failed_repos)}", file=sys.stderr)


if __name__ == "__main__":
    main()
