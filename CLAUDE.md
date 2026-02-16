# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SPECA (Specification-to-Checklist Agentic Auditing) — an automated security audit pipeline that uses Claude Code CLI to analyze codebases for vulnerabilities. The pipeline transforms specifications into formal program graphs, generates security properties, creates audit checklists, and performs three-phase formal audits against target code.

## Commands

```bash
# Run tests (pre-flight check used in all CI workflows)
uv run python3 -m pytest tests/ -v --tb=short

# Run a single phase
uv run python3 scripts/run_phase.py --phase 01a

# Run multiple phases sequentially
uv run python3 scripts/run_phase.py --phase 01a 01b 01c

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

1. **config.py** — `PhaseConfig` Pydantic models define each phase (skill path, prompt path, queue/output patterns, batch strategy, circuit breaker thresholds, cost limits). All phases live in `PHASE_CONFIGS` dict.
2. **base.py** — `BaseOrchestrator` loads inputs, validates with Pydantic schemas, filters already-processed items (resume), enriches with context, creates batches, executes in parallel via asyncio. Subclasses: `Phase01Orchestrator`, `Phase02Orchestrator`, `Phase03Orchestrator`, `Phase04Orchestrator`.
3. **runner.py** — `ClaudeRunner` invokes `claude` CLI per batch with `--skill-context`, `--prompt-path`, `--stream-json`. Includes `CircuitBreaker` (consecutive failures, total retries, empty results) and retry with exponential backoff (max 3).
4. **watchdog.py** — `LogWatcher` tails stream-json logs in real-time via async task; `CostTracker` enforces per-phase budget (hard stop on `BudgetExceeded`).
5. **resume.py** — `ResumeManager` scans `PARTIAL_*.json` outputs, extracts processed IDs, enables incremental execution.
6. **collector.py** — `ResultCollector` saves partial results immediately after each batch. Validation is lenient (warns but doesn't block) to preserve partial progress.
7. **schemas.py** — Pydantic models for all inter-phase data contracts. Cross-phase validation at boundaries (01a→01b→01c/01d→01e→02→03→04).

### Pipeline Phases

Phase IDs: `01a` → `01b` → `01c` (verify) / `01d` (trust model) → `01e` → `02` → `02c` → `03` → `04`

- **01a** Spec Discovery: crawl URLs → `outputs/01a_STATE.json`
- **01b** Subgraph Extraction: specs → program graphs (`.mmd` + `index.json`)
- **01c** Subgraph Verification: validate graph structure
- **01d** Trust Model: identify trust boundaries/actors (depends on 01b, parallel with 01c)
- **01e** Property Generation: formal security properties from trust models
- **02** Checklist: generate audit checklist items from properties
- **02c** Code Pre-resolution: pre-resolve code locations (`code_scope`, `code_excerpt`) for checklist items against target repository using Tree-sitter MCP. Requires `target_repo`, `target_ref_type`, `audit_scope`. Creates new branch with `outputs/02c_TARGET_INFO.json`. Reduces token consumption in Phase 03 by ~40-60%.
- **03** Audit Map: three-phase formal audit (Abstract Interpretation → Symbolic Execution → Invariant Proving) against target codebase. Reads `outputs/02c_TARGET_INFO.json` from branch to auto-clone same target repository/commit. Uses pre-resolved code from Phase 02c.
- **04** Review: six-category verdict system (CONFIRMED_VULNERABILITY through REQUIRES_MANUAL_REVIEW)

Manual (not orchestrated): `05` PoC Generation, `06` Bug-Bounty Report, `06b` Full Audit Report.

### Skills System

Skills live in `.claude/skills/<name>/SKILL.md`. Each has YAML frontmatter (`name`, `description`, `allowed-tools`, `context: fork`). Skills are pure functions: they receive JSON input and return JSON output. Worker prompts (`prompts/<phase>_worker.md`) invoke skills via `/skill-name` slash commands, aggregate results, and write output files.

### Data Flow Convention

- **Output naming:** `outputs/{phase_id}_{PREFIX}_PARTIAL_W{worker}B{batch}_{timestamp}.json`
- **Queue files:** `outputs/{phase_id}_QUEUE_{worker_id}.json`
- **Logs:** `outputs/logs/{phase_id}_W{worker}B{batch}_{timestamp}.jsonl`
- Phases consume `PARTIAL_*.json` glob patterns from upstream phases.

### Key Design Decisions

- **Partial results are first-class:** Every batch result is saved immediately. Resume scans these files to skip completed items. Never block saves on validation failures.
- **Circuit breaker is shared:** All workers in a phase share one circuit breaker, so systemic issues (bad prompt, API outage) trigger fast abort.
- **MCP-first code resolution:** Phase 02c and Phase 03 must use `mcp__tree_sitter__get_symbols` / `run_query` for code location before reading files. Direct file access for code resolution is not permitted.
- **Budget enforcement:** Cost tracking is built into `ClaudeRunner`, not bolted on. Raises `BudgetExceeded` at the runner level.
- **Phase 02c/03 target consistency:** Phase 02c creates a new branch with `outputs/02c_TARGET_INFO.json` containing target repository and commit info. Phase 03 reads this file to auto-clone the same target, ensuring consistency. No manual target specification needed in Phase 03.
- **Phase 02c optimization:** Pre-resolves code locations for checklist items before Phase 03, reducing redundant MCP calls and token consumption by ~40-60% in Phase 03.
- **Phase 03 optimization:** Uses unified `formal-audit-unified` skill (single context fork) for all three audit phases (Abstract Interpretation → Symbolic Execution → Invariant Proving). Reduces token consumption by ~75-80% per item compared to sequential skill invocations.

### Environment Variables

- `KEYWORDS`, `SPEC_URLS` — Phase 01a discovery inputs
- `FORCE_EXECUTE=1` — Bypass resume (set automatically by `--force` flag)
- `CLAUDE_CODE_PERMISSIONS=bypassPermissions` — Used in CI
- `CLAUDE_CODE_MAX_OUTPUT_TOKENS=100000` — Used in CI
- `GITHUB_PERSONAL_ACCESS_TOKEN` — For GitHub MCP server
