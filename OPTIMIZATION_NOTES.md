# Phase 03 Optimization Notes

## Overview

This document describes the optimizations implemented to reduce token consumption in Phase 03 (Audit Map Generation).

## Implemented Optimizations

### 1. Early Termination Logic (High Priority)

**Location**: `.claude/skills/formal-audit-unified/SKILL.md`

**Description**: Added early exit checks at each phase to skip unnecessary analysis for trivially safe or verified safe code.

**Implementation**:
- **Phase 1**: If code is trivially safe (e.g., simple getter, constant return, no external input), mark as `trivially_safe=true` and skip to Phase 3 with minimal analysis
- **Phase 2**: Skip entirely if `trivially_safe=true`. If no counterexample found and code has strong guards, mark as `verified_safe=true`
- **Phase 3**: Use simplified analysis for `trivially_safe` or `verified_safe` cases

**Expected Impact**:
- **Token reduction**: 30-50% for simple/safe code paths
- **Time savings**: Proportional to token reduction
- **Accuracy**: Maintained through conservative classification

### 2. Cache Strategy Optimization (High Priority)

**Location**: `prompts/03_auditmap_worker_optimized.md`

**Description**: Added explicit cache optimization guidelines to maximize Claude API's prompt caching effectiveness.

**Implementation**:
- **Reuse context**: Keep common context (skill definitions, checklist schema) in the same conversation
- **Batch similar items**: Process items from the same file/component together to maximize cache hits
- **Minimal context**: Only include necessary information in each skill invocation
- **Cache-friendly invocation**: Pass only essential context to skills

**Expected Impact**:
- **Cache hit rate**: Increase from ~50% to ~80%
- **Token reduction**: 20-30% through better cache utilization
- **Cost savings**: Proportional to cache hit improvement

### 3. Code Resolution Pre-execution (Medium Priority)

**Location**: 
- `prompts/02c_worker.md` - Phase 02c worker prompt
- `.github/workflows/02c-enrich-code.yml` - Phase 02c GitHub Workflow
- `scripts/orchestrator/schemas.py` - CodeScope type definition
- `scripts/orchestrator/config.py` - Phase 02c configuration
- `prompts/03_auditmap_worker_optimized.md` - Phase 03 checks pre-resolved code

**Description**: Phase 02c pre-resolves code locations for checklist items before Phase 03. This is now a formal phase in the pipeline, not an optional step.

**Implementation**:
- **Type-safe schema**: Added `CodeScope` model with `resolution_status` field
- **Orchestrated phase**: Phase 02c runs via `scripts/run_phase.py --phase 02c`
- **Target consistency**: Phase 02c creates branch with `TARGET_INFO.json`, Phase 03 auto-clones same target
- **Batch optimization**: Resolves code locations in parallel batches (100 items per batch)
- **MCP-based**: Uses Tree-sitter MCP for symbolic code navigation

**Expected Impact**:
- **MCP call reduction**: 70-80% (from ~1500 to ~300 calls)
- **Time savings**: 3-5 minutes per audit
- **Reliability**: Early detection of code resolution failures
- **Flexibility**: Can be skipped if not needed

## Usage

### Running the Full Pipeline

All optimizations are enabled by default. To run the full workflow:

```bash
# Step 1: Run Phase 02 (Checklist Generation)
uv run python3 scripts/run_phase.py --phase 02 --workers 4 --max-concurrent 64

# Step 2: Run Phase 02c (Code Pre-resolution)
# Via GitHub Workflow (recommended):
#   Manually trigger "02c. Code Pre-resolution" workflow
#   Inputs: target_repo, target_ref_type, audit_scope
#   Creates new branch with TARGET_INFO.json

# Or via command line (after setting up target_workspace):
uv run python3 scripts/run_phase.py --phase 02c --workers 4 --max-concurrent 64

# Step 3: Run Phase 03 (Audit Map Generation)
# Via GitHub Workflow (recommended):
#   Manually trigger "03. Audit Map" workflow
#   Input: branch (from Phase 02c)
#   Auto-reads TARGET_INFO.json and clones same target

# Or via command line:
uv run python3 scripts/run_phase.py --phase 03 --workers 4 --max-concurrent 64
```

## Performance Metrics

### Before Optimization

- **Tokens per item**: ~27,000 (effective input) + ~245,000 (cache read) = ~272,000 total
- **API calls per item**: ~5.1
- **MCP calls**: ~1,500 for code resolution
- **Execution time**: 20+ minutes for 533 items (incomplete)

### After Optimization (Estimated)

- **Tokens per item**: ~6,200 (effective input) + ~56,000 (cache read) = ~62,200 total
- **Token reduction**: ~77%
- **API calls per item**: ~2-3 (with early termination)
- **MCP calls**: ~200 (with pre-resolution)
- **Execution time**: <10 minutes for 533 items (complete)

## Future Improvements

### Additional Optimizations to Consider

1. **Dynamic Concurrency Adjustment**: Automatically adjust `max_concurrent` based on token consumption rate
2. **Risk-based Prioritization**: Process high-risk items first, skip low-risk items if budget limited
3. **Incremental Analysis**: Cache analysis results across audit runs for unchanged code
4. **Simplified Output Format**: Further compress output JSON to reduce token overhead

### Monitoring and Metrics

Consider adding:
- Real-time token consumption dashboard
- Per-phase token breakdown
- Cache hit rate monitoring
- Early termination effectiveness metrics

## References

- Original Issue: [#40](https://github.com/NyxFoundation/security-agent/issues/40)
- Initial Optimization PR: [#41](https://github.com/NyxFoundation/security-agent/pull/41)
- Analysis Report: See `review_report.md` in the repository root


## Phase 02c Bug Fix (2026-02-17)

### Problem Identified

Analysis of the `preresolve_prysm_fusaka-audit_238d5c07df_20260216150647` branch revealed critical issues with Phase 02c implementation:

- **Resolution rate**: Only 17.3% (225/1,304 items) - extremely low
- **Primary error**: `No such tool available: mcp__tree_sitter__find_symbol` (14 occurrences)
- **Secondary errors**: File path issues, token limit exceeded, file operation errors

### Root Causes

1. **Incorrect MCP tool names**: Prompt specified `mcp__tree_sitter__*` but actual tool names likely required server prefix (e.g., `mcp__serena__tree_sitter__*`)
2. **Over-reliance on MCP tools**: MCP tool instability caused cascading failures
3. **Insufficient error handling**: Some errors halted processing, leaving many items unprocessed
4. **Environment path mismatches**: GitHub Actions paths (`/home/gohan/runners/...`) hardcoded in some places

### Solution: Simplified Implementation

**Replaced MCP-based implementation with built-in shell tools for reliability.**

#### Key Changes to `prompts/02c_worker.md`

| Aspect | Before (MCP-based) | After (Shell-based) |
|--------|-------------------|---------------------|
| **Code search** | `mcp__tree_sitter__find_symbol` | `grep -rn` or `rg --json` |
| **File reading** | `mcp__filesystem__read_text_file` | `file` tool (built-in) |
| **Batch processing** | Multiple MCP calls per item | Single grep for all symbols |
| **Error handling** | Fragile, errors propagate | Robust, per-item try-catch |
| **Dependencies** | MCP servers (external) | Shell tools (built-in) |

#### New Algorithm

```
1. Extract all symbols from batch → ["sym1", "sym2", "sym3", ...]
2. Build regex pattern → "(sym1|sym2|sym3)"
3. Run ONE grep command:
   rg -n '(func|type|const|var)\s+(sym1|sym2|sym3)' target_workspace/
4. Parse results → create symbol_map {sym1: {file, line}, ...}
5. For each item:
   - Lookup symbol in map (no external calls)
   - Read code excerpt using file tool
   - Handle errors gracefully, continue to next item
6. Write all results to output file
```

#### Expected Improvements

| Metric | Before | After (Expected) |
|--------|--------|------------------|
| **Resolution rate** | 17.3% | **>80%** |
| **Error rate** | 11.7% | **<5%** |
| **MCP calls** | 146 | **0** |
| **Shell commands** | Unknown | **1-5 per batch** |
| **Processing time** | Unknown | **<2 min per 100 items** |

### Backward Compatibility

- Output schema unchanged (`code_scope`, `code_excerpt` fields remain the same)
- Phase 03 requires no modifications
- Old prompt saved as `prompts/02c_worker_old.md` for reference
- Can revert via environment variable `USE_LEGACY_PHASE02C=1` if needed

### Testing Plan

1. **Unit test**: Small batch (10 items) to verify basic functionality
2. **Integration test**: 100-item batch to measure resolution rate
3. **Production test**: Full Prysm audit (1,000+ items) to validate at scale

### Next Steps

1. ✅ Prompt rewritten with shell-based implementation
2. ⏳ Push to master branch
3. ⏳ Run GitHub Actions workflow to test
4. ⏳ Verify resolution rate >80%
5. ⏳ Measure Phase 03 efficiency improvement
