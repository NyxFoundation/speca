#!/usr/bin/env python3
"""Collect outputs/03_*.json from branches into benchmarks/results/..."""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def resolve_branch(branch: str) -> str:
    candidates = [
        branch,
        f"origin/{branch}",
        f"refs/heads/{branch}",
        f"refs/remotes/origin/{branch}",
    ]
    for ref in candidates:
        try:
            run_git(["show-ref", "--verify", "--quiet", ref])
            return ref
        except subprocess.CalledProcessError:
            continue
    return branch


def list_output_files(branch: str) -> list[str]:
    try:
        output = run_git(["ls-tree", "--name-only", f"{branch}:outputs"])
    except subprocess.CalledProcessError:
        return []
    files = [line.strip() for line in output.splitlines() if line.strip()]
    return [f for f in files if f.endswith(".json")]


def filter_output_files(files: Iterable[str], globs: list[str]) -> list[str]:
    filtered: list[str] = []
    for name in files:
        if any(fnmatch.fnmatch(name, pattern) for pattern in globs):
            filtered.append(name)
    return filtered


_TS_RE = re.compile(r"_W(?P<worker>\d+)_(?P<ts>\d{9,})_(?P<seq>\d+)\.json$")
_LOG_TS_RE = re.compile(r"^(?P<phase>\d+)_w(?P<worker>\d+)b(?P<batch>\d+)_(?P<ts>\d{9,})\.log\.jsonl$")


def estimate_phase_timing(files: Iterable[str]) -> dict:
    per_worker: dict[str, dict] = {}
    all_ts: list[int] = []
    for name in files:
        match = _TS_RE.search(name)
        if not match:
            continue
        ts = int(match.group("ts"))
        worker = match.group("worker")
        entry = per_worker.setdefault(
            worker,
            {"min_ts": ts, "max_ts": ts, "count": 0, "estimated_seconds": 0},
        )
        entry["min_ts"] = min(entry["min_ts"], ts)
        entry["max_ts"] = max(entry["max_ts"], ts)
        entry["count"] += 1
        all_ts.append(ts)

    if not all_ts:
        return {}

    for entry in per_worker.values():
        entry["estimated_seconds"] = max(0, entry["max_ts"] - entry["min_ts"])

    return {
        "estimated_start_ts": min(all_ts),
        "estimated_end_ts": max(all_ts),
        "estimated_total_seconds": max(0, max(all_ts) - min(all_ts)),
        "per_worker": per_worker,
        "source": "filename_timestamps",
    }


def list_log_files(branch: str, logs_dir: str) -> list[str]:
    try:
        output = run_git(["ls-tree", "--name-only", f"{branch}:{logs_dir}"])
    except subprocess.CalledProcessError:
        return []
    files = [line.strip() for line in output.splitlines() if line.strip()]
    return [f for f in files if f.endswith(".log.jsonl")]


def parse_epoch(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            return float(value) / 1000.0
        return float(value)
    if isinstance(value, str):
        try:
            from datetime import datetime

            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            return datetime.fromisoformat(text).timestamp()
        except Exception:
            return None
    return None


def extract_log_timing(log_text: str, filename_ts: int) -> dict:
    min_ts = None
    max_ts = None
    duration_candidates: list[float] = []
    token_totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    token_sources = {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    }

    def add_usage(usage: dict) -> None:
        for key in token_sources:
            value = usage.get(key)
            if isinstance(value, (int, float)):
                token_totals[key] += int(value)

    def add_model_usage(model_usage: dict) -> None:
        if not isinstance(model_usage, dict):
            return
        for model, entry in model_usage.items():
            if not isinstance(entry, dict):
                continue
            input_tokens = entry.get("inputTokens")
            output_tokens = entry.get("outputTokens")
            cache_read = entry.get("cacheReadInputTokens")
            cache_create = entry.get("cacheCreationInputTokens")
            if isinstance(input_tokens, (int, float)):
                token_totals["input_tokens"] += int(input_tokens)
            if isinstance(output_tokens, (int, float)):
                token_totals["output_tokens"] += int(output_tokens)
            if isinstance(cache_read, (int, float)):
                token_totals["cache_read_input_tokens"] += int(cache_read)
            if isinstance(cache_create, (int, float)):
                token_totals["cache_creation_input_tokens"] += int(cache_create)
    for line in log_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key in ("timestamp", "ts", "time", "created_at", "created", "event_time"):
            ts = parse_epoch(payload.get(key))
            if ts is None:
                continue
            min_ts = ts if min_ts is None else min(min_ts, ts)
            max_ts = ts if max_ts is None else max(max_ts, ts)
        for key in ("duration_ms", "duration", "elapsed", "latency_ms"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                duration_candidates.append(float(value))
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(usage, dict):
            add_usage(usage)
        message = payload.get("message") if isinstance(payload, dict) else None
        if isinstance(message, dict) and isinstance(message.get("usage"), dict):
            add_usage(message["usage"])
        model_usage = payload.get("modelUsage") if isinstance(payload, dict) else None
        if isinstance(model_usage, dict):
            add_model_usage(model_usage)
        for key in token_sources:
            value = payload.get(key)
            if isinstance(value, (int, float)):
                token_totals[key] += int(value)
    if min_ts is None or max_ts is None:
        min_ts = float(filename_ts)
        max_ts = float(filename_ts)
        source = "filename_timestamp"
    else:
        source = "log_event_timestamps"
    estimated_seconds = max(0.0, max_ts - min_ts)
    if duration_candidates and estimated_seconds == 0.0:
        candidate = max(duration_candidates)
        if candidate > 10_000_000_000:
            candidate = candidate / 1000.0
        elif candidate > 10000:
            candidate = candidate / 1000.0
        estimated_seconds = max(estimated_seconds, float(candidate))
        source = "log_duration_field"
    if token_totals["total_tokens"] == 0:
        token_totals["total_tokens"] = (
            token_totals["input_tokens"]
            + token_totals["output_tokens"]
            + token_totals["cache_read_input_tokens"]
            + token_totals["cache_creation_input_tokens"]
        )
    return {
        "estimated_start_ts": min_ts,
        "estimated_end_ts": max_ts,
        "estimated_seconds": estimated_seconds,
        "source": source,
        "tokens": token_totals,
    }


def collect_phase_logs(branch: str, logs_dir: str, phase_id: str) -> dict:
    files = list_log_files(branch, logs_dir)
    phase_logs = []
    total_tokens = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }

    for name in files:
        match = _LOG_TS_RE.match(name)
        if not match or match.group("phase") != phase_id:
            continue
        ts = int(match.group("ts"))
        try:
            content = run_git(["show", f"{branch}:{logs_dir}/{name}"])
        except subprocess.CalledProcessError:
            continue
        timing = extract_log_timing(content, ts)
        tokens = timing.get("tokens") or {}
        for key in total_tokens:
            value = tokens.get(key)
            if isinstance(value, (int, float)):
                total_tokens[key] += int(value)
        phase_logs.append({"file": name, **timing})

    if not phase_logs:
        return {}

    starts = [entry["estimated_start_ts"] for entry in phase_logs if entry.get("estimated_start_ts") is not None]
    ends = [entry["estimated_end_ts"] for entry in phase_logs if entry.get("estimated_end_ts") is not None]
    sources = {entry.get("source") for entry in phase_logs if entry.get("source")}
    return {
        "phase_id": phase_id,
        "log_files": len(phase_logs),
        "estimated_start_ts": min(starts) if starts else None,
        "estimated_end_ts": max(ends) if ends else None,
        "estimated_total_seconds": max(ends) - min(starts) if starts and ends else 0.0,
        "sources": sorted(sources),
        "per_log": phase_logs,
        "tokens": total_tokens,
        "source": "logs",
    }


def write_file(branch: str, path: str, dest: Path) -> None:
    content = run_git(["show", f"{branch}:outputs/{path}"])
    dest.write_text(content, encoding="utf-8")


def sanitize_branch(branch: str) -> str:
    return branch.replace("/", "__")


def collect_branch(branch: str, output_root: Path, globs: list[str], logs_dir: str, log_phase: str) -> dict:
    ref = resolve_branch(branch)
    sanitized = sanitize_branch(branch)
    dest_dir = output_root / sanitized
    dest_dir.mkdir(parents=True, exist_ok=True)

    files = list_output_files(ref)
    files = filter_output_files(files, globs)
    collected = []
    for name in files:
        dest = dest_dir / name
        write_file(ref, name, dest)
        collected.append(name)

    target_info = {}
    if "03_TARGET_INFO.json" in files:
        try:
            target_info = json.loads(run_git(["show", f"{ref}:outputs/03_TARGET_INFO.json"]))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            target_info = {}

    commit = ""
    if target_info.get("target_commit"):
        commit = str(target_info.get("target_commit"))
    else:
        try:
            commit = run_git(["rev-parse", ref])
        except subprocess.CalledProcessError:
            commit = ""

    manifest = {
        "branch": branch,
        "ref": ref,
        "sanitized_branch": sanitized,
        "files": collected,
        "commit": commit,
        "commit_short": commit[:8] if commit else "",
        "target_info": target_info,
        "phase_timing": estimate_phase_timing(collected),
        "phase_log_timing": collect_phase_logs(ref, logs_dir, log_phase),
    }
    (dest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def parse_branches(value: str) -> list[str]:
    parts = [item.strip() for item in value.split(",")]
    return [p for p in parts if p]


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect outputs/03_*.json from branches")
    parser.add_argument("--branches", required=True, help="Comma-separated branch names")
    parser.add_argument(
        "--output-globs",
        default="03_PARTIAL_*.json,03_AUDITMAP_PARTIAL_*.json,03_TARGET_INFO.json,03_*.json",
        help="Comma-separated glob patterns to select outputs (default includes 03_PARTIAL/03_AUDITMAP_PARTIAL)",
    )
    parser.add_argument("--logs-dir", default="outputs/logs", help="Logs directory in repo")
    parser.add_argument("--log-phase", default="03", help="Phase ID to aggregate logs for")
    parser.add_argument(
        "--output-root",
        default=str(ROOT_DIR / "benchmarks" / "results" / "rq1" / "sherlock_ethereum_audit_contest"),
        help="Output root directory",
    )
    args = parser.parse_args()
    globs = [g.strip() for g in args.output_globs.split(",") if g.strip()]

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    manifests = []
    for branch in parse_branches(args.branches):
        manifests.append(collect_branch(branch, output_root, globs, args.logs_dir, args.log_phase))

    summary_path = output_root / "collection_summary.json"
    summary_path.write_text(
        json.dumps(
            {"branches": manifests, "output_globs": globs, "logs_dir": args.logs_dir, "log_phase": args.log_phase},
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
