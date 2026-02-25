#!/usr/bin/env python3
"""RQ1 matching logic — LLM-based issue recall measurement.

For each known H/M/L issue from the CSV, ask the LLM whether any audit
finding across all branches detected the same root cause.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class Issue:
    issue_id: str
    title: str
    description: str
    severity: str


@dataclass
class AuditItem:
    item_id: str
    text: str
    classification: str | None = None
    branch: str = ""


def load_csv_issues(
    path: Path,
    severity_filter: set[str] | None = None,
) -> list[Issue]:
    import csv

    issues: list[Issue] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            severity = (row.get("submitted_severity") or "").strip().lower()
            if severity_filter and severity not in severity_filter:
                continue
            title = (row.get("title") or "").strip()
            description = (row.get("description") or "").strip()
            issue_id = str(row.get("number") or "").strip()
            issues.append(Issue(issue_id, title, description, severity))
    return issues


def _build_audit_text(raw: dict) -> tuple[str, str, str]:
    """Return (item_id, text, classification) from a Phase 03 audit item."""
    item_id = str(raw.get("property_id") or "")
    classification = str(raw.get("classification") or "")
    parts = [
        str(raw.get("proof_trace") or ""),
        str(raw.get("attack_scenario") or ""),
        str(raw.get("code_path") or ""),
    ]
    text = "\n".join(p for p in parts if p).strip()
    return item_id, text, classification


def extract_audit_items(
    files: Iterable[Path],
    classification_filter: set[str] | None = None,
    branch: str = "",
) -> list[AuditItem]:
    items: list[AuditItem] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        raw_items: list[dict] = []
        if isinstance(payload, dict) and isinstance(payload.get("audit_items"), list):
            raw_items = [item for item in payload["audit_items"] if isinstance(item, dict)]
        for raw in raw_items:
            cls = raw.get("classification")
            if classification_filter:
                if not isinstance(cls, str) or cls.strip().lower() not in classification_filter:
                    continue
            item_id, text, classification = _build_audit_text(raw)
            items.append(AuditItem(item_id, text, classification=classification, branch=branch))
    return items


# ── LLM helpers ──────────────────────────────────────────────────────


def call_llm(prompt: str) -> str:
    env = os.environ.copy()
    for var in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID"):
        env.pop(var, None)

    model = env.get("RQ1_MODEL", "haiku")
    command = ["claude", "--output-format", "json", "--model", model, "-p", prompt]

    result = subprocess.run(
        command, check=False, capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        print(f"[rq1] call_llm failed (rc={result.returncode}): {result.stderr[:300] if result.stderr else ''}")
        return ""
    try:
        envelope = json.loads(result.stdout)
        if isinstance(envelope, dict) and "result" in envelope:
            return str(envelope["result"])
    except (json.JSONDecodeError, TypeError):
        pass
    return result.stdout


def extract_json_from_text(text: str) -> dict | None:
    if not text:
        return None
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list) and payload:
            return payload[0] if isinstance(payload[0], dict) else None
    except json.JSONDecodeError:
        pass
    # Nested envelope
    try:
        wrapper = json.loads(text)
        if isinstance(wrapper, dict) and "content" in wrapper:
            content = wrapper.get("content")
            if isinstance(content, list):
                combined = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            else:
                combined = str(content)
            match = re.search(r"\{.*\}", combined, flags=re.DOTALL)
            if match:
                return json.loads(match.group(0))
    except Exception:
        pass
    # Regex fallback
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _truncate(text: str, max_chars: int = 300) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


# ── Core matching ────────────────────────────────────────────────────


def _parse_response(raw: str, candidate_ids: list[str], index_key: str = "finding_index") -> tuple[bool, str | None, float]:
    """Parse LLM response → (matched, candidate_id, confidence)."""
    payload = extract_json_from_text(raw) or {}
    matched = bool(payload.get("match"))
    # Try the specific key first, then common fallbacks
    idx = payload.get(index_key)
    if idx is None:
        for fallback in ("finding_index", "issue_index", "candidate_index"):
            if fallback != index_key and fallback in payload:
                idx = payload[fallback]
                break
    confidence = payload.get("confidence")
    try:
        confidence = float(confidence)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        confidence = 0.0
    if matched:
        cid = None
        if isinstance(idx, int) and 0 <= idx < len(candidate_ids):
            cid = candidate_ids[idx]
        return True, cid, confidence
    return False, None, confidence


def match_issues(
    issues: list[Issue],
    audit_items: list[AuditItem],
    cache_path: Path | None = None,
) -> tuple[dict[str, dict], int]:
    """For each issue, ask LLM if any audit finding detected it."""
    # Build shared findings block
    finding_lines = []
    finding_ids = []
    for idx, item in enumerate(audit_items):
        finding_lines.append(f"[{idx}] {item.item_id} ({item.branch}): {_truncate(item.text)}")
        finding_ids.append(item.item_id)
    findings_text = "\n".join(finding_lines)

    matches: dict[str, dict] = {}
    cache_handle = None
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_handle = cache_path.open("w", encoding="utf-8")

    try:
        for issue in issues:
            prompt = (
                "Was the following known vulnerability detected by any of the audit findings below?\n"
                'Respond with JSON only: {"match": true|false, "finding_index": number|null, "confidence": 0.0-1.0}\n\n'
                f"KNOWN VULNERABILITY (Issue #{issue.issue_id}, {issue.severity}):\n"
                f"Title: {issue.title}\n"
                f"Description: {_truncate(issue.description, 500)}\n\n"
                f"AUDIT FINDINGS ({len(audit_items)} total):\n{findings_text}\n"
            )

            print(f"[rq1] issue #{issue.issue_id}: start (findings={len(audit_items)}, prompt={len(prompt)} chars)")
            raw = call_llm(prompt)
            print(f"[rq1] issue #{issue.issue_id}: done ({len(raw)} bytes)")

            if cache_handle:
                cache_handle.write(json.dumps({
                    "issue_id": issue.issue_id,
                    "raw": raw,
                    "finding_ids": finding_ids,
                }, ensure_ascii=False) + "\n")
                cache_handle.flush()

            matched, finding_id, confidence = _parse_response(raw, finding_ids)
            if matched:
                matches[issue.issue_id] = {"finding_id": finding_id, "confidence": confidence}
                print(f"[rq1] issue #{issue.issue_id}: MATCHED -> {finding_id} (conf={confidence})")
            else:
                print(f"[rq1] issue #{issue.issue_id}: no match (conf={confidence})")
    finally:
        if cache_handle:
            cache_handle.close()

    return matches, len(issues)


def reparse_cache(cache_path: Path) -> tuple[dict[str, dict], int]:
    """Re-parse cached LLM responses without calling LLM."""
    matches: dict[str, dict] = {}
    total = 0
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        issue_id = record.get("issue_id", "")
        raw = record.get("raw", "")
        finding_ids = record.get("finding_ids", [])

        matched, finding_id, confidence = _parse_response(raw, finding_ids)
        if matched:
            matches[issue_id] = {"finding_id": finding_id, "confidence": confidence}
        print(f"[rq1] reparse #{issue_id}: matched={matched}, finding={finding_id}, conf={confidence}")

    return matches, total


# ── FP detection (finding → issues) ─────────────────────────────────


def check_findings_fp(
    findings: list[AuditItem],
    issues: list[Issue],
    cache_path: Path | None = None,
) -> dict[str, dict]:
    """For each finding, check if it matches any issue. Returns {finding_id: {issue_id, severity, title, confidence}}."""
    issue_lines = []
    issue_ids = []
    issue_map = {i.issue_id: i for i in issues}
    for idx, issue in enumerate(issues):
        issue_lines.append(f"[{idx}] #{issue.issue_id} ({issue.severity}): {issue.title}")
        issue_ids.append(issue.issue_id)
    issues_text = "\n".join(issue_lines)

    results: dict[str, dict] = {}
    cache_handle = None
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_handle = cache_path.open("w", encoding="utf-8")

    try:
        for finding in findings:
            prompt = (
                "Does the following audit finding describe the same vulnerability as any known issue below?\n"
                'Respond with JSON only: {"match": true|false, "issue_index": number|null, "confidence": 0.0-1.0}\n\n'
                f"AUDIT FINDING ({finding.item_id}, {finding.branch}):\n"
                f"{_truncate(finding.text, 400)}\n\n"
                f"KNOWN ISSUES ({len(issues)}):\n{issues_text}\n"
            )
            print(f"[rq1] fp-check {finding.item_id}: start ({len(issues)} issues)")
            raw = call_llm(prompt)
            print(f"[rq1] fp-check {finding.item_id}: done ({len(raw)} bytes)")

            if cache_handle:
                cache_handle.write(json.dumps({
                    "finding_id": finding.item_id,
                    "raw": raw,
                    "issue_ids": issue_ids,
                }, ensure_ascii=False) + "\n")
                cache_handle.flush()

            matched, issue_id, confidence = _parse_response(raw, issue_ids, index_key="issue_index")
            if matched and issue_id:
                issue = issue_map.get(issue_id)
                results[finding.item_id] = {
                    "issue_id": issue_id,
                    "severity": issue.severity if issue else "",
                    "title": issue.title if issue else "",
                    "confidence": confidence,
                }
                print(f"[rq1] fp-check {finding.item_id}: -> #{issue_id} ({issue.severity if issue else '?'})")
            else:
                print(f"[rq1] fp-check {finding.item_id}: no match")
    finally:
        if cache_handle:
            cache_handle.close()

    return results


def reparse_fp_cache(cache_path: Path) -> dict[str, dict]:
    """Re-parse FP detection cache."""
    results: dict[str, dict] = {}
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        finding_id = record.get("finding_id", "")
        raw = record.get("raw", "")
        issue_ids = record.get("issue_ids", [])
        matched, issue_id, confidence = _parse_response(raw, issue_ids, index_key="issue_index")
        if matched and issue_id:
            results[finding_id] = {"issue_id": issue_id, "confidence": confidence}
    return results
