"""
Queue Manager Module

Handles loading, splitting, and state management for work queues.
"""

import glob
import json
from pathlib import Path
from typing import Any

from .config import PhaseConfig


class QueueManager:
    """
    Manages work queues for phase execution.
    
    Responsibilities:
    - Load items from input sources
    - Split items across workers
    - Track processed items
    - Resume from partial completion
    """
    
    def __init__(self, config: PhaseConfig):
        self.config = config
        self.output_dir = Path("outputs")
    
    def load_all_items(self) -> list[dict[str, Any]]:
        """
        Load all items from input sources.
        
        This method handles different input patterns based on phase configuration.
        """
        items = []
        
        for pattern in self.config.input_patterns:
            for filepath in sorted(glob.glob(pattern)):
                try:
                    items.extend(self._load_items_from_file(filepath))
                except Exception as e:
                    print(f"Warning: Failed to load {filepath}: {e}")
        
        return items
    
    def _load_items_from_file(self, filepath: str) -> list[dict[str, Any]]:
        """Load items from a single file."""
        with open(filepath) as f:
            data = json.load(f)
        
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        
        if isinstance(data, dict):
            # Try common keys for item lists
            for key in ["items", "found_specs", "work_queue", "sub_graphs", "trust_model",
                        "checklist", "checklist_items", "properties", "audit_items", "reviewed_items"]:
                if key in data and isinstance(data[key], list):
                    items = []
                    for item in data[key]:
                        if isinstance(item, dict):
                            # Add source file reference
                            item["_source_file"] = filepath
                            items.append(item)
                    return items
        
        return []
    
    def split_queue(self, items: list[dict[str, Any]], num_workers: int) -> list[list[dict[str, Any]]]:
        """
        Split items across workers using round-robin distribution.
        
        This ensures even distribution of work across workers.
        """
        queues: list[list[dict[str, Any]]] = [[] for _ in range(num_workers)]
        
        for i, item in enumerate(items):
            worker_id = i % num_workers
            queues[worker_id].append(item)
        
        return queues
    
    def save_worker_queues(
        self,
        queues: list[list[dict[str, Any]]],
    ) -> list[Path]:
        """Save split queues to worker-specific files."""
        queue_files = []
        
        for worker_id, items in enumerate(queues):
            queue_path = self.output_dir / self.config.queue_pattern.format(worker_id=worker_id)
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            
            queue_data = {
                "worker_id": worker_id,
                "phase": self.config.phase_id,
                "items": items,
                "processed": [],
                "total_items": len(items),
            }
            
            with open(queue_path, "w") as f:
                json.dump(queue_data, f, indent=2)
            
            queue_files.append(queue_path)
        
        return queue_files
    
    def get_remaining_items(self, queue_file: Path) -> list[dict[str, Any]]:
        """Get items that haven't been processed yet."""
        with open(queue_file) as f:
            data = json.load(f)
        
        items = data.get("items", [])
        processed = set(data.get("processed", []))
        id_field = self.config.item_id_field
        
        remaining = []
        for item in items:
            item_id = item.get(id_field)
            if item_id and item_id not in processed:
                remaining.append(item)
        
        return remaining
    
    def mark_processed(self, queue_file: Path, item_ids: list[str]) -> None:
        """Mark items as processed in the queue file."""
        with open(queue_file) as f:
            data = json.load(f)
        
        processed = set(data.get("processed", []))
        processed.update(item_ids)
        data["processed"] = sorted(processed)
        
        with open(queue_file, "w") as f:
            json.dump(data, f, indent=2)
