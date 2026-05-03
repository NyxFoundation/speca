<p align="center">
  <img src="assets/speca_logo.png" alt="SPECA logo" width="240" />
</p>

<h1 align="center">SPECA: A Specification-to-Checklist Agentic Auditing Framework</h1>

<p align="center">
  <a href="https://arxiv.org/abs/2604.26495"><img src="https://img.shields.io/badge/arXiv-2604.26495-b31b1b.svg" alt="arXiv"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/NyxFoundation/speca/actions"><img src="https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
</p>

> **Paper:** Masato Kamba, Hirotake Murakami, Akiyoshi Sannai. *Beyond Code Reasoning: A Specification-Anchored Audit Framework for Expert-Augmented Security Verification.* arXiv preprint [arXiv:2604.26495](https://arxiv.org/abs/2604.26495), 2026.

### Abstract

Security-critical software is routinely audited by tools that reason about vulnerabilities as repository-local code patterns. Yet specification-governed systems — protocol stacks, consensus implementations, cryptographic libraries — are constrained by invariants and correctness conditions defined in natural-language specifications. When a vulnerability arises from what the *specification requires* rather than how code is written, code-level approaches lack the representational vocabulary to detect it, and their false positives resist systematic diagnosis.

**SPECA** is a specification-anchored security audit framework that derives explicit, typed security properties from natural-language specifications and audits implementations through structured **proof-attempt** reasoning grounded in each property. The framework yields three capabilities absent from code-driven auditing:

1. **Spec-dependent detections** that no code-local pattern matcher can express.
2. **Controlled cross-implementation comparison** under a shared property vocabulary.
3. **False positives that decompose into interpretable, pipeline-phase-traceable root causes.**

### speca-cli (TUI front-end)

A Node.js + Ink terminal UI for SPECA — `npx speca-cli@next doctor` to bootstrap, then `speca auth login` and `speca init` to configure a target without hand-editing JSON. Currently shipping M2 (`auth` + `init`); pipeline run / browse land in M3+. Full docs: [`cli/README.md`](cli/README.md). Japanese 5-minute quickstart for hirorogo team: [`docs/hiro/cli-quickstart.md`](docs/hiro/cli-quickstart.md).

### Headline Results

- **Sherlock Ethereum Fusaka Audit Contest** (366 submissions, 10 implementations): SPECA recovers **all 15** in-scope H/M/L vulnerabilities (5H/2M/8L) and independently discovers **4 bugs confirmed by developer fix commits** — including a cryptographic invariant violation absent from all 366 adjudicated contest submissions.
- **RepoAudit C/C++ benchmark** (15 projects, 35 non-disputed ground-truth bugs): SPECA matches the best published precision (**88.9%**, Sonnet 4.5) while surfacing **12 author-validated candidate bugs beyond the established ground truth** — two confirmed by upstream maintainers.
- **All false positives** in the deep analysis (N=16) trace to **three interpretable root causes** — trust boundary misunderstanding (50%), code reading error (37.5%), specification misinterpretation (12.5%) — each mapped to a specific pipeline phase.

See [Evaluation](#evaluation) for full numbers and charts.

## Table of Contents

- [Why SPECA?](#why-speca)
- [speca-cli (TUI front-end)](#speca-cli-tui-front-end)
- [Quick Start](#quick-start)
- [Demo](#demo)
- [Architecture](#architecture)
- [Phases](#phases)
- [Running on GitHub Actions](#running-on-github-actions)
- [Configuration](#configuration)
- [Evaluation](#evaluation) — RQ1 Sherlock + RQ2 RepoAudit, with charts
- [Reproducing the Benchmarks](#reproducing-the-benchmarks)
- [Contributing](#contributing)
- [Citation](#citation)
- [License](#license)

## Why SPECA?

Existing LLM-based auditors begin from the *code* and work outward — scanning a repository for bug-pattern templates, dataflow anomalies, and API misuse. Specification-governed systems break this assumption: a vulnerability can arise from what the spec *requires* even when no local code pattern looks suspicious. The KZG batch-verification bug recovered by SPECA in [§Evaluation](#evaluation) is exactly this kind of issue — a violation of a mathematical invariant defined only in the specification, missed by all 366 contest auditors despite the code being open and well-reviewed.

SPECA inverts the direction of analysis. It begins from the **specification** and derives a typed property vocabulary, then asks the implementation to *prove* each property. This shift produces three capabilities that code-driven tools cannot match:

| | Code-driven auditing | SPECA (specification-anchored) |
|---|---|---|
| **Detection** | Finds defects that look like known bug patterns | Finds defects defined as violations of explicit, typed properties |
| **Cross-implementation comparison** | Each codebase analyzed in isolation | Single property vocabulary applied uniformly across N implementations |
| **False positive triage** | Opaque — "the model thought this was a bug" | FPs decompose into 3 root causes (trust boundary / code reading / spec misinterpretation), each tied to a pipeline phase |

A second, often-overlooked benefit: because every finding is grounded in a specific property derived from a specific spec section, every detection has a **provenance chain** (`property → subgraph → spec section → INV-* label`). This makes findings auditable, not just generated.

### Why "proof-attempt" instead of "find bugs"

An early prototype used the conventional adversarial framing — *"find bugs in this code"* — and produced an **88% false-positive rate**. Without a structured claim to disprove, the model emitted speculative findings with weak grounding. The proof-attempt framing forces the model to commit to a verifiable claim before reporting a gap, and the recall-safe 3-gate review filter (simplified down from a 5-gate prototype, after the dropped gates were shown to filter informational true positives at 0% precision) preserves H/M/L recall while filtering ~2/3 of the remaining false positives.

## Quick Start

### Prerequisites

- **Python 3.11+** and [`uv`](https://github.com/astral-sh/uv) (`pip install uv`)
- **Node.js 20+** (for the Claude Code CLI and MCP servers)
- **Anthropic API access** — `ANTHROPIC_API_KEY` exported in your shell, or a logged-in [Claude Code](https://docs.claude.com/en/docs/claude-code) session
- **`git`** — Phase 03 auto-clones the target repository at the commit pinned in `outputs/TARGET_INFO.json`

### Install

```bash
# 1. Clone
git clone https://github.com/NyxFoundation/speca.git
cd speca

# 2. Install Claude Code CLI (used as the worker runtime)
npm install -g @anthropic-ai/claude-code

# 3. Install Python deps via uv (creates an isolated env)
uv sync

# 4. Register MCP servers (tree_sitter / filesystem / fetch)
bash scripts/setup_mcp.sh
bash scripts/setup_mcp.sh --verify
```

### Run a single phase

```bash
# Smoke-test: discover specs from a seed URL
SPEC_URLS="https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7594.md" \
  uv run python3 scripts/run_phase.py --phase 01a
```

### End-to-end audit

```bash
# Place these two files first:
#   outputs/BUG_BOUNTY_SCOPE.json   # required by Phase 01e
#   outputs/TARGET_INFO.json        # required by Phase 02c/03

uv run python3 scripts/run_phase.py --target 04 --workers 4 --max-concurrent 64
```

Outputs are written to `outputs/<phase_id>_PARTIAL_*.json`. See the [Configuration](#configuration) section below for `BUG_BOUNTY_SCOPE.json` / `TARGET_INFO.json` formats.

### Run the test suite

```bash
uv run python3 -m pytest tests/ -v --tb=short
```

## Demo

See past and ongoing audit runs on the **GitHub Actions** page:

**[View Actions Runs](https://github.com/NyxFoundation/speca/actions)**

Each workflow step (01a through 04) can be triggered independently via `workflow_dispatch`. Results are committed to audit branches and can be reviewed as Pull Requests.

## Architecture

SPECA is organized as a **6-phase pipeline** in two stages: **Knowledge Structuring** (Phases 1–3) transforms natural-language specifications into explicit security properties, and **Systematic Auditing** (Phases 4–6) applies structured proof-attempt reasoning to check whether each implementation satisfies those properties.

<p align="center">
  <img src="assets/pipeline.png" alt="SPECA pipeline" width="900" />
</p>

In multi-implementation settings, the **left stage executes once** against the specification (producing a shared property vocabulary), and the **right stage executes per implementation** — enabling controlled cross-implementation security comparison by holding security expectations constant while varying the code under test.

| Stage | Phase | Name | Purpose |
|---|---|---|---|
| **Knowledge Structuring** | 1 | Specification Discovery | Crawl spec documents into a structured index |
|  | 2 | Subgraph Extraction | Decompose specs into [Nielson & Nielson](https://www.imm.dtu.dk/~hrni/) program graphs with RFC 2119–derived invariants |
|  | 3 | Property Generation | STRIDE + CWE Top 25 threat model → typed security properties (Invariant / Pre / Post / Assumption) |
| **Systematic Auditing** | 4 | Code Pre-resolution | Tree-sitter symbol resolution links each property to source locations (40–60% audit-token reduction) |
|  | 5 | Property-Grounded Audit | Per-property *Map → Prove → Stress-Test* — gaps in the proof are findings |
|  | 6 | Severity-Preserving Review | Three narrow mechanical gates (Dead Code / Trust Boundary / Scope) preserve H/M/L recall |

### The Audit Harness

The pipeline ships as a reusable **audit harness** under `scripts/orchestrator/` — not a one-off script. The harness provides the infrastructure that every phase needs (queueing, parallel worker dispatch, token-aware batching, resume on partial failure, per-phase budget enforcement, shared circuit-breaker logic, and structured log/cost telemetry); each phase plugs in a worker prompt and a Pydantic schema and inherits all of the above for free. This separation is what makes the framework reusable: you can drop in a new phase, target a new codebase, or swap a model backbone without touching the harness itself.

Concretely, the harness:
- **Drives the Claude Code CLI** as the worker runtime (one subprocess per batch, with `--prompt-path` and `--stream-json`), so each worker inherits Claude Code's tool sandbox (Read/Write/Grep/Glob, MCP servers when enabled).
- **Resumes from `outputs/*_PARTIAL_*.json`** so a 10-implementation RQ1 run that's interrupted at hour 4 picks up exactly where it left off without re-spending tokens.
- **Enforces a per-phase budget** at the runner level (`BudgetExceeded` is raised, not logged) so a runaway prompt cannot burn the whole RQ1 budget on a single target.
- **Validates leniently** — Pydantic schema mismatches generate warnings, not aborts; partial results are first-class and never blocked on validation failures.
- **Shares one circuit breaker per phase** across all workers, so systemic issues (bad prompt, API outage, schema drift) trigger a fast abort instead of N parallel failures.

In other words: the harness handles the messy parts of running a 100-target audit at scale, leaving the per-phase prompts to focus on auditing.

```
scripts/
├── run_phase.py            # Entry point
├── setup_mcp.sh            # MCP server registration
└── orchestrator/
    ├── config.py            # Phase definitions (PhaseConfig)
    ├── base.py              # BaseOrchestrator (async pipeline)
    ├── runner.py            # ClaudeRunner + CircuitBreaker
    ├── batch.py             # Token/count-based batching
    ├── queue.py             # Queue splitting & state
    ├── collector.py         # Result parsing & aggregation
    ├── resume.py            # Resume & cleanup manager
    ├── watchdog.py          # LogWatcher + CostTracker
    ├── schemas.py           # Pydantic data contracts
    └── factory.py           # create_orchestrator()
```

> **Phase ID note.** The paper uses Phase 1–6 labels; the codebase uses the legacy IDs `01a → 01b → 01e → 02c → 03 → 04` (a one-to-one mapping). Phases 5–6 of the paper correspond to legacy `03` (Audit Map) and `04` (Audit Review). The remainder of this README uses the legacy IDs to match the file layout.

## Phases

### Phase 01a: Specification Discovery

| | |
|---|---|
| **Prompt** | `prompts/01a_crawl.md` |
| **Skill** | `/spec-discovery` |
| **Input** | Seed URLs (via `SPEC_URLS` env var) |
| **Output** | `outputs/01a_STATE.json` |

Crawls seed URLs to discover all relevant technical specification documents. Uses the `mcp__fetch__fetch` tool to recursively follow links and build a catalog of specification pages.

<details>
<summary>Output example (<code>outputs/01a_STATE.json</code>, from <code>ethereum-fusaka-20260220</code>)</summary>

```json
{
  "start_url": "https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7594.md",
  "found_specs": [
    {
      "url": "https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7594.md",
      "title": "EIP-7594: PeerDAS - Peer Data Availability Sampling",
      "category": "EIP",
      "type": "Standards Track / Core",
      "status": "Final",
      "layer": "consensus+networking",
      "description": "Introducing simple DAS utilizing gossip distribution and peer requests..."
    },
    {
      "url": "https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7823.md",
      "title": "EIP-7823: Set Upper Bounds for MODEXP",
      "category": "EIP",
      "type": "Standards Track / Core",
      "status": "Final",
      "layer": "execution",
      "description": "Restricts each MODEXP precompile input field to a maximum of 8192 bits..."
    }
  ],
  "metadata": {
    "timestamp": "2026-02-05T12:00:00Z",
    "keywords": ["ethereum", "fusaka", "fulu", "osaka", "..."],
    "total_specs": 28,
    "breakdown": { "eips": 11, "consensus_specs": 7, "execution_specs": 9 }
  }
}
```
</details>

### Phase 01b: Subgraph Extraction

| | |
|---|---|
| **Prompt** | `prompts/01b_extract_worker.md` |
| **Skill** | `/subgraph-extractor` |
| **Input** | `outputs/01a_STATE.json` |
| **Output** | `outputs/01b_PARTIAL_*.json` + `outputs/graphs/*/*.mmd` |

Extracts formal **Program Graphs** (following Nielson & Nielson's definition) from each specification document. Each subgraph is output as an enriched Mermaid state diagram (`.mmd`) with YAML frontmatter and inline invariant annotations. PARTIAL JSON files reference the `.mmd` paths for downstream consumption.

<details>
<summary>Output example — PARTIAL JSON (<code>outputs/01b_PARTIAL_W0B1_*.json</code>, from <code>ethereum-fusaka-20260220</code>)</summary>

```json
{
  "specs": [
    {
      "source_url": "https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7951.md",
      "title": "EIP-7951: Precompile for secp256r1 Curve Support",
      "sub_graphs": [
        {
          "id": "SG-001",
          "name": "p256verify_main",
          "mermaid_file": "outputs/graphs/W0B1_1770278556/EIP-7951/SG-001_p256verify_main.mmd"
        },
        {
          "id": "SG-002",
          "name": "input_validation",
          "mermaid_file": "outputs/graphs/W0B1_1770278556/EIP-7951/SG-002_input_validation.mmd"
        },
        {
          "id": "SG-003",
          "name": "signature_verification",
          "mermaid_file": "outputs/graphs/W0B1_1770278556/EIP-7951/SG-003_signature_verification.mmd"
        }
      ]
    }
  ],
  "metadata": {
    "phase": "01b",
    "worker_id": 0,
    "batch_index": 1,
    "item_count": 2,
    "timestamp": 1770278944,
    "processed_ids": ["https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7951.md"]
  }
}
```
</details>

<details>
<summary>Output example — enriched Mermaid file (<code>.mmd</code>)</summary>

```mermaid
---
title: "p256verify_main (EIP-7951: Precompile for secp256r1 Curve Support)"
---
stateDiagram-v2
    direction TB
    [*] --> q_gas: charge 6900 gas
    q_gas --> q_decode: decode input(h, r, s, qx, qy)
    q_decode --> q_validate: input_validation(h, r, s, qx, qy)
    q_validate --> q_fail_validation: validation failed
    q_validate --> q_verify: validation passed
    q_fail_validation --> [*]: return empty
    q_verify --> q_check_result: signature_verification(h, r, s, qx, qy)
    q_check_result --> q_success: verified = true
    q_check_result --> q_fail_verify: verified = false
    q_success --> [*]: return 0x01 (32 bytes)
    q_fail_verify --> [*]: return empty

    note right of q_fail_verify
        INV-001: Precompile MUST NOT revert under any circumstances
        INV-002: Gas cost is always 6900 regardless of execution path
        INV-003: Output is exactly 32 bytes on success or 0 bytes on failure
    end note
```
</details>

### Phase 01e: Property Generation

| | |
|---|---|
| **Prompt** | `prompts/01e_prop_worker.md` (inlined — no skill fork) |
| **Input** | `outputs/01b_PARTIAL_*.json` + `outputs/BUG_BOUNTY_SCOPE.json` (required) |
| **Output** | `outputs/01e_PARTIAL_*.json` |

Performs inline trust model analysis and generates formal security properties from subgraphs. Combines former phases 01d (Trust Model) and property generation into a single inlined prompt. Key features:

- **Domain-agnostic STRIDE + CWE Top 25**: General STRIDE thinking framework augmented with CWE Top 25 patterns (CWE-22/78/89/94/200/502/639/770/862). No domain-specific hardcoding.
- **Reachability classification**: `external-reachable`, `internal-only`, `api-only`
- **Bug bounty scope determination**: Uses `severity_classification` from `BUG_BOUNTY_SCOPE.json` as authoritative severity definitions
- **Slim output**: `covers` is a string (primary element ID), `reachability` has 4 fields only (`classification`, `entry_points`, `attacker_controlled`, `bug_bounty_scope`)

The orchestrator **requires** `outputs/BUG_BOUNTY_SCOPE.json` and aborts if the file is missing.

<details>
<summary>Output example (<code>outputs/01e_PARTIAL_W0B1_*.json</code>, from <code>ethereum-fusaka-20260220</code>)</summary>

```json
{
  "properties": [
    {
      "property_id": "PROP-56ad1eb2-inv-001",
      "text": "P256VERIFY must accept valid secp256r1 signatures and reject all invalid ones deterministically.",
      "type": "invariant",
      "assertion": "forall (h,r,s,qx,qy): p256verify(h,r,s,qx,qy) == true iff ECDSA_verify(h,r,s,(qx,qy)) == true",
      "severity": "CRITICAL",
      "covers": "SG-003",
      "reachability": {
        "classification": "external-reachable",
        "entry_points": ["Transaction", "P2P"],
        "attacker_controlled": true,
        "bug_bounty_scope": "in-scope"
      },
      "bug_bounty_eligible": true,
      "exploitability": "external-attack"
    },
    {
      "property_id": "PROP-56ad1eb2-pre-001",
      "text": "Execution payload parent_hash must chain to state.latest_execution_payload_header.block_hash.",
      "type": "pre-condition",
      "assertion": "forall payload p: p.parent_hash == state.latest_execution_payload_header.block_hash",
      "severity": "HIGH",
      "covers": "SG-002",
      "reachability": {
        "classification": "external-reachable",
        "entry_points": ["P2P"],
        "attacker_controlled": true,
        "bug_bounty_scope": "in-scope"
      },
      "bug_bounty_eligible": true,
      "exploitability": "external-attack"
    }
  ],
  "metadata": {
    "timestamp": "1771748647",
    "total_properties": 45,
    "by_severity": { "CRITICAL": 9, "HIGH": 18, "MEDIUM": 16, "INFORMATIONAL": 2 },
    "by_scope": { "in_scope": 35, "out_of_scope": 10 },
    "bug_bounty_eligible_count": 30
  }
}
```
</details>

### Phase 02c: Code Location Pre-resolution

| | |
|---|---|
| **Prompt** | `prompts/02c_codelocation_worker.md` (inlined — no skill fork) |
| **Input** | `outputs/01e_PARTIAL_*.json` + `outputs/TARGET_INFO.json` + `outputs/01b_SUBGRAPH_INDEX.json` |
| **Output** | `outputs/02c_PARTIAL_*.json` |
| **Model** | Sonnet |

Pre-resolves code locations for each property against the target repository using Tree-sitter MCP (primary) with Glob/Grep fallback. Records file paths, symbol names, and line ranges without extracting code. Applies severity gating (drops `Informational` properties by default). Builds `outputs/01b_SUBGRAPH_INDEX.json` from 01b partials for spec-level context. Reads `outputs/TARGET_INFO.json` (created by 02c workflow before phase runs).

Reduces token consumption in Phase 03 by ~40-60%.

<details>
<summary>Output example — resolved (<code>outputs/02c_PARTIAL_W0B1_*.json</code>)</summary>

```json
{
  "properties_with_code": [
    {
      "property_id": "PROP-56ad1eb2-inv-001",
      "text": "P256VERIFY must accept valid secp256r1 signatures and reject all invalid ones deterministically.",
      "type": "invariant",
      "assertion": "forall (h,r,s,qx,qy): p256verify(h,r,s,qx,qy) == true iff ECDSA_verify(h,r,s,(qx,qy)) == true",
      "severity": "CRITICAL",
      "covers": "SG-003",
      "reachability": { "classification": "external-reachable", "entry_points": ["Transaction", "P2P"], "attacker_controlled": true, "bug_bounty_scope": "in-scope" },
      "exploitability": "external-attack",
      "code_scope": {
        "locations": [
          {
            "file": "core/vm/contracts.go",
            "symbol": "p256Verify.Run",
            "line_range": { "start": 1433, "end": 1449 },
            "role": "primary"
          },
          {
            "file": "crypto/secp256r1/verifier.go",
            "symbol": "Verify",
            "line_range": { "start": 27, "end": 27 },
            "role": "callee"
          }
        ],
        "resolution_status": "resolved",
        "resolution_error": "",
        "resolution_method": "grep_fallback"
      }
    }
  ]
}
```
</details>

<details>
<summary>Output example — out-of-scope / not-found</summary>

```json
{
  "property_id": "PROP-56ad1eb2-inv-004",
  "text": "Blob commitment count in block must not exceed get_blob_parameters(epoch).max_blobs_per_block.",
  "code_scope": {
    "locations": [],
    "resolution_status": "out_of_scope",
    "resolution_error": "Property references get_blob_parameters (consensus-layer function). Target is ethereum/go-ethereum (execution client) with no consensus-layer logic."
  }
}
```
</details>

### Phase 03: Audit Map (Formal Audit)

| | |
|---|---|
| **Prompt** | `prompts/03_auditmap_worker_inline.md` (inlined — no skill fork) |
| **Input** | `outputs/02c_PARTIAL_*.json` + Target codebase (auto-cloned from `TARGET_INFO.json`) |
| **Output** | `outputs/03_PARTIAL_*.json` |
| **Model** | Sonnet |

Performs a proof-based 3-sub-phase formal audit for each property against the target codebase. **The core method: try to prove the property holds; where the proof breaks, that gap is the bug.** This framing was chosen over an adversarial *"find bugs"* prompt after preliminary experiments showed the adversarial approach produced an **88% false positive rate** — without a structured claim to disprove, the model produced numerous speculative findings with weak grounding.

<p align="center">
  <img src="assets/phase5.png" alt="Phase 5 — Property-Grounded Audit (Map / Prove / Stress-Test)" width="700" />
</p>

1. **Sub-phase 1 (Map):** Decompose the property's assertion into verifiable sub-claims, read the enforcement code completely (full function bodies plus callers/callees), and link each sub-claim to the code responsible for satisfying it.
2. **Sub-phase 2 (Prove):** Verify input coverage, path coverage, concurrency safety, temporal validity, and implementation-pattern obligations (e.g., cache keys and deduplication keys computed from complete inputs); gaps are recorded as findings.
3. **Sub-phase 3 (Stress-Test):** Challenge the conclusion — re-examine every assumption (if the proof succeeded) or attempt to construct a concrete attack path (if it failed); findings without a plausible attack path are downgraded to `potential-vulnerability`.

> "Proof attempt" is precise terminology: this is **LLM-driven evidence construction with structured reasoning steps, not formal verification**. The structure is what makes both detections and failures analyzable.

Compact 6-field output per item: `property_id`, `classification`, `code_path`, `proof_trace`, `attack_scenario`, `checklist_id`.

<details>
<summary>Output example — vulnerability found (Sherlock #190: Prysm inclusion proof cache poisoning)</summary>

```json
{
  "audit_items": [
    {
      "property_id": "PROP-6a4369e9-inv-042",
      "classification": "vulnerability",
      "code_path": "beacon-chain/verification/data_column.go::inclusionProofKey::L527-547",
      "proof_trace": "The cache key omits KzgCommitments (the data being proven), including only the inclusion proof and header hash. Two data columns with identical proofs/headers but different commitments produce the same cache key, causing the second to skip verification and reuse the first's cached result.",
      "attack_scenario": "Attacker sends valid DataColumnSidecar A, then sends forged DataColumnSidecar M with same inclusion proof and header but malicious KzgCommitments. Cache lookup succeeds on M's key, bypassing full Merkle verification and accepting invalid commitments.",
      "checklist_id": "PROP-6a4369e9-inv-042"
    }
  ],
  "metadata": {
    "phase": "03",
    "worker_id": 0,
    "batch_index": 81,
    "item_count": 1,
    "timestamp": 1771777036,
    "processed_ids": ["PROP-6a4369e9-inv-042"]
  }
}
```
</details>

<details>
<summary>Output example — not-a-vulnerability (proof succeeded)</summary>

```json
{
  "audit_items": [
    {
      "property_id": "PROP-6a4369e9-inv-047",
      "classification": "not-a-vulnerability",
      "code_path": "eip_7594/src/lib.rs::get_custody_groups::L52",
      "proof_trace": "The loop at L67 is guarded by validation at L52 (ensure! custody_group_count <= number_of_custody_groups). All call paths use local custody_group_count (validator-computed or config-derived), not peer-reported values.",
      "attack_scenario": "",
      "checklist_id": "PROP-6a4369e9-inv-047"
    }
  ]
}
```
</details>

### Phase 04: Audit Review

| | |
|---|---|
| **Prompt** | `prompts/04_review_worker.md` (inlined — no skill fork) |
| **Input** | `outputs/03_PARTIAL_*.json` + `outputs/BUG_BOUNTY_SCOPE.json` + `outputs/TARGET_INFO.json` |
| **Output** | `outputs/04_PARTIAL_*.json` |
| **Model** | Sonnet |

Filters false positives from Phase 03 findings via a recall-safe 3-gate pipeline with early exit. **Only these 3 gates may produce DISPUTED_FP** — no other reasoning may dispute a finding:

1. **Gate 1 (Dead Code):** Grep for callers — zero non-test callers → DISPUTED_FP. Public/exported API exception: passes gate regardless of internal caller count. Skipped for "missing validation" findings.
2. **Gate 2 (Trust Boundary):** Look up the attack path's data source in `trust_assumptions` from BUG_BOUNTY_SCOPE.json — if trust level is TRUSTED/SEMI_TRUSTED and no untrusted path also reaches the code → DISPUTED_FP. No code analysis; purely a lookup.
3. **Gate 3 (Scope Check):** Check `out_of_scope`, `conditional_scope`, and `in_scope.scope_restriction` in BUG_BOUNTY_SCOPE.json — finding falls under an excluded category → DISPUTED_FP.

Items that pass all gates undergo severity calibration against `severity_classification` thresholds (with optional network-share-based severity cap from `deployment_context.client_diversity`). Non-findings (not-a-vulnerability, out-of-scope, informational) early-exit as PASS_THROUGH. Verdicts: CONFIRMED_VULNERABILITY, CONFIRMED_POTENTIAL, DISPUTED_FP, DOWNGRADED, NEEDS_MANUAL_REVIEW, PASS_THROUGH.

<details>
<summary>Output example — CONFIRMED_VULNERABILITY</summary>

```json
{
  "reviewed_items": [
    {
      "property_id": "PROP-6a4369e9-pre-009",
      "review_verdict": "CONFIRMED_VULNERABILITY",
      "original_classification": "vulnerability",
      "adjusted_severity": "Medium",
      "reviewer_notes": "Spec requires: 'data_column_sidecars_by_root must reject requests exceeding MAX_REQUEST_DATA_COLUMN_SIDECARS'. Code reading verified: codec.rs:562-570 validates number of identifiers <=128, each identifier can have <=128 columns, enabling 128x128=16384 total columns. Handler rpc_methods.rs:408-460 lacks total column validation. Severity calibrated to Medium per BUG_BOUNTY_SCOPE.json: client market share <5%.",
      "spec_reference": "01e property PROP-6a4369e9-pre-009: 'data_column_sidecars_by_root must reject requests exceeding MAX_REQUEST_DATA_COLUMN_SIDECARS'"
    }
  ],
  "metadata": { "phase": "04", "worker_id": 1, "batch_index": 2, "item_count": 1, "timestamp": 1771818928, "processed_ids": ["PROP-6a4369e9-pre-009"] }
}
```
</details>

<details>
<summary>Output example — DISPUTED_FP (Gate triggered)</summary>

```json
{
  "reviewed_items": [
    {
      "property_id": "PROP-6a4369e9-inv-010",
      "review_verdict": "DISPUTED_FP",
      "original_classification": "vulnerability",
      "adjusted_severity": "Informational",
      "reviewer_notes": "Phase 03 misunderstood the validation architecture. The array length validation DOES exist and IS enforced on all paths (gossip, RPC, and database loads). The claim of 'out-of-bounds panic' is false — the length check at kzg_utils.rs:84-89 prevents any indexing operation.",
      "spec_reference": "01e property: 'Column, kzg_commitments, and kzg_proofs arrays must all have equal length.' Code enforces this on all paths via kzg_utils.rs:84-89."
    }
  ]
}
```
</details>

<details>
<summary>Output example — DOWNGRADED (severity cap)</summary>

```json
{
  "reviewed_items": [
    {
      "property_id": "PROP-57888860-inv-006",
      "review_verdict": "CONFIRMED_POTENTIAL",
      "original_classification": "vulnerability",
      "adjusted_severity": "Low",
      "reviewer_notes": "Code reading verified: reconstruction.go:79 iterates Go map (sidecarByIndex) which has randomized iteration order, building cellsIndices without sorting before passing to RecoverCellsAndKZGProofs (line 86). Spec SG-024 explicitly requires 'assert cell_indices == sorted(cell_indices)'. Downgraded from Medium to Low: single-client bug affecting Prysm (31% CL share), below the 33% threshold for Medium severity.",
      "spec_reference": "Fulu Polynomial Commitments Sampling SG-024: INV requires cell indices unique and in ascending order"
    }
  ]
}
```
</details>

### Phase 05: PoC Generation (Manual)

| | |
|---|---|
| **Prompt** | `prompts/05_poc.md` |
| **Usage** | `/05_poc TYPE=unit VULN_ID=... OUTPUT_PATH=...` |

Generates minimal, self-verifying Proof-of-Concept tests in the project's native stack (auto-detected language and test framework). Supports unit / integration / e2e scopes. Includes a self-repair loop (up to 4 attempts) and false-positive mitigation via guard assertions.

### Phase 06: Bug-Bounty Report (Manual)

| | |
|---|---|
| **Prompt** | `prompts/06_report.md` |
| **Usage** | `/06_report VULN_ID=... REPORT_TYPE=ETHEREUM` |

Generates a platform-tailored Markdown bug-bounty report (CANTINA, CODE4RENA, ETHEREUM, IMMUNEFI, SHERLOCK). Fills template placeholders with sanitized data, embeds PoC code with run commands, and derives severity from bounty guidelines when not specified.

### Phase 06b: Full Audit Report (Manual)

| | |
|---|---|
| **Prompt** | `prompts/06b_audit_report.md` |
| **Usage** | `/07_audit_report OUTPUT_PATH=outputs/AUDIT_REPORT.md` |

Compiles a publication-ready security assessment report covering all findings. Includes: Cover Page, Executive Summary, Scope, System Overview, Methodology, Specification Traceability, Finding Classification, Findings Summary, Detailed Findings, Re-Verification, Operational Recommendations, and Appendix. All internal IDs are sanitized to sequential labels (e.g., Finding-01, Gap-02).

## Running on GitHub Actions

All pipeline phases are executed via **GitHub Actions workflows** with `workflow_dispatch` triggers:

| Workflow | File | Description |
|---|---|---|
| 01a. Discovery | `01a-discovery.yml` | Crawl specification URLs |
| 01b. Subgraph Extraction | `01b-subgraph.yml` | Extract program graphs |
| 01e. Properties | `01e-properties.yml` | Trust model + property generation |
| 02c. Code Resolution | `02c-enrich-code.yml` | Pre-resolve code locations |
| 03. Audit Map | `03-audit-map.yml` | Proof-based 3-phase formal audit |
| 04. Audit Review | `04-audit-review.yml` | 3-gate FP filter + severity calibration |

Each workflow:
1. Checks out the repository and syncs the latest `scripts/`, `prompts/`, `.claude/` from the base branch.
2. Installs Claude Code CLI and registers MCP servers via `scripts/setup_mcp.sh`.
3. Runs the orchestrator: `uv run python3 scripts/run_phase.py --phase <ID> --workers N`.
4. Commits results to an audit branch and uploads logs as artifacts.

For local execution, see [Quick Start](#quick-start) above.

### MCP Servers

The following MCP servers are registered by `scripts/setup_mcp.sh`:

| Server | Command | Used In |
|---|---|---|
| `tree_sitter` | `uvx mcp-server-tree-sitter` | 02c |
| `filesystem` | `npx -y @modelcontextprotocol/server-filesystem` | 01b, 02c |
| `fetch` | `uvx mcp-server-fetch` | 01a |

Note: Phases 01e, 03, and 04 use inlined prompts with no MCP servers (only built-in Read/Write/Grep/Glob tools).

## Configuration

SPECA expects two JSON files in `outputs/` before running the audit phases:

### `outputs/BUG_BOUNTY_SCOPE.json` — *required by Phase 01e and Phase 04*

Defines the trust model and severity rubric for the target. Phase 01e aborts (`sys.exit(1)`) if it is missing. Minimal shape:

```json
{
  "in_scope":   { "components": ["..."], "scope_restriction": "..." },
  "out_of_scope": ["..."],
  "conditional_scope": ["..."],
  "trust_assumptions": {
    "p2p_input":      { "trust_level": "UNTRUSTED",   "rationale": "..." },
    "consensus_state":{ "trust_level": "TRUSTED",     "rationale": "..." },
    "rpc_input":      { "trust_level": "SEMI_TRUSTED","rationale": "..." }
  },
  "severity_classification": {
    "CRITICAL": "Loss of funds / consensus split / mass DoS",
    "HIGH":     "...",
    "MEDIUM":   "...",
    "LOW":      "..."
  },
  "deployment_context": {
    "type": "multi-implementation",
    "target_share": { "value": 0.31, "metric": "validator-share" }
  }
}
```

`deployment_context.target_share.value` ∈ [0, 1] is used by Phase 04 as an optional severity cap (e.g. a single-client bug below a 33% network-share threshold gets downgraded).

### `outputs/TARGET_INFO.json` — *required by Phase 02c / 03 / 04*

Pins the target repository and commit. Phase 03 will `git clone` to this exact ref:

```json
{
  "name":   "go-ethereum",
  "repo":   "https://github.com/ethereum/go-ethereum",
  "commit": "abc1234deadbeef...",
  "language": "go"
}
```

### Environment Variables

| Variable | Used By | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | All phases | Claude Code authentication |
| `SPEC_URLS` | 01a | Comma-separated seed URLs to crawl |
| `KEYWORDS` | 01a | Optional crawl keyword filter |
| `FORCE_EXECUTE=1` | All phases | Bypass resume state (set automatically by `--force`) |
| `CLAUDE_CODE_PERMISSIONS=bypassPermissions` | CI | Skip interactive permission prompts |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS=100000` | CI | Raise output cap for long audit traces |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | Optional | Used by GitHub MCP server when enabled |

## Evaluation

SPECA is evaluated on two complementary benchmarks. **RQ1** measures effectiveness on a large multi-implementation security contest with 366 professional auditors; **RQ2** compares SPECA against published code-driven baselines on an established C/C++ benchmark.

> All numbers below are taken verbatim from the paper ([arXiv:2604.26495](https://arxiv.org/abs/2604.26495)). Charts are reproducible via the scripts under [`benchmarks/`](./benchmarks/README.md); raw artifacts (logs, per-finding labels, model outputs) ship with this repository.

### RQ1 — Sherlock Ethereum Fusaka Audit Contest

**Benchmark.** 10 production Ethereum client implementations of EIP-7594 (PeerDAS) and EIP-7691, spanning **5 programming languages** (Go, Rust, Nim, TypeScript, C). 366 submissions from professional auditors; 15 judged valid at H/M/L severity (5 High, 2 Medium, 8 Low).

**Headline detection numbers (post-Phase 6, N=72):**

| Metric | Value |
|---|---|
| Phase 5 findings (pre-review) | 102 |
| Phase 6 findings (post-review) | 72 |
| **H/M/L recovered (expert-augmented)** | **15 / 15 (100%)** |
| H/M/L recovered (automated-only) | 8 / 15 (53%) |
| **Novel bugs confirmed by fix commits** | **4** |
| Confirmed FPs (post-review) | 24 (33.3%) |
| Strict precision (H/M/L match) | 26.4% (19/72) |
| Confirmed-useful precision | 59.7% (43/72) |
| Broad precision (non-FP rate) | 66.7% (48/72) |

**Phase 6 lifts precision while preserving recall.** The severity-preserving review filter raises broad precision from **56.9% → 66.7%** while preserving 100% recall on H/M/L true positives, raising **F1 from 72.5% → 80.0%**:

<p align="center">
  <img src="benchmarks/results/rq1/sherlock_ethereum_audit_contest/chart_phase_comparison.png" alt="Phase 5 vs Phase 6" width="600" />
</p>

**Property neighborhoods drive recall.** Many issues are recovered not by a single alert but by multiple complementary properties. Cluster-level strict precision (grouping all findings against the same issue into one cluster) is **48.7%** (vs. 26.4% finding-level), confirming genuine redundancy rather than alert duplication.

<p align="center">
  <img src="benchmarks/results/rq1/sherlock_ethereum_audit_contest/chart_findings_per_issue.png" alt="Findings per issue" width="600" />
</p>

The Sankey diagram below makes the same neighborhood structure visible from the property side: the horizontal density around a handful of issues shows which property families converge on the same root cause.

<p align="center">
  <img src="benchmarks/results/rq1/sherlock_ethereum_audit_contest/chart_sankey_flow.png" alt="Property family → ground-truth issue Sankey flow" width="700" />
</p>

**Per-repository finding distribution** across the 10 implementations (Phase 5 vs Phase 6):

<p align="center">
  <img src="benchmarks/results/rq1/sherlock_ethereum_audit_contest/chart_per_repo.png" alt="Per-repository findings" width="700" />
</p>

**4 novel bugs absent from all 366 contest submissions, confirmed by developer fix commits:**

| # | Target | Bug | Fix |
|---|---|---|---|
| A | **c-kzg-4844** | KZG batch-verification challenge hash uses the original commitment array rather than the deduplicated array — selective forgery against batch verify | `f18ba082` |
| B | **Lodestar** | Inverted logic + missing validation on column sidecar cache | `3b98c59c` |
| C | **Nimbus** | Unchecked array access reachable from RPC and Engine API | `b3a3f3f9` |
| D | **Prysm** | Wrong subnet parameter computation + missing cell-count validation | `b5bdd65f` |

> **Bug A** is particularly significant: a cryptographic correctness bug in a core library used by multiple Ethereum clients. It is a violation of an invariant that the specification defines but no code-level auditing tool was designed to check.

**Recovered Sherlock H/M/L issues** (representative subset):

| Severity | Target | Issue | Sherlock # |
|---|---|---|---|
| HIGH | Prysm | Inclusion proof cache key omits `KzgCommitments` → cache poisoning bypasses Merkle verification | #190 |
| HIGH | Nethermind | Mismatched loop bounds between `BlobVersionedHashes` and `wrapper.Blobs` → extra hashes bypass commitment validation | #210 |
| HIGH | c-kzg-4844 | Fiat-Shamir challenge hash uses original array instead of deduplicated commitments → selective forgery | #203 |
| HIGH | Lighthouse | `get_beacon_proposer_indices` recomputes from active validators instead of reading `proposer_lookahead` → consensus split | #40 |
| MEDIUM | Nimbus | `handle_custody_groups` loop terminates only when `HashSet.size == custody_group_count` → infinite-loop DoS via P2P metadata | #15 |
| MEDIUM | Nimbus | 30-minute metadata refresh timer with no fork-aware acceleration → stale `custody_group_count=0` blocks data-column sync | #216 |
| LOW | Grandine | `verify_kzg_proofs` returns `Ok(false)` but boolean is discarded by `.map_err()?` → invalid KZG proofs accepted | #376 |
| LOW | Grandine | `get_blob_schedule_entry` assumes descending order but named-network constructors define ascending → wrong epoch match causes chain split | #319 |
| LOW | Lodestar | Cache key `(blockRootHex, index)` excludes signature → attacker rebroadcasts invalid-signature sidecars via cache hit | #381 |
| LOW | Reth/alloy-evm | `next_block_excess_blob_gas_osaka()` receives child's base fee instead of parent's → invalid block proposals | #371 |

**Phase 6 three-gate filter effectiveness** (N=30 `DISPUTED_FP`):

<p align="center">
  <img src="benchmarks/results/rq1/sherlock_ethereum_audit_contest/chart_gate_effectiveness.png" alt="Gate effectiveness" width="600" />
</p>

The current 3-gate design was **simplified from a 5-gate prototype** after empirical analysis showed two of the original gates (Spec Cross-Reference and Exploitability) filtered informational true positives at **0% precision**, providing no net benefit.

#### Structured False-Positive Analysis

A defining capability of SPECA: every false positive decomposes into a **traceable root cause**. Of 16 deeply analyzed FPs (drawn from a population of 44 total):

| Root Cause | Phase Origin | N | % |
|---|---|---|---|
| Trust boundary misunderstanding | Phase 3 (Property Generation) | 8 | 50.0% |
| Code reading error | Phase 5 (Audit) | 6 | 37.5% |
| Specification misinterpretation | Phase 3 | 2 | 12.5% |

<p align="center">
  <img src="benchmarks/results/rq1/sherlock_ethereum_audit_contest/chart_fp_taxonomy.png" alt="FP taxonomy" width="600" />
</p>

Each root cause maps to a **concrete, implementable improvement target**: explicit trust-boundary configuration, richer code-reading context, and enforced spec-section re-reading before classification. This is the property-centered representation's payoff: failures are diagnosable.

#### Property-Type Ablation

Which parts of the property vocabulary actually drive detection?

| Property Type | N | TP | FP | Precision |
|---|---|---|---|---|
| Invariant | 67 | 18 | 6 | **75.0%** |
| Precondition | 11 | 4 | 0 | **100.0%** |
| Postcondition | 5 | 1 | 1 | 50.0% |
| Assumption | 5 | 0 | 1 | **0.0%** |

<p align="center">
  <img src="benchmarks/results/rq1/sherlock_ethereum_audit_contest/chart_property_type_ablation.png" alt="Property type ablation" width="600" />
</p>

Invariants account for 76% of findings at 75% precision and dominate detection today. Assumption-type properties are too noisy for reliable auditing and are best treated as an exploratory mode. **Postcondition and assumption generation are the concrete research frontiers** for the automated-only configuration.

#### Automated-Only vs. Expert-Augmented

| Configuration | Properties | H/M/L | Coverage |
|---|---|---|---|
| Automated-only | Auto-generated (Phases 1–3) | 8 / 15 | 53% |
| **Expert-augmented** | Auto + 7 manual properties | **15 / 15** | **100%** |

The 7 manual properties cluster in two domain-specific areas — **cryptographic invariants** (KZG polynomial commitment edge cases, BLS12-381 identity element handling) and **protocol-lifecycle rules** (custody group bounds, cache key completeness, fork-transition metadata refresh) — that require mathematical domain knowledge or multi-specification cross-referencing not yet reliably automated. They are authored once per spec corpus and **reused across all 10 implementations**, so expert-knowledge injection has high amortized leverage in multi-implementation settings.

### RQ2 — RepoAudit C/C++ Benchmark

**Benchmark.** 15 open-source C/C++ projects with 35 non-disputed ground-truth bugs (null-pointer dereferences, memory leaks, use-after-free) confirmed by developer fixes, plus 5 disputed bugs. Comparison: published RepoAudit baselines (4 model configurations) plus Meta Infer and Amazon CodeGuru.

| Method | TP | FP | Precision | New cand. | Cost |
|---|---|---|---|---|---|
| _Partially controlled (DeepSeek R1)_ | | | | | |
| RepoAudit (DeepSeek R1) | 41 | 6 | 87.2% | (in TP) | $8.55 |
| **SPECA (DeepSeek R1)** | — | 15 | 72.7% | **7** | $93.51 |
| _Latest models_ | | | | | |
| RepoAudit (Claude 3.7 Sonnet) | 40 | 5 | 88.9% | (in TP) | $23.85 |
| **SPECA (Sonnet 4.5)** | — | 6 | **88.9%** | **12** | $81.05 |
| _Other configurations_ | | | | | |
| Amazon CodeGuru | 0 | 18 | 0.0% | 0 | — |
| Meta Infer | 7 | 2 | 77.8% | 0 | free |
| RepoAudit (o3-mini) | 36 | 9 | 80.0% | (in TP) | $4.50 |
| RepoAudit (Claude 3.5 Sonnet) | 40 | 11 | 78.4% | (in TP) | $38.10 |
| **SPECA (Sonnet 4)** | — | 13 | 81.2% | **18** | $100.68 |

> **New cand.** = author-validated candidate bugs *beyond* the established ground truth. Recall is not reported because the GT was constructed from RepoAudit's own discoveries (structurally unfair to compare).

<p align="center">
  <img src="benchmarks/results/rq2a/figures/rq2a_precision_comparison.png" alt="Precision comparison" width="600" />
</p>

<p align="center">
  <img src="benchmarks/results/rq2a/figures/rq2a_tp_fp_comparison.png" alt="TP vs FP" width="600" />
</p>

**SPECA (Sonnet 4.5) matches the best published baseline precision (88.9%)** while uniquely surfacing 12 author-validated beyond-GT candidates. Two of those candidates are externally validated:

- **`PROP-N3-npd-001` (coturn, NPD)** — confirmed at **Level A** (bug existed in the analyzed commit, independently fixed in a later release; PR #1841 self-withdrawn after discovering the fix).
- **`PROP-U5-uaf-002` (ICU/i18n, UAF race condition)** — confirmed at **Level B** (ICU maintainer approved the corresponding Jira ticket; PR #3921).

**Cost vs. detection performance:**

<p align="center">
  <img src="benchmarks/results/rq2a/figures/rq2a_cost_efficiency.png" alt="Cost vs precision" width="600" />
</p>

At the Sonnet 4.5 configuration, SPECA achieves the highest precision while uniquely reporting double-digit beyond-GT candidates at a per-bug cost (~**$1.69/bug**) competitive with the best published baseline.

**Symmetric cross-backbone comparison** (same-backbone DeepSeek R1 left, latest-models right):

<p align="center">
  <img src="benchmarks/results/rq2a/figures/rq2a_symmetric_comparison.png" alt="Symmetric comparison" width="700" />
</p>

#### The Property Adherence Effect

An instructive non-monotonic pattern: Sonnet 4 discovers **18** beyond-GT candidates, Sonnet 4.5 discovers **12**, DeepSeek R1 discovers **7**. This is *not* a simple precision–discovery tradeoff — it reflects **increasing property adherence**. More capable models audit more faithfully against the stated property, checking exactly what the specification-derived property asserts and no more. Less capable models drift from the property scope during the proof-attempt phase, producing some genuine bugs (beyond-GT) and some false positives.

> Engineering implication: **as models improve, property generation (Phases 1–3) becomes the binding constraint on detection coverage.** The model audits precisely what the properties tell it to audit; comprehensive property derivation is the primary lever for improving recall.

### Cost & Throughput

- **RQ1 (Sherlock):** ≈ $400–620 total API cost (10 implementations).
- **RQ2 (RepoAudit, Sonnet 4.5):** $81.05 total = **$1.69 / bug**.
- Phases 1–3 use Claude **Opus** (specification understanding); Phases 4–6 use Claude **Sonnet** (code analysis & review).

## Reproducing the Benchmarks

All evaluation scripts, per-repository outputs, and labeling artifacts ship with the repo:

- [`benchmarks/results/rq1/sherlock_ethereum_audit_contest/`](./benchmarks/results/rq1/sherlock_ethereum_audit_contest/) — RQ1 raw outputs, labels, and chart-generation scripts.
- [`benchmarks/results/rq2a/`](./benchmarks/results/rq2a/) — RQ2 RepoAudit outputs and figures.
- [`benchmarks/README.md`](./benchmarks/README.md) — full reproduction instructions.

## Contributing

We welcome issues and pull requests from the community.

- **Bugs / feature requests:** open a [GitHub issue](https://github.com/NyxFoundation/speca/issues) with a minimal reproducer or a concrete use-case.
- **Pull requests:**
  1. Fork the repo and create a topic branch off `master`.
  2. Run the test suite: `uv run python3 -m pytest tests/ -v --tb=short`.
  3. Keep changes focused — pipeline phases are deliberately decoupled, so a PR should usually touch one phase at a time.
  4. Open the PR with a brief description of *what* changed and *why*. If the change affects an inter-phase data contract, update `scripts/orchestrator/schemas.py` and the relevant prompt under `prompts/` together.
- **New target domains:** SPECA is domain-agnostic by design. To onboard a new target, you typically only need to write a `BUG_BOUNTY_SCOPE.json` and a `TARGET_INFO.json` — no code change required.

## Citation

If you use SPECA in academic work, please cite the accompanying paper:

```bibtex
@misc{kamba2026speca,
  title         = {Beyond Code Reasoning: A Specification-Anchored Audit Framework for Expert-Augmented Security Verification},
  author        = {Kamba, Masato and Murakami, Hirotake and Sannai, Akiyoshi},
  year          = {2026},
  eprint        = {2604.26495},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CR},
  url           = {https://arxiv.org/abs/2604.26495}
}
```

## License

SPECA is released under the [MIT License](LICENSE). See the `LICENSE` file for full terms.

> **Disclaimer.** SPECA is a research artifact. Findings produced by the pipeline are *candidate* vulnerabilities and **must** be validated by a human auditor before being reported to a vendor or bug-bounty program. The maintainers make no warranty as to the completeness or correctness of any audit produced by this software.
