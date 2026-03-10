#!/usr/bin/env python3
"""Collect DeFi audit reports from Sherlock and Code4rena into CSV."""

import argparse
import csv
import json
import subprocess
import sys
import time
import re
from pathlib import Path
from typing import Optional

# Protocol type classification by keywords in repo name
PROTOCOL_KEYWORDS = {
    "lending": [
        "lend", "borrow", "aave", "compound", "silo", "morpho", "euler",
        "venus", "radiant", "exactly", "teller", "notional", "credit",
        "interest-rate", "collateral", "mach-finance", "plaza-finance",
    ],
    "dex": [
        "swap", "dex", "amm", "uniswap", "kyber", "balancer", "curve",
        "sushi", "pancake", "rubicon", "jala", "woofi",
    ],
    "perpetual": [
        "perp", "perpetual", "leverage", "margin", "gmx", "kwenta",
        "wagmi",
    ],
    "bridge": [
        "bridge", "cross-chain", "layerzero", "wormhole", "stargate",
    ],
    "yield": [
        "yield", "stake", "staking", "farm", "vault", "beefy",
        "saffron", "gamma", "pooltogether", "peapods", "yieldoor",
        "convex", "yearn",
    ],
    "oracle": [
        "oracle", "pyth", "chainlink", "band",
    ],
    "nft": [
        "nft", "erc721", "erc1155",
    ],
}


def classify_protocol(repo_name: str) -> str:
    """Classify protocol type from repo name."""
    name_lower = repo_name.lower()
    for ptype, keywords in PROTOCOL_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return ptype
    return "other"


def extract_contest_name(repo_name: str, source: str) -> str:
    """Extract clean contest name from repo name."""
    if source == "sherlock":
        # Remove date prefix and -judging suffix
        name = re.sub(r"^\d{4}-\d{2}-", "", repo_name)
        name = re.sub(r"-judging$", "", name)
    else:
        # Remove date prefix and -findings suffix
        name = re.sub(r"^\d{4}-\d{2}-", "", repo_name)
        name = re.sub(r"-findings$", "", name)
    return name


def classify_status(labels: list[str], source: str) -> str:
    """Determine issue status from labels."""
    labels_lower = [l.lower() for l in labels]
    if source == "sherlock":
        if "invalid" in labels_lower or "excluded" in labels_lower:
            return "invalid"
        if "duplicate" in labels_lower:
            return "duplicate"
        return "valid"
    else:  # code4rena
        if "invalid" in labels_lower or "unsatisfactory" in labels_lower:
            return "invalid"
        for l in labels_lower:
            if l.startswith("duplicate"):
                return "duplicate"
        return "valid"


def extract_severity(labels: list[str], source: str) -> Optional[str]:
    """Extract severity from labels."""
    for label in labels:
        if source == "sherlock":
            if label == "High":
                return "High"
            if label == "Medium":
                return "Medium"
        else:  # code4rena
            if label == "3 (High Risk)":
                return "High"
            if label == "2 (Med Risk)":
                return "Medium"
    return None


def gh_api(endpoint: str, paginate: bool = False) -> list | dict:
    """Call GitHub API via gh CLI."""
    cmd = ["gh", "api", endpoint]
    if paginate:
        cmd.append("--paginate")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  API error: {result.stderr.strip()}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # Paginated results may be concatenated arrays
        try:
            # Try joining arrays
            parts = result.stdout.strip().split("\n")
            combined = []
            for part in parts:
                if part.strip():
                    data = json.loads(part)
                    if isinstance(data, list):
                        combined.extend(data)
                    else:
                        combined.append(data)
            return combined
        except Exception:
            return []


def list_repos(org: str, suffix: str) -> list[str]:
    """List repos from org matching suffix."""
    print(f"Listing repos from {org}...")
    repos = gh_api(f"orgs/{org}/repos?per_page=100&type=public", paginate=True)
    filtered = [r["name"] for r in repos if isinstance(r, dict) and r.get("name", "").endswith(suffix)]
    print(f"  Found {len(filtered)} repos with suffix '{suffix}'")
    return sorted(filtered)


def fetch_issues(org: str, repo: str, label: str) -> list[dict]:
    """Fetch all issues with a specific label from a repo."""
    encoded_label = label.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    endpoint = f"repos/{org}/{repo}/issues?labels={encoded_label}&state=all&per_page=100"
    return gh_api(endpoint, paginate=True)


def collect_source(source: str, output_dir: Path, resume: bool = True) -> Path:
    """Collect issues from a single source."""
    if source == "sherlock":
        org = "sherlock-audit"
        suffix = "-judging"
        labels = ["High", "Medium"]
    else:
        org = "code-423n4"
        suffix = "-findings"
        labels = ["3 (High Risk)", "2 (Med Risk)"]

    csv_path = output_dir / f"{source}_high_medium.csv"
    metadata_path = output_dir / f"{source}_metadata.json"

    # Resume: load already processed repos
    processed_repos = set()
    if resume and metadata_path.exists():
        meta = json.loads(metadata_path.read_text())
        processed_repos = set(meta.get("processed_repos", []))
        print(f"Resuming: {len(processed_repos)} repos already processed")

    repos = list_repos(org, suffix)

    # Open CSV (append mode for resume)
    mode = "a" if resume and csv_path.exists() else "w"
    csvfile = open(csv_path, mode, newline="", encoding="utf-8")
    writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
    if mode == "w":
        writer.writerow(["id", "source", "contest_name", "protocol_type",
                         "severity", "status", "title", "description"])

    total_issues = 0
    api_calls = 0

    for i, repo in enumerate(repos):
        if repo in processed_repos:
            continue

        contest_name = extract_contest_name(repo, source)
        protocol_type = classify_protocol(repo)

        print(f"[{i+1}/{len(repos)}] {repo} ({protocol_type})", end="", flush=True)

        repo_issues = 0
        for label in labels:
            issues = fetch_issues(org, repo, label)
            api_calls += 1

            if not isinstance(issues, list):
                continue

            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                if "pull_request" in issue:
                    continue  # skip PRs

                issue_labels = [l["name"] for l in issue.get("labels", [])]
                severity = extract_severity(issue_labels, source)
                if not severity:
                    continue

                status = classify_status(issue_labels, source)
                issue_id = f"{source}_{contest_name}_{issue['number']}"
                title = issue.get("title", "")
                body = issue.get("body", "") or ""

                writer.writerow([
                    issue_id, source, contest_name, protocol_type,
                    severity, status, title, body,
                ])
                repo_issues += 1
                total_issues += 1

        print(f" → {repo_issues} issues")

        processed_repos.add(repo)

        # Save metadata every 10 repos
        if (i + 1) % 10 == 0:
            csvfile.flush()
            metadata_path.write_text(json.dumps({
                "source": source,
                "processed_repos": sorted(processed_repos),
                "total_issues": total_issues,
                "api_calls": api_calls,
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }, indent=2))

    csvfile.close()

    # Final metadata
    metadata_path.write_text(json.dumps({
        "source": source,
        "processed_repos": sorted(processed_repos),
        "total_repos": len(repos),
        "total_issues": total_issues,
        "api_calls": api_calls,
        "completed": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }, indent=2))

    print(f"\n{'='*60}")
    print(f"Source: {source}")
    print(f"Repos processed: {len(processed_repos)}/{len(repos)}")
    print(f"Issues collected: {total_issues}")
    print(f"API calls: {api_calls}")
    print(f"Output: {csv_path}")
    print(f"{'='*60}\n")

    return csv_path


def merge_csvs(output_dir: Path) -> Path:
    """Merge source CSVs into a single combined CSV."""
    merged_path = output_dir / "defi_all_high_medium.csv"
    sources = ["sherlock", "code4rena"]
    total = 0

    with open(merged_path, "w", newline="", encoding="utf-8") as outf:
        writer = csv.writer(outf, quoting=csv.QUOTE_ALL)
        header_written = False

        for source in sources:
            csv_path = output_dir / f"{source}_high_medium.csv"
            if not csv_path.exists():
                print(f"Skipping {source}: {csv_path} not found")
                continue

            with open(csv_path, "r", encoding="utf-8") as inf:
                reader = csv.reader(inf)
                header = next(reader)
                if not header_written:
                    writer.writerow(header)
                    header_written = True

                for row in reader:
                    writer.writerow(row)
                    total += 1

    print(f"Merged CSV: {merged_path} ({total} records)")

    # Print severity/type distribution
    severity_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}

    with open(merged_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sev = row.get("severity", "unknown")
            ptype = row.get("protocol_type", "unknown")
            src = row.get("source", "unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            type_counts[ptype] = type_counts.get(ptype, 0) + 1
            source_counts[src] = source_counts.get(src, 0) + 1

    print("\nSeverity distribution:")
    for k, v in sorted(severity_counts.items()):
        print(f"  {k}: {v}")

    print("\nProtocol type distribution:")
    for k, v in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print("\nSource distribution:")
    for k, v in sorted(source_counts.items()):
        print(f"  {k}: {v}")

    return merged_path


def main():
    parser = argparse.ArgumentParser(description="Collect DeFi audit reports")
    parser.add_argument("--source", choices=["sherlock", "code4rena", "all"],
                        help="Source to collect from")
    parser.add_argument("--merge", action="store_true",
                        help="Merge existing source CSVs")
    parser.add_argument("--output", type=Path,
                        default=Path("benchmarks/data/defi_audit_reports"),
                        help="Output directory")
    parser.add_argument("--no-resume", action="store_true",
                        help="Don't resume from previous run")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    if args.merge:
        merge_csvs(args.output)
        return

    if not args.source:
        parser.error("--source or --merge required")

    sources = ["sherlock", "code4rena"] if args.source == "all" else [args.source]
    for source in sources:
        collect_source(source, args.output, resume=not args.no_resume)

    if len(sources) > 1:
        merge_csvs(args.output)


if __name__ == "__main__":
    main()
