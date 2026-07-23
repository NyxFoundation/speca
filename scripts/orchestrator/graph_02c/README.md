# Graph-based deterministic 02c (speca#157)

An LLM-free, deterministic replacement for Phase 02c's per-property code-location
resolution — cheaper and reproducible, so the 3-model MoA audit (02c→04) can run
without the Claude/MCP dependency.

## How it works (tiered, recall-first)
1. **Symbol index** (`symbols.py`) — Tree-sitter parses the client tree once
   (all 6 client languages) into a `name → file:line` index. Deterministic.
2. **Resolver** (`resolver.py`) — a property resolves to a `code_scope` by rule:
   seeds from `covers` / `spec_symbol` / mined tokens, matched
   convention-insensitively (`norm()` collapses pyspec `process_attestation`
   onto client `ProcessAttestation` / `processAttestation`). Emits a
   **confidence** (high / medium / low).
3. **Confidence gate** (`run.py`) — **high accepted directly** (exact strong-seed
   hit — precise); **medium + low → `needs_llm_fallback`** (never dropped). So the
   LLM runs on only the tail, and system recall ≥ the pure-LLM baseline *by
   construction*. High-only is the default because medium (mined-token) matches
   validated imprecise on real clients whose function structure differs from
   pyspec — e.g. prysm's Go `on_block` mis-matching `Fork`. Set
   `SPECA_02C_ACCEPT=high,medium` to also accept medium (cheaper, less precise).

## Accuracy is measured, not assumed
- `benchmark.py` mines ground truth from Phase 03 findings' `code_path`.
- `metric.py` scores resolution recall / precision / fallback rate.
- `eval_cli.py` runs the gate over `fixtures/bench_repo` and **exits non-zero**
  below `--recall-min` / above `--fallback-max`; wired into CI
  (`.github/workflows/graph-02c-eval.yml`). Validated on real nethermind C#
  (recall 1.0 with the exact seed).
- **Real-client validation** (gasper 01e, 20 properties): lighthouse (Rust, 895
  files) → 16 high / 4 medium, 20/20 located, ~3.1s, 0 LLM; prysm (Go camelCase,
  3586 files) → 10 high / 10 medium. Under the high-only default the imprecise
  medium tail (e.g. `on_block`→`Fork`) drops to the LLM, keeping the
  deterministic tier precise.

## Run
```bash
uv run --with tree-sitter --with tree-sitter-language-pack --with tree-sitter-c-sharp \
  PYTHONPATH=scripts python3 -m orchestrator.graph_02c.eval_cli          # accuracy gate
PYTHONPATH=scripts python -m orchestrator.graph_02c.run --repo <client> --01e <01e_PARTIAL.json>  # produce 02c
```

## Status
resolver + driver + accuracy gate + **02c phase integration** all done and in
CI. Enable with `run_phase.py --code-resolution graph` (or
`SPECA_02C_RESOLUTION=graph`): Phase02cOrchestrator resolves deterministically
over `SPECA_TARGET_WORKSPACE` and runs the LLM only on the low-confidence tail.
Verified end-to-end (schema-valid 02c_PARTIAL, 0 LLM calls when all resolve).
Install the grammars with the `graph-02c` extra (`pip install -e .[graph-02c]`).
