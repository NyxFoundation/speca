# Orchestrator Execution Flow - Complete Analysis

## File Locations
- Entry: `/home/gohan/workspace/security-agent/scripts/run_phase.py` (186 lines)
- Base Orchestrator: `/home/gohan/workspace/security-agent/scripts/orchestrator/base.py` (495 lines)
- Collector: `/home/gohan/workspace/security-agent/scripts/orchestrator/collector.py` (52 lines)
- Runner: `/home/gohan/workspace/security-agent/scripts/orchestrator/runner.py` (331 lines)
- Config: `/home/gohan/workspace/security-agent/scripts/orchestrator/config.py` (215 lines)
- Makefile: `/home/gohan/workspace/security-agent/Makefile` (308 lines)

## Main Execution Flow

### 1. Entry Point (run_phase.py)
- `main()` parses args: --phase, --target, --resume-from, --workers
- `run_phases()` calls `run_phase()` for each phase sequentially
- `run_phase()` creates orchestrator via `create_orchestrator()` and calls `await orchestrator.run()`
- **CRITICAL: NO output checking here - all skip logic is in Makefile!**

### 2. Orchestrator.run() (base.py lines 71-123)
```
1. load_items() - Load from input sources
2. apply_early_exit() - Filter early exit items vs items to process
3. enrich_items() - Add context (phase-specific)
4. create_batches() - Batch items (token or count strategy)
5. execute_batches() - Run batches in parallel
6. Report failures - Exit(1) if any batch failed
```

### 3. Batch Execution (base.py lines 161-200)
- Creates async tasks for each batch
- Calls `runner.run_batch(batch, worker_id, batch_index)`
- Tracks `results[]` and `failed_batches[]`
- For each successful batch: calls `collector.save_partial()`

### 4. Result Parsing (runner.py)
- Primary: Parse from output file `{phase}_PARTIAL_W{w}B{b}_{ts}.json`
- Fallback: Parse from log file (extract ```json blocks)
- Returns `list[dict]` or `None` on failure

### 5. Partial Saving (collector.py lines 28-51)
- Filename: `{phase_id}_PARTIAL_W{worker_id}B{batch_index}_{timestamp}.json`
- Metadata: phase, worker_id, batch_index, item_count, timestamp
- Stored under config.result_key (e.g., "audit_items")

## Resume Mechanism Gaps

### No Item Tracking
- Partials don't record which input items they contain
- No mapping of item_id → partial_file
- No registry of processed items

### No Deduplication
- Resuming re-processes all items
- Creates new partials with new timestamps
- Downstream phases de-dup by item ID during load, so overlaps cause last-wins behavior

### Current Skip Logic (Makefile)
- `if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/{pattern}.json >/dev/null 2>&1; then SKIP`
- Defensive: prevents re-running entire phase
- But assumes all items in phase were processed (fails with partial failures)

## Design for Resume Mechanism

### Need to Track
1. Input items used in each batch
2. Status of each item (pending/processing/completed/failed)
3. Batch-to-items mapping for recovery

### Implementation Options
1. **Extend Partial Metadata**: Store input item IDs in partial metadata
2. **Item Registry**: Keep separate file tracking processed item IDs
3. **Batch State**: Store batch state (pending/running/completed) before execution
4. **Idempotent Processing**: Hash-based dedup in downstream phases

### Backward Compatibility
- Current system writes partials immediately
- Can add optional tracking without breaking existing flow
- Config option: enable/disable resume tracking

## Key Data Structures

### PhaseConfig Fields (config.py)
- `item_id_field`: Field identifying items (e.g., "check_id")
- `batch_strategy`: "token" or "count"
- `result_key`: Key for results in output (e.g., "audit_items")
- `output_prefix`: Semantic name for partials (e.g., "AUDITMAP")

### Save Partial (collector.py)
```python
{
  "result_key": [results],
  "metadata": {
    "phase": "03",
    "worker_id": 1,
    "batch_index": 5,
    "item_count": 25,
    "timestamp": 1707000000
  }
}
```

### Failed Batch Tracking (base.py)
- Stored as `list[tuple[worker_id, batch_index]]`
- Checked at end: if non-empty, exit(1)
- Note: Results already saved via save_partial before failure check

## Batching Strategy

### Token-Based (TokenBasedBatch)
- Respects context token limits
- Packs items until reaching max_context_tokens
- Default: 190,000 tokens max, 5,000 base overhead

### Count-Based (CountBasedBatch)
- Simple count: max N items per batch
- Phase 03 uses count=25 items/batch

## Retry Logic (runner.py)

- Default max_retries: 2
- On failure: print error, sleep exponential backoff
- Returns None if all retries exhausted
