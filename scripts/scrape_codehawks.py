#!/usr/bin/env python3
"""
Scrape CodeHawks contest findings into a CSV.

Strategy:
1. Fetch contest list from codehawks.cyfrin.io/contests (embedded SvelteKit JSON)
2. For each finalized contest, fetch the results page
3. Parse embedded JSON to extract findings with severity, title, description
4. Output to CSV

Usage:
    python3 scripts/scrape_codehawks.py [--output PATH] [--severity high,medium]
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path


def curl_text(url: str, retries: int = 3) -> str | None:
    for attempt in range(retries):
        try:
            result = subprocess.run(
                ["curl", "-s", "-L", "--max-time", "30", url],
                capture_output=True, text=True, timeout=35,
                encoding="utf-8", errors="replace"
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except subprocess.TimeoutExpired:
            time.sleep(2 ** attempt)
    return None


def extract_sveltekit_data(html: str) -> list:
    """Extract data from SvelteKit embedded JSON in script tags."""
    results = []
    # Pattern: data-sveltekit-fetched content
    matches = re.findall(r'data-sveltekit-fetched[^>]*>([^<]+)</script>', html)
    for m in matches:
        try:
            wrapper = json.loads(m)
            body = wrapper.get("body")
            if isinstance(body, str):
                data = json.loads(body)
            else:
                data = body
            results.append(data)
        except (json.JSONDecodeError, TypeError):
            pass
    return results


def fetch_contests() -> list[dict]:
    """Fetch all finalized CodeHawks contests."""
    html = curl_text("https://codehawks.cyfrin.io/contests")
    if not html:
        print("Failed to fetch contests page", file=sys.stderr)
        return []

    contests = []
    for data in extract_sveltekit_data(html):
        if isinstance(data, list):
            for item in data:
                result = item.get("result", {}) if isinstance(item, dict) else {}
                entries = result.get("data", [])
                if isinstance(entries, list):
                    for c in entries:
                        if isinstance(c, dict) and c.get("finalised"):
                            contests.append(c)
    return contests


def fetch_findings(slug: str) -> list[dict]:
    """Fetch findings for a specific contest from its results page."""
    findings = []

    # Try results page
    html = curl_text(f"https://codehawks.cyfrin.io/c/{slug}/results")
    if not html:
        return findings

    # Extract embedded data
    for data in extract_sveltekit_data(html):
        findings.extend(parse_findings_data(data))

    # If no findings from embedded data, try to parse the rendered content
    if not findings:
        findings = parse_findings_from_html(html, slug)

    return findings


def parse_findings_data(data, depth=0) -> list[dict]:
    """Recursively look for findings in nested JSON data."""
    findings = []
    if depth > 5:
        return findings

    if isinstance(data, list):
        for item in data:
            findings.extend(parse_findings_data(item, depth + 1))
    elif isinstance(data, dict):
        # Check if this looks like a finding
        if "severity" in data or "risk" in data:
            title = data.get("title", "") or data.get("name", "")
            desc = data.get("description", "") or data.get("body", "") or data.get("content", "")
            severity = data.get("severity", "") or data.get("risk", "")
            if title and severity:
                findings.append({
                    "title": title,
                    "description": str(desc)[:15000],
                    "severity": str(severity),
                    "finding_id": data.get("id", ""),
                })
        # Recurse into values
        for v in data.values():
            if isinstance(v, (list, dict)):
                findings.extend(parse_findings_data(v, depth + 1))

    return findings


def parse_findings_from_html(html: str, slug: str) -> list[dict]:
    """Fallback: parse findings from rendered HTML content."""
    findings = []

    # Look for finding patterns in the page text
    # CodeHawks typically shows "H-01", "M-01" etc.
    # Extract all JSON-like data from script tags
    script_contents = re.findall(r'<script[^>]*>([^<]{100,})</script>', html)
    for script in script_contents:
        # Look for arrays of findings
        try:
            # Try to find JSON arrays
            for match in re.finditer(r'\[(\{[^[\]]{50,}\}(?:,\{[^[\]]{50,}\})*)\]', script):
                try:
                    arr = json.loads(f"[{match.group(1)}]")
                    findings.extend(parse_findings_data(arr))
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    return findings


def normalize_severity(sev: str) -> str:
    """Normalize severity string."""
    s = sev.lower().strip()
    if "high" in s or s == "h":
        return "High"
    elif "medium" in s or "med" in s or s == "m":
        return "Medium"
    elif "low" in s or s == "l":
        return "Low"
    return sev.capitalize()


def main():
    parser = argparse.ArgumentParser(description="Scrape CodeHawks findings to CSV")
    parser.add_argument("--output", default="benchmarks/data/defi_audit_reports/codehawks_all_issues.csv")
    parser.add_argument("--severity", default="high,medium")
    parser.add_argument("--max-contests", type=int, default=0)
    args = parser.parse_args()

    allowed_severities = {s.strip().capitalize() for s in args.severity.split(",")}

    print("Step 1: Fetching contest list...", file=sys.stderr)
    contests = fetch_contests()
    print(f"  Found {len(contests)} finalized contests", file=sys.stderr)

    if args.max_contests > 0:
        contests = contests[:args.max_contests]

    all_issues = []

    print("\nStep 2: Fetching findings...", file=sys.stderr)
    for idx, contest in enumerate(contests):
        slug = contest.get("urlSlug", "")
        name = contest.get("name", "")
        company = contest.get("company", "")
        reward = contest.get("reward", 0)

        print(f"  [{idx+1}/{len(contests)}] {slug} ({name})...",
              file=sys.stderr, end="", flush=True)

        findings = fetch_findings(slug)

        filtered = []
        for f in findings:
            sev = normalize_severity(f["severity"])
            if sev in allowed_severities:
                filtered.append({
                    "contest_slug": slug,
                    "contest_name": f"{company} - {name}" if company else name,
                    "contest_reward": reward,
                    "finding_id": f.get("finding_id", ""),
                    "severity": sev,
                    "title": f["title"],
                    "description": f["description"],
                    "source_url": f"https://codehawks.cyfrin.io/c/{slug}/results",
                })

        all_issues.extend(filtered)
        print(f" {len(filtered)} issues", file=sys.stderr)
        time.sleep(0.5)

    # Write CSV
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "contest_slug", "contest_name", "contest_reward", "finding_id",
        "severity", "title", "description", "source_url"
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(all_issues)

    high_count = sum(1 for i in all_issues if i["severity"] == "High")
    med_count = sum(1 for i in all_issues if i["severity"] == "Medium")
    print(f"\nDone! Wrote {len(all_issues)} issues to {output_path}", file=sys.stderr)
    print(f"  High: {high_count}, Medium: {med_count}", file=sys.stderr)


if __name__ == "__main__":
    main()
