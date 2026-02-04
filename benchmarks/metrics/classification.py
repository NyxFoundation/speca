#!/usr/bin/env python3
"""Classification metrics helpers."""

from __future__ import annotations


def compute_confusion(predictions: dict[str, bool | None], ground_truth: dict[str, bool | None]) -> dict:
    tp = fp = tn = fn = 0
    skipped_missing_pred = 0
    skipped_missing_gt = 0
    for case_id, label in ground_truth.items():
        if label is None:
            skipped_missing_gt += 1
            continue
        pred = predictions.get(case_id)
        if pred is None:
            skipped_missing_pred += 1
            continue
        if label and pred:
            tp += 1
        elif label and not pred:
            fn += 1
        elif not label and pred:
            fp += 1
        else:
            tn += 1
    scored = tp + fp + tn + fn
    total_gt = len([v for v in ground_truth.values() if v is not None])
    coverage = scored / total_gt if total_gt else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": (tp + tn) / scored if scored else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "coverage": coverage,
        "skipped_missing_pred": skipped_missing_pred,
        "skipped_missing_gt": skipped_missing_gt,
    }


def compute_confusion_subset(
    predictions: dict[str, bool | None], ground_truth: dict[str, bool | None], case_ids: list[str]
) -> dict:
    tp = fp = tn = fn = 0
    for case_id in case_ids:
        label = ground_truth.get(case_id)
        pred = predictions.get(case_id)
        if label is None or pred is None:
            continue
        if label and pred:
            tp += 1
        elif label and not pred:
            fn += 1
        elif not label and pred:
            fp += 1
        else:
            tn += 1
    scored = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": (tp + tn) / scored if scored else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }
