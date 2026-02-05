"""
Result Collector Module

Handles collection, aggregation, and saving of results.
"""

import json
import time
from pathlib import Path
from typing import Any

from .config import PhaseConfig


class ResultCollector:
    """
    Collects and saves results from phase execution.
    
    Responsibilities:
    - Save partial results per batch to disk immediately
    """
    
    def __init__(self, config: PhaseConfig):
        self.config = config
        self.output_dir = Path("outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def save_partial(
        self,
        results: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> Path:
        """Save partial results from a single batch."""
        timestamp = int(time.time())
        output_path = self.output_dir / f"{self.config.phase_id}_PARTIAL_W{worker_id}B{batch_index}_{timestamp}.json"

        # Extract processed IDs for fast resume lookup
        id_field = self.config.effective_result_id_field
        processed_ids = [
            str(item[id_field])
            for item in results
            if isinstance(item, dict) and id_field in item
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

        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)

        return output_path