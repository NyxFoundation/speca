#!/usr/bin/env python3
"""Statistical helpers shared by benchmarks."""

from __future__ import annotations

import random
from math import comb


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = 0.0
    for i in range(k + 1):
        tail += comb(n, i) * (0.5**n)
    p = 2 * tail
    return min(p, 1.0)


def effect_size_cliffs_delta(b: int, c: int, n: int) -> tuple[float, str]:
    """Compute paired proportion difference (b-c)/n with magnitude labels.

    Note: This is *not* Cliff's Delta (which uses pairwise comparisons);
    it is the difference in proportions from a paired/McNemar-style table.
    The name is kept for backward-compatibility of the call-sites.
    """
    if n == 0:
        return 0.0, "none"
    delta = (b - c) / n
    magnitude = abs(delta)
    if magnitude < 0.147:
        label = "negligible"
    elif magnitude < 0.33:
        label = "small"
    elif magnitude < 0.474:
        label = "medium"
    else:
        label = "large"
    return delta, label


def bootstrap_rate(values: list[bool], samples: int, seed: int, ci_level: float) -> dict:
    if not values:
        return {"mean": 0.0, "ci": [0.0, 0.0]}
    rng = random.Random(seed)
    rates = []
    for _ in range(samples):
        sampled = [values[rng.randrange(len(values))] for _ in range(len(values))]
        rates.append(sum(1 for v in sampled if v) / len(sampled))
    rates.sort()
    ci_low = (1 - ci_level) / 2
    ci_high = 1 - ci_low
    low_idx = round(ci_low * (len(rates) - 1))
    high_idx = round(ci_high * (len(rates) - 1))
    return {"mean": sum(rates) / len(rates), "ci": [rates[low_idx], rates[high_idx]]}


def bootstrap_metric_diffs(
    tool_a: dict[str, bool | None],
    tool_b: dict[str, bool | None],
    ground_truth: dict[str, bool | None],
    case_ids: list[str],
    samples: int,
    seed: int,
    ci_level: float,
) -> dict:
    from benchmarks.metrics.classification import compute_confusion_subset

    rng = random.Random(seed)
    diffs = {"accuracy": [], "precision": [], "recall": [], "f1": []}
    if not case_ids:
        return {k: {"mean": 0.0, "ci": [0.0, 0.0]} for k in diffs}

    for _ in range(samples):
        sampled = [case_ids[rng.randrange(len(case_ids))] for _ in range(len(case_ids))]
        a_metrics = compute_confusion_subset(tool_a, ground_truth, sampled)
        b_metrics = compute_confusion_subset(tool_b, ground_truth, sampled)
        for key in diffs:
            diffs[key].append(a_metrics[key] - b_metrics[key])

    ci_low = (1 - ci_level) / 2
    ci_high = 1 - ci_low
    out: dict[str, dict] = {}
    for key, values in diffs.items():
        values.sort()
        low_idx = round(ci_low * (len(values) - 1))
        high_idx = round(ci_high * (len(values) - 1))
        out[key] = {
            "mean": sum(values) / len(values),
            "ci": [values[low_idx], values[high_idx]],
        }
    return out
