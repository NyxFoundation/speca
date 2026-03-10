"""Sherlock Contest Results Scraper.

Fetches contest metadata from audits.sherlock.xyz API and
issue/comment data from GitHub judging repositories.

Usage:
    uv run python scripts/sherlock_scraper.py --contest 38
    uv run python scripts/sherlock_scraper.py --list
    uv run python scripts/sherlock_scraper.py --all --status FINISHED
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

API_BASE = "https://audits.sherlock.xyz/api"
SEVERITY_LABELS = {"High", "Medium", "Low", "Low/Info", "Informational"}
DEFAULT_OUTPUT = Path("data/sherlock")


def fetch_contest(contest_id: int) -> dict:
    """Fetch contest metadata from Sherlock API."""
    r = httpx.get(f"{API_BASE}/contests/{contest_id}", timeout=30)
    r.raise_for_status()
    data = r.json()
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "status": data.get("status"),
        "prize_pool": data.get("prize_pool"),
        "rewards": data.get("rewards"),
        "token": data.get("token"),
        "starts_at": data.get("starts_at"),
        "ends_at": data.get("ends_at"),
        "judging_repo": data.get("judging_repo_name"),
        "template_repo": data.get("template_repo_name"),
        "lead_judge": data.get("lead_judge_handle"),
        "lead_senior_auditor": data.get("lead_senior_auditor_handle"),
        "scope": data.get("scope", []),
        "context_questions": data.get("context_questions", []),
        "nsloc": data.get("nsloc"),
    }


def fetch_contests_list(status: str | None = None) -> list[dict]:
    """Fetch paginated contest list from Sherlock API."""
    contests = []
    page = 1
    while True:
        r = httpx.get(f"{API_BASE}/contests", params={"page": page}, timeout=30)
        r.raise_for_status()
        data = r.json()
        for item in data.get("items", []):
            if status and item.get("status") != status:
                continue
            contests.append({
                "id": item["id"],
                "title": item.get("title"),
                "status": item.get("status"),
                "judging_repo": item.get("judging_repo_name"),
                "prize_pool": item.get("prize_pool"),
            })
        if not data.get("has_next"):
            break
        page += 1
    return contests


def gh_api(endpoint: str, paginate: bool = False) -> list | dict:
    """Call GitHub API via gh CLI."""
    cmd = ["gh", "api", endpoint]
    if paginate:
        cmd.append("--paginate")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  gh api error: {result.stderr.strip()}", file=sys.stderr)
        return [] if paginate else {}
    text = result.stdout.strip()
    if not text:
        return [] if paginate else {}
    if paginate:
        # --paginate concatenates JSON arrays; merge them
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


def fetch_issues(judging_repo: str) -> list[dict]:
    """Fetch all issues from a GitHub judging repo."""
    print(f"  Fetching issues from {judging_repo}...")
    raw = gh_api(f"repos/{judging_repo}/issues?state=all&per_page=100", paginate=True)
    issues = []
    for item in raw:
        if item.get("pull_request"):
            continue
        labels = [l["name"] for l in item.get("labels", [])]
        severity = None
        for label in labels:
            if label in SEVERITY_LABELS:
                severity = label
                break
        # Parse author from title pattern "username - title"
        title = item.get("title", "")
        author = title.split(" - ", 1)[0] if " - " in title else item.get("user", {}).get("login", "")
        issues.append({
            "number": item["number"],
            "title": title,
            "author": author,
            "severity": severity,
            "labels": labels,
            "state": item.get("state"),
            "body": item.get("body", ""),
            "created_at": item.get("created_at"),
            "comment_count": item.get("comments", 0),
        })
    print(f"  Found {len(issues)} issues")
    return issues


def fetch_comments(judging_repo: str, issue_number: int) -> list[dict]:
    """Fetch comments for a single issue."""
    raw = gh_api(f"repos/{judging_repo}/issues/{issue_number}/comments")
    if not isinstance(raw, list):
        raw = [raw] if raw else []
    return [
        {
            "author": c.get("user", {}).get("login", ""),
            "body": c.get("body", ""),
            "created_at": c.get("created_at"),
        }
        for c in raw
    ]


def scrape_contest(contest_id: int, output_dir: Path) -> dict:
    """Scrape a single contest: metadata + issues + comments."""
    print(f"Scraping contest {contest_id}...")

    contest = fetch_contest(contest_id)
    judging_repo = contest.get("judging_repo")
    if not judging_repo:
        print(f"  No judging repo found for contest {contest_id}", file=sys.stderr)
        return {"contest": contest, "issues": [], "summary": {}}

    issues = fetch_issues(judging_repo)

    # Fetch comments for issues that have them
    issues_with_comments = [i for i in issues if i["comment_count"] > 0]
    print(f"  Fetching comments for {len(issues_with_comments)} issues...")
    for i, issue in enumerate(issues_with_comments):
        issue["comments"] = fetch_comments(judging_repo, issue["number"])
        if (i + 1) % 50 == 0:
            print(f"    {i + 1}/{len(issues_with_comments)} done")
            time.sleep(1)  # gentle rate limiting
    # Issues without comments get empty list
    for issue in issues:
        if "comments" not in issue:
            issue["comments"] = []

    # Build summary
    summary = {
        "total_issues": len(issues),
        "high": sum(1 for i in issues if i["severity"] == "High"),
        "medium": sum(1 for i in issues if i["severity"] == "Medium"),
        "low": sum(1 for i in issues if i["severity"] in ("Low", "Low/Info", "Informational")),
        "non_reward": sum(1 for i in issues if "Non-Reward" in i["labels"]),
        "reward": sum(1 for i in issues if "Reward" in i["labels"]),
        "escalated": sum(1 for i in issues if "Escalated" in i["labels"]),
        "has_duplicates": sum(1 for i in issues if "Has Duplicates" in i["labels"]),
        "duplicate": sum(1 for i in issues if "Duplicate" in i["labels"]),
        "sponsor_confirmed": sum(1 for i in issues if "Sponsor Confirmed" in i["labels"]),
        "sponsor_disputed": sum(1 for i in issues if "Sponsor Disputed" in i["labels"]),
        "will_fix": sum(1 for i in issues if "Will Fix" in i["labels"]),
        "wont_fix": sum(1 for i in issues if "Won't Fix" in i["labels"]),
    }

    result = {"contest": contest, "issues": issues, "summary": summary}

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"contest_{contest_id}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"  Saved to {out_path}")
    print(f"  Summary: {summary['high']}H / {summary['medium']}M / {summary['low']}L / {summary['non_reward']} non-reward / {summary['escalated']} escalated")

    return result


def main():
    parser = argparse.ArgumentParser(description="Sherlock Contest Results Scraper")
    parser.add_argument("--contest", type=int, help="Contest ID to scrape")
    parser.add_argument("--list", action="store_true", help="List all contests")
    parser.add_argument("--all", action="store_true", help="Scrape all contests")
    parser.add_argument("--status", default=None, help="Filter by status (e.g. FINISHED)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory")
    args = parser.parse_args()

    if args.list:
        contests = fetch_contests_list(args.status)
        for c in contests:
            repo = c.get("judging_repo") or "N/A"
            print(f"  [{c['id']:>4}] {c['status']:<20} {c['title']:<40} {repo}")
        print(f"\nTotal: {len(contests)}")
        return

    if args.contest:
        scrape_contest(args.contest, args.output)
        return

    if args.all:
        contests = fetch_contests_list(args.status)
        print(f"Scraping {len(contests)} contests...")
        for c in contests:
            if not c.get("judging_repo"):
                print(f"  [{c['id']}] {c['title']}: no judging repo, skipping")
                continue
            out_path = args.output / f"contest_{c['id']}.json"
            if out_path.exists():
                print(f"  [{c['id']}] {c['title']}: already scraped, skipping")
                continue
            scrape_contest(c["id"], args.output)
            time.sleep(2)  # be nice to APIs
        return

    parser.print_help()


if __name__ == "__main__":
    main()
