#!/usr/bin/env python3
"""RQ1 matching logic (stage1/2/3)."""

from __future__ import annotations

import difflib
import json
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
    text: str
    normalized: str
    tokens: set[str]


@dataclass
class AuditItem:
    item_id: str
    description: str
    snippet: str
    file: str
    line: str
    text: str
    normalized: str
    tokens: set[str]


def normalize_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9_]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def tokenize(text: str) -> set[str]:
    if not text:
        return set()
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_csv_issues(path: Path) -> list[Issue]:
    import csv

    issues: list[Issue] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            title = (row.get("title") or "").strip()
            description = (row.get("description") or "").strip()
            issue_id = str(row.get("number") or "").strip()
            text = f"{title}\n{description}".strip()
            normalized = normalize_text(text)
            tokens = tokenize(text)
            issues.append(Issue(issue_id, title, description, text, normalized, tokens))
    return issues


def build_audit_text(raw: dict) -> tuple[str, str, str, str, str]:
    item_id = str(raw.get("id") or raw.get("check_id") or "")
    description = str(raw.get("description") or raw.get("summary") or "")
    snippet = str(raw.get("snippet") or "")
    file = str(raw.get("file") or "")
    line = str(raw.get("line") or "")

    code_scope = raw.get("code_scope") if isinstance(raw.get("code_scope"), dict) else {}
    scope_desc = str(code_scope.get("description") or "")

    text_parts = [description, scope_desc, snippet, file, line]
    text = "\n".join(part for part in text_parts if part).strip()
    return item_id, description, snippet, file, line if line else "", text


def extract_audit_items(files: Iterable[Path]) -> list[AuditItem]:
    items: list[AuditItem] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        raw_items: list[dict] = []
        if isinstance(payload, dict) and isinstance(payload.get("audit_items"), list):
            raw_items = [item for item in payload.get("audit_items") if isinstance(item, dict)]
        elif isinstance(payload, list):
            raw_items = [item for item in payload if isinstance(item, dict)]

        if not raw_items:
            continue

        for raw in raw_items:
            item_id, description, snippet, file, line, text = build_audit_text(raw)
            normalized = normalize_text(text)
            tokens = tokenize(text)
            items.append(AuditItem(item_id, description, snippet, file, line, text, normalized, tokens))
    return items


def select_keyword_candidates(
    audit_item: AuditItem,
    issues: list[Issue],
    top_k: int,
    min_overlap: int,
) -> list[Issue]:
    scored: list[tuple[int, float, Issue]] = []
    for issue in issues:
        overlap = len(audit_item.tokens & issue.tokens)
        if overlap < min_overlap:
            continue
        score = jaccard(audit_item.tokens, issue.tokens)
        scored.append((overlap, score, issue))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [issue for overlap, score, issue in scored[:top_k]]


def call_claude(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "--output-format", "json", "-p", prompt],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
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
        return None

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def llm_match(audit_item: AuditItem, candidates: list[Issue]) -> tuple[bool, str | None, float]:
    if not candidates:
        return False, None, 0.0

    candidate_block = []
    for idx, issue in enumerate(candidates):
        candidate_block.append(
            f"[{idx}] ID={issue.issue_id}\nTitle: {issue.title}\nDescription: {issue.description}\n"
        )

    prompt = (
        "You are matching security findings. Decide if the audit finding matches any candidate issue."
        ' Respond with JSON only: {"match": true|false, "candidate_index": number|null, "confidence": 0-1}.\n\n'
        "Audit finding:\n"
        f"{audit_item.text}\n\n"
        "Candidates:\n"
        + "\n".join(candidate_block)
        + "\n"
    )

    raw = call_claude(prompt)
    payload = extract_json_from_text(raw) or {}
    match = bool(payload.get("match"))
    idx = payload.get("candidate_index")
    confidence = payload.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    if match and isinstance(idx, int) and 0 <= idx < len(candidates):
        return True, candidates[idx].issue_id, confidence
    return False, None, confidence


def match_items(
    audit_items: list[AuditItem],
    issues: list[Issue],
    use_llm: bool,
    llm_max: int,
    stage1_threshold: float,
    stage2_threshold: float,
    keyword_min_overlap: int,
    candidate_top_k: int,
) -> tuple[dict[str, dict], dict, int]:
    matches: dict[str, dict] = {}
    stage_counts = {"stage1": 0, "stage2": 0, "stage3": 0}
    llm_calls = 0

    for item in audit_items:
        best_score = 0.0
        best_issue = None
        for issue in issues:
            score = similarity(item.normalized, issue.normalized)
            if score > best_score:
                best_score = score
                best_issue = issue
        if best_issue and best_score >= stage1_threshold:
            matches[item.item_id] = {
                "stage": "stage1",
                "issue_id": best_issue.issue_id,
                "score": best_score,
            }
            stage_counts["stage1"] += 1

    for item in audit_items:
        if item.item_id in matches:
            continue
        best_score = 0.0
        best_issue = None
        for issue in issues:
            overlap = len(item.tokens & issue.tokens)
            score = jaccard(item.tokens, issue.tokens)
            if score > best_score and overlap >= 3:
                best_score = score
                best_issue = issue
        if best_issue and best_score >= stage2_threshold:
            matches[item.item_id] = {
                "stage": "stage2",
                "issue_id": best_issue.issue_id,
                "score": best_score,
            }
            stage_counts["stage2"] += 1

    if use_llm:
        for item in audit_items:
            if item.item_id in matches:
                continue
            if llm_calls >= llm_max:
                break
            candidates = select_keyword_candidates(
                item,
                issues,
                top_k=candidate_top_k,
                min_overlap=keyword_min_overlap,
            )
            if not candidates:
                continue
            llm_calls += 1
            matched, issue_id, confidence = llm_match(item, candidates)
            if matched and issue_id:
                matches[item.item_id] = {
                    "stage": "stage3",
                    "issue_id": issue_id,
                    "score": confidence,
                }
                stage_counts["stage3"] += 1

    return matches, stage_counts, llm_calls
