"""
Filtering utilities for phase orchestrators.

Provides common filtering logic to skip items based on status or scope.
"""

from typing import Any


def should_skip_item_for_audit(item: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Determine if an item should be skipped during Phase 03 (audit).

    Args:
        item: Checklist item with code_scope field

    Returns:
        Tuple of (should_skip: bool, reason: str | None)
    """
    code_scope = item.get("code_scope", {})
    resolution_status = code_scope.get("resolution_status", "")

    # Skip out_of_scope items (layer mismatch)
    if resolution_status == "out_of_scope":
        return True, "Layer mismatch - spec not applicable to target"

    # Skip items without resolved code locations
    if resolution_status == "not_found":
        return True, "Code location not found"

    # Skip items with errors (unless you want to retry them)
    if resolution_status == "error":
        return True, "Code resolution error"

    # Process resolved items
    if resolution_status == "resolved":
        locations = code_scope.get("locations", [])
        if not locations:
            return True, "No code locations available"
        return False, None

    # Unknown status - skip to be safe
    return True, f"Unknown resolution status: {resolution_status}"


def filter_items_for_audit(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """
    Filter checklist items for Phase 03 audit.

    Args:
        items: List of checklist items with code_scope

    Returns:
        Tuple of (filtered_items, skip_stats)
        - filtered_items: Items that should be audited
        - skip_stats: Dict of skip reasons and counts
    """
    filtered = []
    skip_stats = {}

    for item in items:
        should_skip, reason = should_skip_item_for_audit(item)

        if should_skip:
            skip_stats[reason] = skip_stats.get(reason, 0) + 1
        else:
            filtered.append(item)

    return filtered, skip_stats


def mark_item_as_skipped(item: dict[str, Any], reason: str) -> dict[str, Any]:
    """
    Mark an item as skipped in Phase 03 output.

    This allows downstream phases (Phase 04) to understand why items were not audited.
    """
    item["audit_result"] = {
        "status": "skipped",
        "reason": reason,
        "phases": {
            "abstract_interpretation": {"status": "skipped"},
            "symbolic_execution": {"status": "skipped"},
            "invariant_proving": {"status": "skipped"},
        },
    }
    return item
