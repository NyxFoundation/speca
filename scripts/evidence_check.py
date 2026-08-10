#!/usr/bin/env python3
"""evidence_check.py — enforce RULES.md (artifact > testimony) mechanically.

A norm doc alone gets ignored; this is the gate that makes RULES.md real. It
reads a PR body / report and enforces:

  R1/R3  every VERIFIED-style claim is an Evidence Block with an adjacent raw log
  R1/R5  every `RERUN: <cmd> EXPECT <substr>` is RE-EXECUTED here (not trusted as
         pasted) and its output must contain <substr>; freshness stops mattering
         because the checker regenerates the output itself
  R2     `UNVERIFIED:` is a first-class passing state (honesty never fails)
  R6     changed-files over the size limit fails unless a SPLIT-JUSTIFIED marker
         explains the split

Markers (HTML comments, so they render invisibly in the PR body):
  <!-- EVIDENCE claim="..." -->        followed by a fenced ``` raw-log block
  <!-- RERUN: <command> EXPECT <substring> -->
  <!-- UNVERIFIED: <reason> -->
  <!-- SPLIT-JUSTIFIED: <reason> -->

Usage:
  python3 scripts/evidence_check.py --body PR_BODY.md [--changed-files N]
  python3 scripts/evidence_check.py --selftest      # red-before-green self-test
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

EVIDENCE = re.compile(r'<!--\s*EVIDENCE\s+claim="([^"]*)"\s*-->')
RERUN = re.compile(r'<!--\s*RERUN:\s*(.+?)\s+EXPECT\s+(.+?)\s*-->')
UNVERIFIED = re.compile(r'<!--\s*UNVERIFIED:\s*(.+?)\s*-->')
SPLIT_OK = re.compile(r'<!--\s*SPLIT-JUSTIFIED:\s*(.+?)\s*-->')
FENCE = re.compile(r'^\s*```')
# claim keywords that, standing alone as prose, are inadmissible testimony (R3)
CLAIM_KW = re.compile(
    r'\b(verified|confirmed|passes|passing|all green|tests? pass)\b|確認しました|検証済み',
    re.IGNORECASE,
)

DEFAULT_SIZE_LIMIT = 40  # changed files; #118 was 136


class Finding:
    def __init__(self, level: str, rule: str, msg: str):
        self.level, self.rule, self.msg = level, rule, msg  # level: FAIL|WARN|OK

    def __str__(self) -> str:
        return f"[{self.level}] {self.rule}: {self.msg}"


def _lines_are_fenced_after(lines: list[str], idx: int, window: int = 3) -> bool:
    """Is there a ``` fence within `window` non-empty lines after line idx? (R3)"""
    seen = 0
    for ln in lines[idx + 1:]:
        if not ln.strip():
            continue
        if FENCE.match(ln):
            return True
        seen += 1
        if seen >= window:
            break
    return False


def _fenced_spans(lines: list[str]) -> list[tuple[int, int]]:
    spans, open_at = [], None
    for i, ln in enumerate(lines):
        if FENCE.match(ln):
            if open_at is None:
                open_at = i
            else:
                spans.append((open_at, i))
                open_at = None
    return spans


def _in_fence(i: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= i <= b for a, b in spans)


def run_rerun(cmd: str, expect: str, cwd: str | None, timeout: int = 120) -> Finding:
    """R1/R5: execute the command ourselves and match EXPECT. Pasted logs are
    never trusted — this regenerates the output."""
    try:
        p = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
    except subprocess.TimeoutExpired:
        return Finding("FAIL", "R1/R5", f"RERUN timed out: {cmd}")
    except Exception as e:  # noqa: BLE001
        return Finding("FAIL", "R1/R5", f"RERUN could not execute ({e}): {cmd}")
    out = (p.stdout or "") + (p.stderr or "")
    if expect in out:
        return Finding("OK", "R1/R5", f"re-ran, found EXPECT {expect!r}: {cmd}")
    return Finding(
        "FAIL", "R1/R5",
        f"re-ran but EXPECT {expect!r} NOT in output (rc={p.returncode}): {cmd}\n"
        f"        --- actual output (first 300 chars) ---\n        {out.strip()[:300]!r}",
    )


def check(text: str, changed_files: int | None = None, size_limit: int = DEFAULT_SIZE_LIMIT,
          strict_claims: bool = False, run: bool = True, cwd: str | None = None) -> list[Finding]:
    lines = text.splitlines()
    spans = _fenced_spans(lines)
    findings: list[Finding] = []

    # R1/R3 — every EVIDENCE claim needs an adjacent raw log
    for i, ln in enumerate(lines):
        m = EVIDENCE.search(ln)
        if m and not _lines_are_fenced_after(lines, i):
            findings.append(Finding(
                "FAIL", "R1/R3",
                f'EVIDENCE claim has no adjacent raw-log fence: "{m.group(1)}"'))

    # R1/R5 — re-run every RERUN
    reruns = RERUN.findall(text)
    if run:
        for cmd, expect in reruns:
            findings.append(run_rerun(cmd.strip(), expect.strip(), cwd))
    else:
        for cmd, expect in reruns:
            findings.append(Finding("WARN", "R1/R5", f"RERUN not executed (--no-run): {cmd}"))

    # R2 — UNVERIFIED always OK
    for reason in UNVERIFIED.findall(text):
        findings.append(Finding("OK", "R2", f"declared UNVERIFIED (honest): {reason}"))

    # R3 — prose claim keyword with no Evidence/Unverified marker on that line's
    # section. Heuristic: a claim keyword outside any fence, on a line that is not
    # itself a marker, and with no EVIDENCE/UNVERIFIED marker within +/-2 lines.
    for i, ln in enumerate(lines):
        if _in_fence(i, spans) or ln.strip().startswith("<!--"):
            continue
        if not CLAIM_KW.search(ln):
            continue
        near = "\n".join(lines[max(0, i - 2): i + 3])
        if EVIDENCE.search(near) or UNVERIFIED.search(near):
            continue
        lvl = "FAIL" if strict_claims else "WARN"
        findings.append(Finding(lvl, "R3", f"bare claim without evidence (line {i+1}): {ln.strip()[:80]}"))

    # R6 — size gate
    if changed_files is not None and changed_files > size_limit:
        if SPLIT_OK.search(text):
            findings.append(Finding("OK", "R6", f"{changed_files} files > {size_limit} but SPLIT-JUSTIFIED"))
        else:
            findings.append(Finding(
                "FAIL", "R6",
                f"{changed_files} changed files exceeds size limit {size_limit}; "
                f"split the PR or add <!-- SPLIT-JUSTIFIED: ... -->"))

    if not findings:
        findings.append(Finding("WARN", "-", "no evidence markers found — nothing to enforce"))
    return findings


def _report(findings: list[Finding]) -> int:
    for f in findings:
        print(str(f))
    fails = [f for f in findings if f.level == "FAIL"]
    print(f"\n{'FAIL' if fails else 'PASS'}: "
          f"{len(fails)} failing, "
          f"{sum(f.level=='WARN' for f in findings)} warnings, "
          f"{sum(f.level=='OK' for f in findings)} ok")
    return 1 if fails else 0


HONEST = '''## Summary
Fixed the counter.

<!-- EVIDENCE claim="the counter prints confirmed=7" -->
```
$ python3 -c "print('confirmed=7')"
confirmed=7
```
<!-- RERUN: python3 -c "print('confirmed=7')" EXPECT confirmed=7 -->

<!-- UNVERIFIED: did not run the 01e join — no real 01e fixture available -->
'''

FABRICATED = '''## Summary
I verified the counter prints confirmed=7. Tests pass.

<!-- EVIDENCE claim="the counter prints confirmed=7" -->
```
$ python3 -c "print('confirmed=7')"
confirmed=7
```
<!-- RERUN: python3 -c "print('confirmed=0')" EXPECT confirmed=7 -->
'''

CLAIM_NO_LOG = '''## Summary
I confirmed everything passes and verified the schema. All green.
'''


def _selftest() -> int:
    """Red-before-green for the gate itself: the honest doc must PASS, the
    fabricated doc (RERUN re-runs to confirmed=0, not 7) must FAIL."""
    honest = _report(check(HONEST, changed_files=3))
    print("--- fabricated (must FAIL) ---")
    fabricated = _report(check(FABRICATED, changed_files=3))
    print("--- bare-claim, strict (must FAIL) ---")
    bare = _report(check(CLAIM_NO_LOG, strict_claims=True))
    assert honest == 0, "honest doc should PASS"
    assert fabricated == 1, "fabricated doc must FAIL (RERUN mismatch caught)"
    assert bare == 1, "bare claim with no evidence must FAIL under --strict-claims"
    print("\nselftest OK: honest PASS, fabricated FAIL, bare-claim FAIL")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Enforce RULES.md evidence blocks")
    ap.add_argument("--body", help="path to PR body / report markdown")
    ap.add_argument("--changed-files", type=int, help="number of changed files (R6 size gate)")
    ap.add_argument("--size-limit", type=int, default=DEFAULT_SIZE_LIMIT)
    ap.add_argument("--strict-claims", action="store_true", help="bare claim keywords FAIL (default WARN)")
    ap.add_argument("--no-run", action="store_true", help="do not execute RERUN commands")
    ap.add_argument("--cwd", help="working dir for RERUN commands")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    if not args.body:
        ap.error("provide --body FILE, or --selftest")
    with open(args.body, encoding="utf-8") as fh:
        text = fh.read()
    findings = check(text, changed_files=args.changed_files, size_limit=args.size_limit,
                     strict_claims=args.strict_claims, run=not args.no_run, cwd=args.cwd)
    return _report(findings)


if __name__ == "__main__":
    sys.exit(main())
