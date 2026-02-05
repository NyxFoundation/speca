"""
Resume Manager Module

Scans existing PARTIAL files to identify already-processed items,
enabling incremental re-execution of a phase.
"""

import glob
import json
import sys
from pathlib import Path
from typing import Any

from .config import PhaseConfig


class ResumeManager:
    """
    Determines which items have already been processed by inspecting
    PARTIAL output files on disk.

    Usage in BaseOrchestrator.run():
        remaining, skipped = self.resume_manager.filter_remaining(all_items)
    """

    def __init__(self, config: PhaseConfig):
        self.config = config
        self.output_dir = Path("outputs")

    def get_processed_ids(self) -> set[str]:
        """
        Scan ``{phase_id}_PARTIAL_*.json`` files and extract IDs from
        result items using ``effective_result_id_field``.

        Falls back to ``metadata.processed_ids`` when present (faster
        path for future runs where the collector records IDs explicitly).

        Corrupted files are logged and skipped.
        """
        pattern = str(self.output_dir / f"{self.config.phase_id}_PARTIAL_*.json")
        id_field = self.config.effective_result_id_field
        result_key = self.config.result_key
        processed: set[str] = set()

        for filepath in sorted(glob.glob(pattern)):
            try:
                with open(filepath) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                print(
                    f"Warning: skipping corrupted PARTIAL {filepath}: {exc}",
                    file=sys.stderr,
                )
                continue

            # Fast path: use metadata.processed_ids if available
            meta_ids = (
                data.get("metadata", {}).get("processed_ids")
                if isinstance(data.get("metadata"), dict)
                else None
            )
            if meta_ids and isinstance(meta_ids, list):
                processed.update(str(i) for i in meta_ids)
                continue

            # Slow path: scan result items
            items = data.get(result_key, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    item_id = item.get(id_field)
                    if item_id is not None:
                        processed.add(str(item_id))

        return processed

    def filter_remaining(
        self,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Remove already-processed items from *items*.

        Returns:
            (remaining_items, skipped_count)
        """
        processed_ids = self.get_processed_ids()
        if not processed_ids:
            return items, 0

        id_field = self.config.item_id_field
        remaining: list[dict[str, Any]] = []
        skipped = 0

        for item in items:
            item_id = item.get(id_field)
            if item_id is not None and str(item_id) in processed_ids:
                skipped += 1
            else:
                remaining.append(item)

        return remaining, skipped
