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
3. **Confidence gate** (`run.py`) — high/medium accepted directly; **low →
   `needs_llm_fallback`** (never dropped). So the LLM runs on only the tail, and
   system recall ≥ the pure-LLM baseline *by construction*.

## Accuracy is measured, not assumed
- `benchmark.py` mines ground truth from Phase 03 findings' `code_path`.
- `metric.py` scores resolution recall / precision / fallback rate.
- `eval_cli.py` runs the gate over `fixtures/bench_repo` and **exits non-zero**
  below `--recall-min` / above `--fallback-max`; wired into CI
  (`.github/workflows/graph-02c-eval.yml`). Validated on real nethermind C#
  (recall 1.0 with the exact seed).

## Run
```bash
uv run --with tree-sitter --with tree-sitter-language-pack --with tree-sitter-c-sharp \
  python3 -m experiments.graph_02c.eval_cli          # accuracy gate
python -m experiments.graph_02c.run --repo <client> --01e <01e_PARTIAL.json>  # produce 02c
```

## Status / next
resolver + driver + gate done. **Not yet wired into the 02c phase orchestrator**
— that integration lands as a reviewed PR (a deterministic 02c path + LLM tail),
not autonomous commits.
