#!/usr/bin/env python3
"""Use codex CLI to perform LLM matching between agent findings and CSV issues."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

TARGET_LABELS = {
    "NEEDS-MANUAL-AUDIT",
    "NEEDS-REVIEW",
    "exploitable",
    "vulnerability-confirmed",
    "true-positive",
    "potential-vulnerability",
    "needs-review",
    "requires_review",
    "low-risk-externally-reachable",
    "requires_manual_review",
    "potential_vulnerability_defense_in_depth",
}

CL_CLIENT_KEYWORDS = {
    "grandine": "grandinetech/grandine",
    "lighthouse": "sigp/lighthouse",
    "lodestar": "ChainSafe/lodestar",
    "nimbus": "status-im/nimbus-eth2",
    "prysm": "OffchainLabs/prysm",
    "teku": "Consensys/teku",
}

EL_CLIENT_KEYWORDS = {
    "reth": "reth",
    "geth": "geth",
    "go-eth": "geth",
    "besu": "besu",
    "erigon": "erigon",
    "nethermind": "nethermind",
}


def load_agent_findings(results_dir: Path) -> dict[str, list[dict]]:
    findings_by_repo: dict[str, list[dict]] = defaultdict(list)

    for dpath in sorted(results_dir.iterdir()):
        if not dpath.is_dir():
            continue

        manifest_path = dpath / "manifest.json"
        target_repo = ""
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                target_repo = manifest.get("target_info", {}).get("target_repo", "")
            except json.JSONDecodeError:
                target_repo = ""

        for fpath in sorted(dpath.glob("03_AUDITMAP_PARTIAL_*.json")):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            raw_items = data if isinstance(data, list) else data.get("audit_items") if isinstance(data, dict) else None
            if not isinstance(raw_items, list):
                continue
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                fc = item.get("final_classification", "")
                if fc not in TARGET_LABELS:
                    continue
                summary = {
                    "check_id": item.get("check_id", item.get("checklist_item_id", "")),
                    "title": item.get("title", item.get("finding_title", "")),
                    "classification": fc,
                    "bug_class": item.get("bug_class", ""),
                    "risk_category": item.get("risk_category", ""),
                    "severity": item.get("severity_hint", item.get("severity", "")),
                    "code_file": "",
                    "description": item.get(
                        "finding_description",
                        item.get("summary", item.get("reason", "")),
                    ),
                }
                code_scope = item.get("code_scope", {})
                if isinstance(code_scope, dict):
                    summary["code_file"] = code_scope.get("file", "")

                audit_trail = item.get("audit_trail", {})
                if isinstance(audit_trail, dict):
                    for phase_key in (
                        "phase1_abstract_interpretation",
                        "phase2_symbolic_execution",
                        "phase3_invariant_proving",
                    ):
                        phase = audit_trail.get(phase_key, {})
                        if isinstance(phase, dict) and phase.get("reason"):
                            summary["description"] += " | " + str(phase["reason"])

                findings_by_repo[target_repo].append(summary)

    return findings_by_repo


def load_csv_issues(csv_path: Path) -> list[dict]:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in rows:
        title = row.get("title", "").lower()
        desc = row.get("description", "").lower()
        combined = title + " " + desc

        cl_clients = set()
        for keyword, repo in CL_CLIENT_KEYWORDS.items():
            if keyword in combined:
                cl_clients.add(repo)
        row["_cl_clients"] = cl_clients

        el_clients = set()
        for keyword, repo in EL_CLIENT_KEYWORDS.items():
            if keyword in combined:
                el_clients.add(repo)
        row["_el_clients"] = el_clients

    return rows


def run_codex(prompt: str, model: str, max_tokens: int) -> str:
    command = [
        "codex",
        "exec",
        "--sandbox",
        "read-only",
        "--model",
        model,
        prompt,
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "codex exec failed")
    return result.stdout.strip()


def match_issue_with_codex(issue: dict, findings_for_clients: dict[str, list[dict]], model: str, max_tokens: int) -> dict:
    issue_text = f"Issue #{issue['number']} [{issue['submitted_severity']}]: {issue['title']}\n"
    issue_text += f"Description (first 1000 chars): {issue.get('description', '')[:1000]}"

    findings_text = ""
    finding_count = 0
    for repo, findings in findings_for_clients.items():
        for f in findings:
            finding_count += 1
            findings_text += f"\n[{finding_count}] Check: {f['check_id']}\n"
            findings_text += f"  Title: {f['title'][:200]}\n"
            findings_text += f"  Classification: {f['classification']}\n"
            findings_text += f"  Bug class: {f['bug_class']}\n"
            findings_text += f"  Severity: {f['severity']}\n"
            findings_text += f"  File: {f['code_file']}\n"
            findings_text += f"  Description: {str(f['description'])[:300]}\n"

    if finding_count == 0:
        return {"matched": False, "reason": "No findings for relevant clients", "matched_finding_number": None}

    prompt = f"""You are analyzing whether an automated security audit agent detected the same vulnerability as a human-reported issue from a Sherlock audit contest.

HUMAN-REPORTED ISSUE:
{issue_text}

AGENT FINDINGS (from the same client codebase, labeled as requiring review/potentially vulnerable):
{findings_text}

TASK: Determine if any of the agent's findings covers the SAME or SUBSTANTIALLY SIMILAR vulnerability as the human-reported issue.
Consider:
- The finding doesn't need to be identical; it should cover the same bug class, same code area, or same security concern
- A finding about the same EIP/feature area with similar security implications counts as a match
- Generic findings about the same subsystem (e.g., "gossip validation" or "custody groups") that would lead an auditor to discover the specific bug also count
- Findings that flag the exact code file/function where the bug exists count as a match

Respond with JSON only:
{{"matched": true/false, "matched_finding_number": <number or null>, "confidence": "high"/"medium"/"low", "reason": "<brief explanation>"}}"""

    content = run_codex(prompt, model, max_tokens)
    # Extract JSON from response
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"matched": False, "reason": "Invalid JSON from codex", "matched_finding_number": None}


def main() -> None:
    parser = argparse.ArgumentParser(description="Codex LLM matching")
    parser.add_argument(
        "--results-dir",
        default=str(ROOT_DIR / "benchmarks" / "results" / "rq1" / "sherlock_ethereum_audit_contest"),
    )
    parser.add_argument(
        "--csv",
        default=str(
            ROOT_DIR
            / "benchmarks"
            / "data"
            / "rq1"
            / "sherlock_contest_1140_issues_1766639267091.csv"
        ),
    )
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument(
        "--severity-filter",
        type=str,
        default="",
        help="Comma-separated severities to include (e.g., High,Medium,Low)",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    csv_path = Path(args.csv)

    print("Loading data...")
    findings_by_repo = load_agent_findings(results_dir)
    issues = load_csv_issues(csv_path)

    print("Agent findings by repo:")
    for repo, findings in findings_by_repo.items():
        print(f"  {repo}: {len(findings)} findings")

    severity_filter = {
        item.strip() for item in args.severity_filter.split(",") if item.strip()
    }
    all_valid_issues = [i for i in issues if i.get("submitted_severity") != "Invalid"]
    if severity_filter:
        all_valid_issues = [
            i for i in all_valid_issues if i.get("submitted_severity") in severity_filter
        ]

    results = []

    for idx, issue in enumerate(all_valid_issues):
        print(
            f"\n[{idx+1}/{len(all_valid_issues)}] Issue #{issue['number']} [{issue['submitted_severity']}]: {issue['title'][:80]}"
        )

        relevant_findings: dict[str, list[dict]] = {}
        if issue["_cl_clients"]:
            for repo in issue["_cl_clients"]:
                if repo in findings_by_repo:
                    relevant_findings[repo] = findings_by_repo[repo]
        else:
            relevant_findings = findings_by_repo

        if issue["_el_clients"] and not issue["_cl_clients"]:
            result = {
                "issue_number": issue["number"],
                "issue_title": issue["title"],
                "issue_severity": issue["submitted_severity"],
                "cl_clients": list(issue["_cl_clients"]),
                "el_clients": list(issue["_el_clients"]),
                "matched": False,
                "reason": "EL-only issue (not in scope of CL audit)",
                "confidence": "high",
                "matched_finding_number": None,
            }
            results.append(result)
            print("  -> SKIP (EL-only)")
            continue

        if not relevant_findings or all(len(v) == 0 for v in relevant_findings.values()):
            result = {
                "issue_number": issue["number"],
                "issue_title": issue["title"],
                "issue_severity": issue["submitted_severity"],
                "cl_clients": list(issue["_cl_clients"]),
                "el_clients": list(issue["_el_clients"]),
                "matched": False,
                "reason": "No agent findings for relevant clients",
                "confidence": "high",
                "matched_finding_number": None,
            }
            results.append(result)
            print("  -> SKIP (no findings)")
            continue

        llm_result = match_issue_with_codex(issue, relevant_findings, args.model, args.max_tokens)

        result = {
            "issue_number": issue["number"],
            "issue_title": issue["title"],
            "issue_severity": issue["submitted_severity"],
            "cl_clients": list(issue["_cl_clients"]),
            "el_clients": list(issue["_el_clients"]),
            "matched": llm_result.get("matched", False),
            "reason": llm_result.get("reason", ""),
            "confidence": llm_result.get("confidence", "unknown"),
            "matched_finding_number": llm_result.get("matched_finding_number"),
        }
        results.append(result)

        status = "MATCHED" if result["matched"] else "NOT MATCHED"
        print(f"  -> {status} (confidence: {result['confidence']}) - {result['reason'][:100]}")

        time.sleep(args.sleep)

    out_path = Path("/tmp/codex_matching_results.json")
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
