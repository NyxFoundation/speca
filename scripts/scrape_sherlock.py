#!/usr/bin/env python3
"""
Scrape all Sherlock contest reports into a CSV.

Strategy:
1. Paginate through https://mainnet-contest.sherlock.xyz/contests to get all finished contests.
2. For each finished contest, fetch the detail endpoint which includes a `report` field
   containing structured markdown with all judged issues (H-*, M-*).
3. Parse the markdown report to extract individual issues with severity, title, description,
   source URL, and found-by information.
4. For contests without a `report` field, fall back to GitHub judging repo issues via `gh` CLI.
5. Output everything to a single CSV.

Usage:
    uv run python3 scripts/scrape_sherlock.py [--output PATH] [--severity high,medium] [--max-contests N]
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# Use curl via subprocess since urllib may get 403 from Cloudflare
def curl_json(url: str, retries: int = 3) -> dict | list | None:
    for attempt in range(retries):
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "30", url],
                capture_output=True, text=True, timeout=35
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            print(f"  [warn] attempt {attempt+1} failed for {url}: {e}", file=sys.stderr)
            time.sleep(2 ** attempt)
    return None


def fetch_all_finished_contests() -> list[dict]:
    """Paginate through Sherlock API to get all finished contests."""
    contests = []
    page = 1
    while True:
        print(f"  Fetching contest list page {page}...", file=sys.stderr)
        data = curl_json(f"https://mainnet-contest.sherlock.xyz/contests?page={page}")
        if not data or not data.get("items"):
            break
        for c in data["items"]:
            if c.get("status") == "FINISHED":
                contests.append({
                    "id": c["id"],
                    "title": c["title"],
                    "prize_pool": c.get("prize_pool", 0),
                    "rewards": c.get("rewards", 0),
                    "starts_at": c.get("starts_at"),
                    "ends_at": c.get("ends_at"),
                })
        next_page = data.get("next_page")
        if not next_page:
            break
        page = next_page
        time.sleep(0.3)  # be polite
    return sorted(contests, key=lambda c: c["id"])


def parse_report_markdown(report: str, contest_id: int, contest_title: str) -> list[dict]:
    """Parse Sherlock's structured report markdown into individual issues."""
    issues = []
    if not report:
        return issues

    # Split by issue headers: # Issue H-1: ... or # Issue M-1: ...
    # Pattern: # Issue (H|M)-\d+: <title>
    issue_pattern = re.compile(
        r'^# Issue ([HM])-(\d+):\s*(.+?)$',
        re.MULTILINE
    )

    matches = list(issue_pattern.finditer(report))
    for i, match in enumerate(matches):
        severity_letter = match.group(1)
        issue_num = match.group(2)
        title = match.group(3).strip()
        severity = "High" if severity_letter == "H" else "Medium"

        # Extract body: from end of this match to start of next match (or end of report)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(report)
        body = report[start:end].strip()

        # Extract source URL
        source_match = re.search(r'Source:\s*(https://\S+)', body)
        source_url = source_match.group(1) if source_match else ""

        # Extract "Found by" line
        found_by_match = re.search(r'## Found by\s*\n(.+?)(?:\n\n|\n##)', body, re.DOTALL)
        found_by = ""
        if found_by_match:
            found_by = found_by_match.group(1).strip()
            # Clean up: comma-separated list of auditors
            found_by = ", ".join(
                line.strip().lstrip("- ")
                for line in found_by.split("\n")
                if line.strip()
            )

        # Extract judge comments (## Sherlock or ## Discussion sections)
        judge_sections = []
        for section_match in re.finditer(
            r'##\s*(Sherlock|Discussion)\s*\n(.*?)(?=\n## |\Z)',
            body, re.DOTALL
        ):
            judge_sections.append(section_match.group(2).strip())
        judge_comment = "\n---\n".join(judge_sections) if judge_sections else ""

        # Clean description: remove Source and Found by sections for the main description
        desc = body
        # Remove the Source line
        desc = re.sub(r'Source:\s*https://\S+\s*', '', desc)
        # Remove Found by section
        desc = re.sub(r'## Found by\s*\n.+?(?=\n## |\Z)', '', desc, flags=re.DOTALL)

        issues.append({
            "contest_id": contest_id,
            "contest_title": contest_title,
            "issue_id": f"{severity_letter}-{issue_num}",
            "severity": severity,
            "title": title,
            "description": desc.strip(),
            "source_url": source_url,
            "found_by": found_by,
            "judge_comment": judge_comment,
        })

    return issues


def fetch_github_issues(judging_repo: str, contest_id: int, contest_title: str) -> list[dict]:
    """Fallback: fetch issues from GitHub judging repo via gh CLI."""
    issues = []
    if not judging_repo:
        return issues

    print(f"  Falling back to GitHub: {judging_repo}", file=sys.stderr)
    try:
        # Get all issues with High/Medium labels
        result = subprocess.run(
            ["gh", "issue", "list", "-R", judging_repo,
             "--state", "all", "--limit", "500",
             "--json", "number,title,body,labels"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"  [warn] gh failed for {judging_repo}: {result.stderr[:200]}", file=sys.stderr)
            return issues

        gh_issues = json.loads(result.stdout)
        for gi in gh_issues:
            labels = [l.get("name", "").lower() for l in gi.get("labels", [])]
            if "high" in labels:
                severity = "High"
            elif "medium" in labels or "med" in labels:
                severity = "Medium"
            else:
                continue  # skip non-H/M

            # Detect duplicates (usually labeled "duplicate" or "non-reward")
            is_dup = any(l in ("duplicate", "non-reward", "escalation resolved: won't fix")
                         for l in labels)

            issues.append({
                "contest_id": contest_id,
                "contest_title": contest_title,
                "issue_id": f"#{gi['number']}",
                "severity": severity,
                "title": gi.get("title", ""),
                "description": (gi.get("body", "") or "")[:10000],
                "source_url": f"https://github.com/{judging_repo}/issues/{gi['number']}",
                "found_by": "",
                "judge_comment": "duplicate" if is_dup else "",
            })
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"  [warn] GitHub fallback failed: {e}", file=sys.stderr)

    return issues


def main():
    parser = argparse.ArgumentParser(description="Scrape Sherlock contest reports to CSV")
    parser.add_argument("--output", default="benchmarks/data/defi_audit_reports/sherlock_all_issues.csv")
    parser.add_argument("--severity", default="high,medium",
                        help="Comma-separated severities to include (default: high,medium)")
    parser.add_argument("--max-contests", type=int, default=0,
                        help="Max contests to process (0=all)")
    parser.add_argument("--skip-github-fallback", action="store_true",
                        help="Skip GitHub fallback for contests without reports")
    args = parser.parse_args()

    allowed_severities = {s.strip().capitalize() for s in args.severity.split(",")}

    print("Step 1: Fetching all finished contests...", file=sys.stderr)
    contests = fetch_all_finished_contests()
    print(f"  Found {len(contests)} finished contests", file=sys.stderr)

    if args.max_contests > 0:
        contests = contests[:args.max_contests]

    all_issues = []
    github_fallback_contests = []

    print("\nStep 2: Parsing report fields from API...", file=sys.stderr)
    for idx, contest in enumerate(contests):
        cid = contest["id"]
        print(f"  [{idx+1}/{len(contests)}] Contest {cid}: {contest['title']}...",
              file=sys.stderr, end="", flush=True)

        detail = curl_json(f"https://mainnet-contest.sherlock.xyz/contests/{cid}")
        if not detail:
            print(" [FAIL - no response]", file=sys.stderr)
            continue

        report = detail.get("report", "") or ""
        judging_repo = detail.get("judging_repo_name", "")

        if report:
            issues = parse_report_markdown(report, cid, contest["title"])
            filtered = [i for i in issues if i["severity"] in allowed_severities]
            all_issues.extend(filtered)
            print(f" {len(filtered)} issues (from report)", file=sys.stderr)
        elif judging_repo and not args.skip_github_fallback:
            github_fallback_contests.append((contest, judging_repo))
            print(f" [no report, will try GitHub: {judging_repo}]", file=sys.stderr)
        else:
            print(" [no report, no repo]", file=sys.stderr)

        time.sleep(0.2)

    if github_fallback_contests:
        print(f"\nStep 3: GitHub fallback for {len(github_fallback_contests)} contests...",
              file=sys.stderr)
        for contest, judging_repo in github_fallback_contests:
            cid = contest["id"]
            print(f"  Contest {cid}: {contest['title']}...", file=sys.stderr, flush=True)
            issues = fetch_github_issues(judging_repo, cid, contest["title"])
            filtered = [i for i in issues if i["severity"] in allowed_severities]
            all_issues.extend(filtered)
            print(f"    {len(filtered)} issues from GitHub", file=sys.stderr)
            time.sleep(0.5)

    # Write CSV
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "contest_id", "contest_title", "issue_id", "severity",
        "title", "description", "source_url", "found_by", "judge_comment"
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(all_issues)

    # Summary
    high_count = sum(1 for i in all_issues if i["severity"] == "High")
    med_count = sum(1 for i in all_issues if i["severity"] == "Medium")
    unique_contests = len(set(i["contest_id"] for i in all_issues))
    print(f"\nDone! Wrote {len(all_issues)} issues to {output_path}", file=sys.stderr)
    print(f"  High: {high_count}, Medium: {med_count}", file=sys.stderr)
    print(f"  From {unique_contests} contests", file=sys.stderr)


if __name__ == "__main__":
    main()
