"""
Result Collector Module

Handles collection, aggregation, and saving of results.
Includes Pydantic-based output validation to catch malformed
LLM outputs before they are persisted to disk.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .config import PhaseConfig
from .paths import get_output_root
from .schemas import (
    Phase01bPartial,
    Phase01ePartial,
    Phase02cPartial,
    Phase03Partial,
    Phase04Partial,
    PartialMetadata,
)


# Map phase_id → Pydantic model for the *result_key* wrapper.
# The collector validates the full output envelope (result_key + metadata).
_PHASE_OUTPUT_MODELS: dict[str, type] = {
    "01b": Phase01bPartial,
    "01e": Phase01ePartial,
    "02c": Phase02cPartial,
    "03": Phase03Partial,
    "04": Phase04Partial,
}


class ResultCollector:
    """
    Collects and saves results from phase execution.

    Responsibilities:
    - Save partial results per batch to disk immediately
    - Validate output data against Pydantic schemas before saving
    - Report validation warnings without blocking saves (lenient mode)
    """

    def __init__(self, config: PhaseConfig):
        self.config = config
        self.output_dir = get_output_root()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Validation statistics (accessible for monitoring / circuit breaker)
        self.total_saves: int = 0
        self.validation_warnings: int = 0
        self.validation_errors: int = 0

    def save_partial(
        self,
        results: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
        timestamp: int | None = None,
    ) -> Path:
        """
        Save partial results from a single batch.

        The output file is validated against the phase-specific Pydantic model.
        Validation failures are logged as warnings but do **not** prevent saving,
        because partial / degraded results are still valuable for resume.

        Args:
            timestamp: Optional timestamp from the batch execution context.
                       Falls back to ``int(time.time())`` if not provided.
        """
        if timestamp is None:
            timestamp = int(time.time())
        # Always use simple {phase_id}_PARTIAL_* naming - no prefix needed
        partial_base = f"{self.config.phase_id}_PARTIAL"

        output_path = (
            self.output_dir
            / f"{partial_base}_W{worker_id}B{batch_index}_{timestamp}.json"
        )

        # Extract processed IDs for fast resume lookup
        id_field = self.config.effective_result_id_field
        processed_ids = [
            str(item[id_field])
            for item in results
            if isinstance(item, dict) and id_field in item
        ]

        # Apply output field filtering if configured
        if self.config.output_fields:
            results = [
                {k: item[k] for k in self.config.output_fields if k in item}
                for item in results
                if isinstance(item, dict)
            ]

        output_data = {
            self.config.result_key: results,
            "metadata": {
                "phase": self.config.phase_id,
                "worker_id": worker_id,
                "batch_index": batch_index,
                "item_count": len(results),
                "timestamp": timestamp,
                "processed_ids": processed_ids,
            },
        }

        # --- Output validation ---
        self.total_saves += 1
        self._validate_output(output_data, output_path)

        # Atomic write: write to temp file then rename to prevent
        # partial reads by concurrent workers (e.g. resume scanning).
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.output_dir), suffix=".json.tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2)
            os.replace(tmp_path, str(output_path))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return output_path

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_output(
        self,
        output_data: dict[str, Any],
        output_path: Path,
    ) -> None:
        """
        Validate *output_data* against the phase-specific Pydantic model.

        Validation is **lenient**: warnings are printed to stderr and counters
        are incremented, but the save is never blocked.  This allows downstream
        resume logic to work even with partially malformed outputs.
        """
        # 1. Validate metadata envelope
        meta_raw = output_data.get("metadata", {})
        try:
            PartialMetadata.model_validate(meta_raw)
        except ValidationError as ve:
            self.validation_warnings += 1
            print(
                f"⚠️  Output metadata validation warning ({output_path.name}): "
                f"{ve.error_count()} error(s)",
                file=sys.stderr,
            )
            for err in ve.errors():
                print(f"    {err['loc']}: {err['msg']}", file=sys.stderr)

        # 2. Validate result payload against phase-specific model
        model_cls = _PHASE_OUTPUT_MODELS.get(self.config.phase_id)
        if model_cls is None:
            # Phase 01a has no structured partial output
            return

        try:
            model_cls.model_validate(output_data)
        except ValidationError as ve:
            self.validation_errors += 1
            print(
                f"⚠️  Output schema validation warning ({output_path.name}): "
                f"{ve.error_count()} error(s)",
                file=sys.stderr,
            )
            for err in ve.errors():
                print(f"    {err['loc']}: {err['msg']}", file=sys.stderr)

    def get_validation_summary(self) -> dict[str, int]:
        """Return a summary of validation statistics."""
        return {
            "total_saves": self.total_saves,
            "validation_warnings": self.validation_warnings,
            "validation_errors": self.validation_errors,
        }
