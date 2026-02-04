#!/usr/bin/env python3
"""Build a CVEfixes subset dataset for distributed systems OSS.

Requires a local CVEfixes SQLite database. This script will extract function-level
before/after code pairs and emit a paired JSONL dataset compatible with the
benchmark evaluators.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Iterable


DEFAULT_REPOS = [
    "apache/kafka",
    "apache/cassandra",
    "apache/hadoop",
    "apache/zookeeper",
    "apache/spark",
    "apache/flink",
    "apache/beam",
    "etcd-io/etcd",
    "redis/redis",
    "cockroachdb/cockroach",
    "envoyproxy/envoy",
    "kubernetes/kubernetes",
    "grpc/grpc",
    "torvalds/linux",
    "systemd/systemd",
    "iproute2/iproute2",
    "openssl/openssl",
    "nginx/nginx",
    "apache/httpd",
    "curl/curl",
    "isc-projects/kea",
    "isc-projects/bind9",
]

BEFORE_COLS = [
    "func_before",
    "function_before",
    "before",
    "code_before",
    "old_code",
    "buggy_code",
    "vuln_code",
    "function_code_before",
]
AFTER_COLS = [
    "func_after",
    "function_after",
    "after",
    "code_after",
    "fixed_code",
    "patched_code",
    "function_code_after",
]
REPO_COLS = [
    "repo",
    "repo_name",
    "repository",
    "project",
    "project_name",
    "repo_url",
    "repository_url",
]
FILE_COLS = ["file_path", "path", "filename", "file"]
LANG_COLS = ["language", "lang"]
CVE_COLS = ["cve_id", "cve", "cveId"]
CWE_COLS = ["cwe_id", "cwe", "cwe_ids", "cwe_list"]
ID_COLS = ["id", "function_id", "func_id", "method_id"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CVEfixes subset dataset.")
    parser.add_argument("--db", type=Path, required=True, help="Path to CVEfixes SQLite DB")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path")
    parser.add_argument("--repos", type=str, default=",".join(DEFAULT_REPOS))
    parser.add_argument("--max-per-repo", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return [row[0] for row in rows]


def list_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [row[1] for row in rows]


def pick_column(columns: Iterable[str], candidates: list[str]) -> str | None:
    cols = {col.lower(): col for col in columns}
    for candidate in candidates:
        key = candidate.lower()
        if key in cols:
            return cols[key]
    return None


def detect_table(conn: sqlite3.Connection) -> tuple[str, dict[str, str | None]]:
    tables = list_tables(conn)
    best = None
    best_cols = None
    for table in tables:
        columns = list_columns(conn, table)
        before_col = pick_column(columns, BEFORE_COLS)
        after_col = pick_column(columns, AFTER_COLS)
        if not before_col or not after_col:
            continue
        repo_col = pick_column(columns, REPO_COLS)
        id_col = pick_column(columns, ID_COLS) or "rowid"
        candidate = {
            "before": before_col,
            "after": after_col,
            "repo": repo_col,
            "file": pick_column(columns, FILE_COLS),
            "lang": pick_column(columns, LANG_COLS),
            "cve": pick_column(columns, CVE_COLS),
            "cwe": pick_column(columns, CWE_COLS),
            "id": id_col,
        }
        if repo_col:
            return table, candidate
        if best is None:
            best = table
            best_cols = candidate
    if best and best_cols:
        return best, best_cols
    raise RuntimeError("Could not find a table with before/after code columns.")


def normalize_repo(value: str) -> str:
    text = value.strip().lower()
    if text.startswith("https://github.com/"):
        text = text[len("https://github.com/") :]
    return text.rstrip("/")


def matches_repo(repo_value: str, repo_filters: list[str]) -> bool:
    if not repo_filters:
        return True
    normalized = normalize_repo(repo_value)
    return any(filter_value in normalized for filter_value in repo_filters)


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")

    repo_filters = [item.strip().lower() for item in args.repos.split(",") if item.strip()]

    conn = sqlite3.connect(str(args.db))
    table, cols = detect_table(conn)

    select_cols = [
        cols["id"],
        cols["before"],
        cols["after"],
    ]
    col_aliases = ["id", "before", "after"]
    for key, alias in (
        ("repo", "repo"),
        ("file", "file_path"),
        ("lang", "language"),
        ("cve", "cve"),
        ("cwe", "cwe"),
    ):
        if cols.get(key):
            select_cols.append(cols[key])
            col_aliases.append(alias)

    query = f"SELECT {', '.join(select_cols)} FROM {table}"
    rows = conn.execute(query)

    output = []
    per_repo_counts = {}
    total = 0
    for row in rows:
        data = dict(zip(col_aliases, row))
        before = data.get("before")
        after = data.get("after")
        if not isinstance(before, str) or not before.strip():
            continue
        if not isinstance(after, str) or not after.strip():
            continue
        repo_value = data.get("repo")
        if repo_value and repo_filters:
            if not matches_repo(str(repo_value), repo_filters):
                continue
        repo_key = normalize_repo(str(repo_value)) if repo_value else "unknown"
        if args.max_per_repo and per_repo_counts.get(repo_key, 0) >= args.max_per_repo:
            continue

        pair_id = f"{table}:{data.get('id')}"
        base = {
            "pair_id": pair_id,
            "cve": data.get("cve"),
            "cwe_id": data.get("cwe"),
            "file_path": data.get("file_path"),
            "language": data.get("language"),
            "repo": data.get("repo"),
        }
        output.append({**base, "vul_type": "vulnerable", "before": before})
        output.append({**base, "vul_type": "clean", "after": after})
        per_repo_counts[repo_key] = per_repo_counts.get(repo_key, 0) + 1
        total += 1
        if args.limit and total >= args.limit:
            break

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in output:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {len(output)} rows ({total} pairs) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
