#!/usr/bin/env python3
"""Setup audit scope files for a GitHub organization's repositories.

Usage:
    uv run python3 scripts/setup_org_audit.py --org sf-kosen
    uv run python3 scripts/setup_org_audit.py --org sf-kosen --repos Nanase-Bot,API-Server
    uv run python3 scripts/setup_org_audit.py --org sf-kosen --output-base outputs_sf-kosen
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def get_org_repos(org: str, repos_filter: list[str] | None = None) -> list[dict]:
    result = subprocess.run(
        ["gh", "repo", "list", org, "--limit", "100",
         "--json", "name,url,description,defaultBranchRef,isArchived,pushedAt"],
        capture_output=True, encoding="utf-8", errors="replace", check=True,
    )
    repos = json.loads(result.stdout)
    repos = [r for r in repos if not r.get("isArchived", False)]
    if repos_filter:
        repos = [r for r in repos if r["name"] in repos_filter]
    return repos


def get_repo_commit(org: str, repo_name: str, branch: str) -> tuple[str, str]:
    if not branch:
        branch = "main"
    for ref in [branch, "main", "master"]:
        result = subprocess.run(
            ["gh", "api", f"repos/{org}/{repo_name}/commits/{ref}",
             "--jq", ".sha"],
            capture_output=True, encoding="utf-8", errors="replace",
        )
        if result.returncode == 0 and result.stdout.strip():
            full = result.stdout.strip()
            return full, full[:7]
    return "HEAD", "HEAD"


def get_readme_urls(org: str, repo_name: str) -> list[str]:
    result = subprocess.run(
        ["gh", "api", f"repos/{org}/{repo_name}/readme",
         "--jq", ".content"],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        return []
    import base64
    import re
    try:
        content = base64.b64decode(result.stdout.strip()).decode("utf-8", errors="replace")
        urls = re.findall(r'https?://[^\s\)\"\'>\]]+', content)
        return urls[:10]
    except Exception:
        return []


def setup_repo(org: str, repo: dict, output_dir: Path) -> dict:
    repo_name = repo["name"]
    branch_info = repo.get("defaultBranchRef") or {}
    branch = branch_info.get("name") or "main"
    full_commit, short_commit = get_repo_commit(org, repo_name, branch)

    output_dir.mkdir(parents=True, exist_ok=True)

    target_info = {
        "target_repo": f"{org}/{repo_name}",
        "target_ref_type": "latest_default_branch",
        "target_ref_label": branch,
        "target_commit": full_commit,
        "target_commit_short": short_commit,
    }
    (output_dir / "TARGET_INFO.json").write_text(
        json.dumps(target_info, indent=2, ensure_ascii=False) + "\n"
    )

    readme_urls = get_readme_urls(org, repo_name)
    spec_urls = [f"https://github.com/{org}/{repo_name}"]
    spec_urls.extend(readme_urls)

    scope = {
        "program_url": f"https://github.com/{org}/{repo_name}",
        "program_name": f"{org}/{repo_name} Security Audit",
        "in_scope_assets": [f"https://github.com/{org}/{repo_name}"],
        "in_scope_contracts": [],
        "out_of_scope": ["test/", "docs/", "*.md"],
        "severity_ratings": "CVSS 3.1",
        "reward_range": "N/A (internal audit)",
        "notes": f"Internal security audit for {org} organization. Target: {repo_name}.",
    }
    (output_dir / "BUG_BOUNTY_SCOPE.json").write_text(
        json.dumps(scope, indent=2, ensure_ascii=False) + "\n"
    )

    desc = repo.get("description") or ""
    desc = desc.encode("ascii", errors="ignore").decode("ascii").strip()
    kw_parts = [repo_name, org]
    if desc:
        kw_parts.append(desc)
    extracted = {
        "spec_urls": ",".join(spec_urls),
        "keywords": ",".join(kw_parts),
    }
    (output_dir / "EXTRACTED_INPUTS.json").write_text(
        json.dumps(extracted, indent=2, ensure_ascii=False) + "\n"
    )

    return {
        "repo": f"{org}/{repo_name}",
        "branch": branch,
        "commit": short_commit,
        "output_dir": str(output_dir),
        "spec_urls": extracted["spec_urls"],
        "keywords": extracted["keywords"],
    }


def main():
    parser = argparse.ArgumentParser(description="Setup audit scope for a GitHub org")
    parser.add_argument("--org", required=True, help="GitHub organization name")
    parser.add_argument("--repos", help="Comma-separated repo names (default: all non-archived)")
    parser.add_argument("--output-base", default=None, help="Base output directory (default: outputs_{org})")
    args = parser.parse_args()

    repos_filter = args.repos.split(",") if args.repos else None
    output_base = args.output_base or f"outputs_{args.org}"

    print(f"Fetching repos from {args.org}...")
    repos = get_org_repos(args.org, repos_filter)
    if not repos:
        print("No repositories found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(repos)} repositories:")
    manifest = []
    for repo in repos:
        repo_name = repo["name"]
        output_dir = Path(output_base) / repo_name
        print(f"  Setting up {repo_name}...")
        info = setup_repo(args.org, repo, output_dir)
        manifest.append(info)
        print(f"    -> {output_dir} (commit: {info['commit']})")

    manifest_path = Path(output_base) / "AUDIT_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"\nManifest written to {manifest_path}")
    print(f"Total: {len(manifest)} repos ready for audit")


if __name__ == "__main__":
    main()
