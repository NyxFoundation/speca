#!/usr/bin/env python3
"""Shared helpers for benchmark runners and evaluation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


ID_KEYS = (
    "id",
    "sample_id",
    "uuid",
    "func_hash",
    "idx",
    "index",
    "cve",
    "cve_id",
    "cwe_id",
)

LABEL_KEYS = (
    "label",
    "is_vulnerable",
    "vulnerable",
    "is_vuln",
    "vuln",
    "is_vul",
    "vul",
    "target",
)

CODE_KEYS = (
    "code",
    "code_snippet",
    "snippet",
    "func",
    "function",
    "vuln_code",
    "vul_code",
    "vulnerable_code",
    "buggy_code",
    "before",
    "before_patch",
    "code_before",
    "func_before",
    "source",
    "patched_code",
    "after",
    "code_after",
)

PATH_KEYS = (
    "filename",
    "file",
    "file_path",
    "path",
)

LANG_KEYS = ("language", "lang")

LANG_EXT = {
    "c": "c",
    "c++": "cpp",
    "cpp": "cpp",
    "c#": "cs",
    "cs": "cs",
    "java": "java",
    "python": "py",
    "py": "py",
    "javascript": "js",
    "js": "js",
    "typescript": "ts",
    "ts": "ts",
    "go": "go",
    "golang": "go",
    "rust": "rs",
    "rs": "rs",
    "php": "php",
    "ruby": "rb",
    "rb": "rb",
    "swift": "swift",
    "kotlin": "kt",
}


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_id(record: dict, fallback: int) -> str:
    for key in ID_KEYS:
        value = record.get(key)
        if value is not None and value != "":
            return str(value)
    return f"sample-{fallback}"


def normalize_bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 0:
            return False
        if value == 1:
            return True
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "vulnerable"}:
            return True
        if lowered in {"0", "false", "no", "n", "clean", "non-vulnerable"}:
            return False
    return None


def extract_label(record: dict) -> bool | None:
    for key in LABEL_KEYS:
        if key in record:
            value = normalize_bool(record.get(key))
            if value is not None:
                return value
    return None


def extract_code(record: dict) -> str | None:
    for key in CODE_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def guess_extension(record: dict) -> str:
    for key in PATH_KEYS:
        path_value = record.get(key)
        if isinstance(path_value, str) and path_value:
            suffix = Path(path_value).suffix
            if suffix:
                return suffix.lstrip(".")
    for key in LANG_KEYS:
        lang_value = record.get(key)
        if isinstance(lang_value, str):
            normalized = lang_value.strip().lower()
            ext = LANG_EXT.get(normalized)
            if ext:
                return ext
    return "txt"


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)
