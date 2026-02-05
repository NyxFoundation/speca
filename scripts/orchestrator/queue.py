"""
Queue Manager Module

Handles loading, splitting, and state management for work queues.
"""

import glob
import json
from typing import Any

from .config import PhaseConfig


class QueueManager:
    """
    Manages work queues for phase execution.

    Responsibilities:
    - Load items from input sources
    """

    def __init__(self, config: PhaseConfig):
        self.config = config
    
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
            for key in ["items", "found_specs", "work_queue", "specs", "sub_graphs", "trust_model",
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
    
