import json
import asyncio
from pathlib import Path

import pytest

from scripts.orchestrator.watchdog import (
    CostTracker,
    BudgetExceeded,
    extract_token_usage_from_log,
)


def test_extract_token_usage_with_cache_fields(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    # Two messages with different IDs — both contribute via sum
    lines = [
        {"type": "assistant", "message": {"id": "msg_01", "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 50,
        }}},
        {"type": "assistant", "message": {"id": "msg_02", "usage": {
            "input_tokens": 20,
            "output_tokens": 7,
            "cache_read_input_tokens": 150,
            "cache_creation_input_tokens": 25,
        }}},
    ]
    log.write_text("\n".join(json.dumps(l) for l in lines))

    usage = extract_token_usage_from_log(log)
    # All fields summed across 2 unique messages
    assert usage["input_tokens"] == 30       # 10 + 20
    assert usage["cache_read_tokens"] == 250  # 100 + 150
    assert usage["cache_creation_tokens"] == 75  # 50 + 25
    assert usage["output_tokens"] == 12       # 5 + 7
    # BUG-ORC15: turns = messages // 2 (a turn is a request-response pair)
    assert usage["num_turns"] == 1


def test_extract_token_usage_dedup_same_message(tmp_path: Path):
    """Duplicate events for the same message ID should be deduped (max per field)."""
    log = tmp_path / "log.jsonl"
    lines = [
        # Two events for msg_01 (same values, typical of Claude CLI stream-json)
        {"type": "assistant", "message": {"id": "msg_01", "usage": {
            "input_tokens": 5,
            "output_tokens": 1,
            "cache_read_input_tokens": 4000,
            "cache_creation_input_tokens": 1000,
        }}},
        {"type": "assistant", "message": {"id": "msg_01", "usage": {
            "input_tokens": 5,
            "output_tokens": 1,
            "cache_read_input_tokens": 4000,
            "cache_creation_input_tokens": 1000,
        }}},
    ]
    log.write_text("\n".join(json.dumps(l) for l in lines))

    usage = extract_token_usage_from_log(log)
    # Only 1 unique message — deduped via max
    assert usage["input_tokens"] == 5
    assert usage["cache_read_tokens"] == 4000
    assert usage["cache_creation_tokens"] == 1000
    assert usage["output_tokens"] == 1
    assert usage["num_turns"] == 1


def test_cost_tracker_accumulates_cache_tokens():
    tracker = CostTracker(
        max_budget_usd=100.0,
        input_price_per_million=1.0,
        output_price_per_million=2.0,
        cache_read_multiplier=0.1,
        cache_creation_multiplier=1.25,
    )
    # 1M tokens each to make cost math easy
    asyncio.run(
        tracker.record_usage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_read_tokens=1_000_000,
            cache_creation_tokens=1_000_000,
        )
    )
    stats = tracker.get_stats()
    # totals
    assert stats["total_input_tokens"] == 1_000_000
    assert stats["total_output_tokens"] == 1_000_000
    assert stats["total_cache_read_tokens"] == 1_000_000
    assert stats["total_cache_creation_tokens"] == 1_000_000
    # cost: input 1.0 + cache_read 0.1 + cache_create 1.25 + output 2.0 = 4.35
    assert pytest.approx(stats["total_cost_usd"], rel=1e-3) == 4.35


def test_cost_tracker_budget_exceeded_with_cache_tokens():
    tracker = CostTracker(max_budget_usd=0.5)  # small budget
    with pytest.raises(BudgetExceeded):
        asyncio.run(
            tracker.record_usage(
                input_tokens=0,
                output_tokens=100_000,  # default output price 15$/M -> $1.5
                cache_read_tokens=0,
                cache_creation_tokens=0,
            )
        )
