# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SPECA (Specification-to-Property Agentic Auditing) — an automated security audit pipeline that uses Claude Code CLI to analyze codebases for vulnerabilities. The pipeline transforms specifications into formal program graphs, generates security properties, pre-resolves code locations, performs proof-based formal audits against target code, and filters false positives via a recall-safe 3-gate review pipeline (Dead Code, Trust Boundary, Scope Check).

## Commands

```bash
# Run tests (pre-flight check used in all CI workflows)
uv run python3 -m pytest tests/ -v --tb=short

# Run a single phase
uv run python3 scripts/run_phase.py --phase 01a

# Run multiple phases sequentially
uv run python3 scripts/run_phase.py --phase 01a 01b 01e

# Run all phases up to a target (resolves dependency chain)
uv run python3 scripts/run_phase.py --target 04 --workers 4

# Force re-execution (clears resume state)
uv run python3 scripts/run_phase.py --phase 03 --force --workers 4 --max-concurrent 64

# Dry-run cleanup check
uv run python3 scripts/run_phase.py --phase 03 --cleanup-dry-run

# Register MCP servers
bash scripts/setup_mcp.sh
bash scripts/setup_mcp.sh --verify
```

## Architecture

### Orchestrator (`scripts/orchestrator/`)

The async Python orchestrator manages the full lifecycle of each phase:

1. **config.py** — `PhaseConfig` Pydantic models define each phase (prompt path, queue/output patterns, batch strategy, circuit breaker thresholds, cost limits, MCP servers, tool filters). All phases live in `PHASE_CONFIGS` dict.
2. **base.py** — `BaseOrchestrator` loads inputs, validates with Pydantic schemas, filters already-processed items (resume), enriches with context, creates batches, executes in parallel via asyncio. Subclasses: `Phase01Orchestrator`, `Phase02cOrchestrator`, `Phase03Orchestrator`, `Phase04Orchestrator`.
3. **runner.py** — `ClaudeRunner` invokes `claude` CLI per batch with `--prompt-path`, `--stream-json`. Includes `CircuitBreaker` (consecutive failures, total retries, empty results) and retry with exponential backoff (max 3).
4. **watchdog.py** — `LogWatcher` tails stream-json logs in real-time via async task; `CostTracker` enforces per-phase budget (hard stop on `BudgetExceeded`).
5. **resume.py** — `ResumeManager` scans `PARTIAL_*.json` outputs, extracts processed IDs, enables incremental execution.
6. **collector.py** — `ResultCollector` saves partial results immediately after each batch. Validation is lenient (warns but doesn't block) to preserve partial progress. Applies `output_fields` filtering to keep PARTIALs compact.
7. **schemas.py** — Pydantic models for all inter-phase data contracts. Cross-phase validation at boundaries (01a→01b→01e→02c→03→04).

### Pipeline Phases

Phase IDs: `01a` → `01b` → `01e` → `02c` → `03` → `04`

- **01a** Spec Discovery: crawl URLs → `outputs/01a_STATE.json`
- **01b** Subgraph Extraction: specs → enriched Mermaid state diagrams (`.mmd` with YAML frontmatter + `note right of` invariant blocks) + `01b_PARTIAL_*.json`
- **01e** Property Generation: trust model analysis (domain-agnostic STRIDE + CWE Top 25) + formal security properties from subgraphs (depends on 01b). **Requires** `outputs/BUG_BOUNTY_SCOPE.json` — orchestrator calls `sys.exit(1)` if missing. Logic inlined in worker prompt (no skill fork). Slim output: `covers` is a string (primary element ID), `reachability` has 4 fields only.
- **02c** Code Pre-resolution: pre-resolve code locations (`code_scope`) for properties against target repository using Tree-sitter MCP. Requires `outputs/TARGET_INFO.json` (created by 02c workflow before phase runs). Also builds `outputs/01b_SUBGRAPH_INDEX.json` from 01b partials for spec-level context. Severity gate drops `Informational` properties. Model: Sonnet.
- **03** Audit Map: proof-based 3-phase formal audit (Map → Prove → Stress-Test) against target codebase. Tries to prove properties hold; gaps in proof are findings. Reads `outputs/TARGET_INFO.json` to auto-clone same target repository/commit. Inlined prompt (no skill fork). Model: Sonnet. Tools: Read/Write/Grep/Glob only.
- **04** Review: 3-gate FP filter pipeline with early exit (Dead Code → Trust Boundary → Scope Check), then severity calibration. Only these 3 gates may produce DISPUTED_FP (recall-safe design). Verdicts: CONFIRMED_VULNERABILITY, CONFIRMED_POTENTIAL, DISPUTED_FP, DOWNGRADED, NEEDS_MANUAL_REVIEW, PASS_THROUGH. Model: Sonnet. Tools: Read/Write/Grep/Glob only (no MCP).

Manual (not orchestrated): `05` PoC Generation, `06` Bug-Bounty Report, `06b` Full Audit Report.

### Skills System

Skills live in `.claude/skills/<name>/SKILL.md`. Each has YAML frontmatter (`name`, `description`, `allowed-tools`, `context: fork`). Currently active skills:
- `spec-discovery` — Phase 01a
- `subgraph-extractor` — Phase 01b

Phases 01e, 02c, 03, and 04 use **inlined prompts** (no skill fork) — all analysis logic is embedded directly in the worker prompt to reduce context fork overhead.

### Data Flow Convention

- **Output naming:** `outputs/{phase_id}_PARTIAL_W{worker}B{batch}_{timestamp}.json`
- **Queue files:** `outputs/{phase_id}_QUEUE_{worker_id}.json`
- **Logs:** `outputs/logs/{phase_id}_W{worker}B{batch}_{timestamp}.jsonl`
- Phases consume `PARTIAL_*.json` glob patterns from upstream phases.
- **01e slim schema:** `covers` = string (primary element ID, e.g. `"FN-001"`). `reachability` = 4 fields: `classification`, `entry_points`, `attacker_controlled`, `bug_bounty_scope`.

### Key Design Decisions

- **Partial results are first-class:** Every batch result is saved immediately. Resume scans these files to skip completed items. Never block saves on validation failures.
- **Circuit breaker is shared:** All workers in a phase share one circuit breaker, so systemic issues (bad prompt, API outage) trigger fast abort.
- **MCP-first code resolution:** Phase 02c uses `mcp__tree_sitter__get_symbols` / `run_query` for code location before reading files. Phase 03 uses built-in Read/Grep/Glob only (no MCP).
- **Budget enforcement:** Cost tracking is built into `ClaudeRunner`, not bolted on. Raises `BudgetExceeded` at the runner level.
- **Phase 02c/03 target consistency:** The 02c CI workflow creates `outputs/TARGET_INFO.json` **before** Phase 02c runs, containing target repository and commit info. Phases 03 and 04 read this same file, ensuring consistency without redundant copies.
- **01b subgraph index for 02c:** Phase 02c builds `outputs/01b_SUBGRAPH_INDEX.json` from 01b partials at load time. Workers use this index to find spec-level function names, state transitions, and mermaid files for improved code resolution accuracy.
- **Phase 02c optimization:** Pre-resolves code locations for properties before Phase 03, reducing redundant MCP calls and token consumption by ~40-60%.
- **Inline prompts (01e, 02c, 03, 04):** Full analysis logic inlined in worker prompts (no skill fork), reducing context fork overhead. Phase 01e inlines trust model + domain-agnostic STRIDE + property generation; Phase 03 inlines proof-based 3-phase audit; Phase 04 inlines 3-gate FP filter pipeline.
- **Required bug_bounty_scope:** Phase 01e requires `outputs/BUG_BOUNTY_SCOPE.json`. The orchestrator aborts with `sys.exit(1)` if the file is missing or unparseable. No hardcoded defaults.
- **Domain-agnostic STRIDE + CWE Top 25:** Phase 01e uses a general STRIDE thinking framework augmented with CWE Top 25 patterns (CWE-22/78/89/94/200/502/639/770/862). No domain-specific hardcoding; suitable for any target system.

### Environment Variables

- `KEYWORDS`, `SPEC_URLS` — Phase 01a discovery inputs
- `FORCE_EXECUTE=1` — Bypass resume (set automatically by `--force` flag)
- `CLAUDE_CODE_PERMISSIONS=bypassPermissions` — Used in CI
- `CLAUDE_CODE_MAX_OUTPUT_TOKENS=100000` — Used in CI
- `GITHUB_PERSONAL_ACCESS_TOKEN` — For GitHub MCP server
