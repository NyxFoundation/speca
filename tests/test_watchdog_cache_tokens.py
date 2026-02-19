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
    # first line sets small usage; second line should override input/cache_read via max
    lines = [
        {"type": "assistant", "message": {"usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 50,
        }}},
        {"usage": {
            "input_tokens": 20,
            "output_tokens": 7,
            "cache_read_input_tokens": 150,
            "cache_creation_input_tokens": 25,
        }},
    ]
    log.write_text("\n".join(json.dumps(l) for l in lines))

    usage = extract_token_usage_from_log(log)
    # input and cache_* take max, output is cumulative sum
    assert usage["input_tokens"] == 20
    assert usage["cache_read_tokens"] == 150
    assert usage["cache_creation_tokens"] == 50  # max(50,25)
    assert usage["output_tokens"] == 12  # 5 + 7


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
