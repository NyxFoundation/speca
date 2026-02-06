"""
Base Orchestrator Module

Provides the abstract base class for all phase orchestrators.
"""

import asyncio
import json
import os
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from tqdm import tqdm

from .config import PhaseConfig, get_phase_config
from .queue import QueueManager
from .batch import BatchStrategy, TokenBasedBatch, CountBasedBatch
from .runner import ClaudeRunner
from .collector import ResultCollector
from .resume import ResumeManager


class BaseOrchestrator(ABC):
    """
    Abstract base class for phase orchestrators.
    
    Provides common functionality for:
    - Queue management
    - Batch creation
    - Parallel Claude execution
    - Result collection
    
    Subclasses can override specific methods for phase-specific behavior.
    """
    
    def __init__(
        self,
        phase_id: str,
        num_workers: int = 4,
        max_concurrent: int = 8,
    ):
        self.config = get_phase_config(phase_id)
        self.num_workers = max(1, num_workers)
        self.max_concurrent = max(1, max_concurrent)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # Components
        self.queue_manager = QueueManager(self.config)
        self.batch_strategy = self._create_batch_strategy()
        self.runner = ClaudeRunner(self.config, self.semaphore)
        self.collector = ResultCollector(self.config)
        self.resume_manager = ResumeManager(self.config)
        
        # State
        self.results: list[dict[str, Any]] = []
        self.failed_batches: list[tuple[int, int]] = []
        self._batch_counter = 0
    
    def _create_batch_strategy(self) -> BatchStrategy:
        """Create the appropriate batch strategy based on config."""
        if self.config.batch_strategy == "token":
            return TokenBasedBatch(
                max_tokens=self.config.max_context_tokens,
                base_tokens=self.config.base_prompt_tokens,
            )
        else:
            return CountBasedBatch(
                max_size=self.config.max_batch_size,
            )
    
    async def run(self) -> None:
        """
        Main execution method.
        
        1. Load items from queue
        2. Apply early exit logic
        3. Create batches
        4. Execute batches in parallel
        5. Collect and save results
        """
        print(f"\n{'='*60}")
        print(f"Phase {self.config.phase_id}: {self.config.name}")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        # Step 1: Load items
        all_items = self.load_items()
        print(f"Loaded {len(all_items)} items")

        if not all_items:
            print("No items to process. Exiting.")
            return

        # Step 1.5: Resume — skip already-processed items
        force_execute = os.environ.get("FORCE_EXECUTE", "") == "1"
        if force_execute:
            print("FORCE_EXECUTE=1: skipping resume filter")
        else:
            all_items, skipped = self.resume_manager.filter_remaining(all_items)
            if skipped:
                print(f"Resume: skipped {skipped} already-processed items, {len(all_items)} remaining")
            if not all_items:
                print("All items already processed. Nothing to do.")
                return

        # Step 2: Apply early exit logic
        early_exit_results, items_to_process = self.apply_early_exit(all_items)
        print(f"Early exit: {len(early_exit_results)} items")
        print(f"To process: {len(items_to_process)} items")
        
        # Step 3: Enrich items (phase-specific)
        enriched_items = self.enrich_items(items_to_process)
        
        # Step 4: Create batches
        batches = self.batch_strategy.create_batches(enriched_items)
        print(f"Created {len(batches)} batches")
        
        # Step 5: Execute batches in parallel
        if batches:
            await self.execute_batches(batches)
        
        duration = time.time() - start_time
        total_results = len(early_exit_results) + len(self.results)
        
        # Step 6: Report failures
        if self.failed_batches:
            print(f"\n⚠️  {len(self.failed_batches)} batch(es) failed (successful results saved as partials)", file=sys.stderr)
            for worker_id, batch_index in self.failed_batches:
                print(f"  - Worker {worker_id}, Batch {batch_index}", file=sys.stderr)
            print(f"   Saved results: {total_results}")
            sys.exit(1)
        
        print(f"\n✅ Phase {self.config.phase_id} completed in {duration:.1f}s")
        print(f"   Total results: {total_results}")
    
    def load_items(self) -> list[dict[str, Any]]:
        """Load items from input sources. Override for custom loading logic."""
        return self.queue_manager.load_all_items()
    
    def apply_early_exit(
        self,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Apply early exit logic to items.
        
        Returns:
            Tuple of (early_exit_results, items_to_process)
        """
        if not self.config.early_exit_check:
            return [], items
        
        early_exit_results = []
        items_to_process = []
        
        for item in items:
            if self.config.early_exit_check(item):
                if self.config.early_exit_builder:
                    early_exit_results.append(self.config.early_exit_builder(item))
            else:
                items_to_process.append(item)
        
        return early_exit_results, items_to_process
    
    def enrich_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Enrich items with additional context.
        Override in subclasses for phase-specific enrichment.
        """
        return items
    
    async def execute_batches(self, batches: list[list[dict[str, Any]]]) -> None:
        """Execute all batches in parallel with progress tracking."""

        async def _run_with_meta(
            batch: list[dict[str, Any]],
            worker_id: int,
            batch_index: int,
        ) -> tuple[list[dict[str, Any]] | None, int, int, int]:
            """Wrap runner call to carry metadata through asyncio.as_completed."""
            result = await self.runner.run_batch(batch, worker_id, batch_index)
            return result, worker_id, batch_index, len(batch)

        tasks = []
        for batch in batches:
            worker_id = self._batch_counter % self.num_workers
            self._batch_counter += 1
            batch_index = self._batch_counter

            tasks.append(asyncio.create_task(
                _run_with_meta(batch, worker_id, batch_index)
            ))

        total_items = sum(len(b) for b in batches)

        with tqdm(total=total_items, desc=f"Processing {self.config.name}", unit="item") as pbar:
            for coro in asyncio.as_completed(tasks):
                batch_size = 0
                try:
                    result, worker_id, batch_index, batch_size = await coro
                    if result is None:
                        self.failed_batches.append((worker_id, batch_index))
                    else:
                        self.results.extend(result)
                        if result:
                            self.collector.save_partial(result, worker_id, batch_index)
                except Exception as e:
                    print(f"Task failed with error: {e}", file=sys.stderr)
                    self.failed_batches.append((0, 0))
                finally:
                    pbar.update(batch_size)
    



class Phase01Orchestrator(BaseOrchestrator):
    """Orchestrator for Phase 01 (Specification Analysis) sub-phases."""

    def load_items(self) -> list[dict[str, Any]]:
        """
        Load items for Phase 01.
        - 01a: Returns a single seed item (no input file).
        - 01c/01d: Loads file paths as items.
        - Others: Standard queue loading.
        """
        if self.config.phase_id == "01a":
            return [{"id": "seed", "source": "manual"}]
        
        if self.config.phase_id in ("01c", "01d"):
            return self._load_file_path_items()
            
        return super().load_items()

    def _load_file_path_items(self) -> list[dict[str, Any]]:
        """Load each matching file as a single work item (file_path = item)."""
        import glob as glob_mod

        items = []
        for pattern in self.config.input_patterns:
            for filepath in sorted(glob_mod.glob(pattern)):
                items.append({"file_path": filepath})
        return items

    def enrich_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich items with necessary context."""
        if self.config.phase_id == "01a":
            # For 01a, we need to ensure KEYWORDS and SPEC_URLS are available
            # We don't necessarily modify the item, as env vars are handled in runner
            # But we can validate here
            keywords = os.environ.get("KEYWORDS")
            spec_urls = os.environ.get("SPEC_URLS")
            if not keywords or not spec_urls:
                 # Fallback defaults if not set (mirroring Makefile defaults)
                 # These should ideally be passed from run_phase.py or env
                 print("Warning: KEYWORDS or SPEC_URLS not set, using defaults")
            return items

        if self.config.phase_id in ("01d", "01e"):
            return self._enrich_with_subgraph_context(items)
        return items
    
    def _enrich_with_subgraph_context(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Add subgraph data to items."""
        # Load subgraph cache
        subgraph_cache: dict[str, dict] = {}
        
        enriched = []
        for item in items:
            enriched_item = item.copy()
            
            # Load relevant subgraph if referenced
            subgraph_file = item.get("subgraph_file")
            if subgraph_file:
                if subgraph_file not in subgraph_cache:
                    try:
                        with open(subgraph_file) as f:
                            subgraph_cache[subgraph_file] = json.load(f)
                    except Exception:
                        subgraph_cache[subgraph_file] = {}
                
                subgraph_id = item.get("subgraph_id")
                if subgraph_id:
                    for sg in subgraph_cache[subgraph_file].get("sub_graphs", []):
                        if sg.get("id") == subgraph_id:
                            enriched_item["subgraph"] = sg
                            break
            
            enriched.append(enriched_item)
        
        return enriched


class Phase02Orchestrator(BaseOrchestrator):
    """Orchestrator for Phase 02 (Checklist Generation)."""
    
    def load_items(self) -> list[dict[str, Any]]:
        """Load properties from 01e partials efficiently with deduplication."""
        import glob
        
        items = {}  # Deduplication map
        for filepath in sorted(glob.glob("outputs/01e_PARTIAL_*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                for prop in data.get("properties", []):
                    if isinstance(prop, dict):
                        prop_id = prop.get("id")
                        if prop_id and prop_id not in items:
                            # Keep first occurrence
                            items[prop_id] = {
                                "property_id": prop_id,
                                "property": prop,
                                "source_file": filepath,
                            }
            except Exception as e:
                print(f"Warning: Failed to load {filepath}: {e}", file=sys.stderr)
        
        return list(items.values())

    def apply_early_exit(
        self,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Apply early exit for properties without required fields."""
        early_exit_results = []
        items_to_process = []
        
        for item in items:
            prop = item.get("property", {})
            
            # Check required fields
            if not prop.get("id"):
                early_exit_results.append(self._build_skip_result(item, "missing property id"))
                continue
            
            # Skip out-of-scope properties
            reachability = prop.get("reachability", {})
            if reachability.get("bug_bounty_scope") == "out-of-scope":
                early_exit_results.append(self._build_skip_result(item, "out-of-scope"))
                continue
            
            items_to_process.append(item)
        
        return early_exit_results, items_to_process
    
    def _build_skip_result(self, item: dict[str, Any], reason: str) -> dict[str, Any]:
        """Build a skip result for early exit items."""
        return {
            "check_id": f"SKIP-{item.get('property_id', 'unknown')}",
            "property_id": item.get("property_id"),
            "checklist": [],  # Empty checklist for skipped items
            "skipped": True,
            "skip_reason": reason,
        }


class Phase03Orchestrator(BaseOrchestrator):
    """
    Orchestrator for Phase 03 (Audit Map Generation).
    
    This is the reference implementation that other phases should follow.
    """
    
    def __init__(self, num_workers: int = 4, max_concurrent: int = 8):
        super().__init__("03", num_workers, max_concurrent)
        self.property_subgraph_map: dict[str, tuple[str | None, str]] = {}
    
    def load_items(self) -> list[dict[str, Any]]:
        """Load checklist items from 02 partials."""
        import glob
        
        # Build property to subgraph mapping
        self._build_property_subgraph_map()
        
        items = {}
        for filepath in sorted(glob.glob("outputs/02_PARTIAL_*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                entries = data.get("checklist_items") or data.get("checklist") or []
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    check_id = entry.get("id") or entry.get("check_id")
                    if not check_id:
                        continue
                    
                    item = {
                        "check_id": check_id,
                        "checklist_item": entry,
                        "checklist_file": filepath,
                    }
                    
                    # Add property and subgraph references
                    property_id = entry.get("property_id")
                    if property_id:
                        item["property_id"] = property_id
                        subgraph_info = self.property_subgraph_map.get(property_id)
                        if subgraph_info:
                            item["subgraph_id"], item["subgraph_file"] = subgraph_info
                    
                    items[check_id] = item
            except Exception as e:
                print(f"Warning: Failed to load {filepath}: {e}", file=sys.stderr)
        
        return list(items.values())
    
    def _build_property_subgraph_map(self) -> None:
        """Build mapping from property_id to (subgraph_id, subgraph_file)."""
        import glob
        
        for prop_file in sorted(glob.glob("outputs/01e_PROP_PARTIAL_*.json")):
            try:
                with open(prop_file) as f:
                    prop_data = json.load(f)
                
                source_files = prop_data.get("metadata", {}).get("source_files", [])
                subgraph_cache = {}
                
                for sg_file in source_files:
                    if Path(sg_file).exists():
                        with open(sg_file) as f:
                            subgraph_cache[sg_file] = json.load(f)
                
                for prop in prop_data.get("properties", []):
                    if not isinstance(prop, dict):
                        continue
                    prop_id = prop.get("id")
                    if not prop_id:
                        continue
                    
                    # Find primary element
                    covers = prop.get("covers", {})
                    primary_element = covers.get("primary_element")
                    if not primary_element:
                        edges = covers.get("edges", [])
                        nodes = covers.get("nodes", [])
                        primary_element = edges[0] if edges else (nodes[0] if nodes else None)
                    
                    if not primary_element:
                        continue
                    
                    # Find subgraph containing this element
                    for sg_file, sg_data in subgraph_cache.items():
                        for subgraph in sg_data.get("sub_graphs", []):
                            edge_ids = [e.get("id") for e in subgraph.get("edges", [])]
                            node_ids = [n.get("id") for n in subgraph.get("nodes", [])]
                            if primary_element in edge_ids or primary_element in node_ids:
                                self.property_subgraph_map[prop_id] = (
                                    subgraph.get("id"),
                                    sg_file,
                                )
                                break
            except Exception as e:
                print(f"Warning: Failed to process {prop_file}: {e}", file=sys.stderr)
    
    def apply_early_exit(
        self,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Apply early exit for items without property_id."""
        early_exit_results = []
        items_to_process = []
        
        for item in items:
            property_id = item.get("property_id")
            if not property_id:
                checklist_item = item.get("checklist_item", {})
                if isinstance(checklist_item, dict):
                    property_id = checklist_item.get("property_id")
            
            if not property_id:
                early_exit_results.append(self._build_early_exit_result(item))
            else:
                items_to_process.append(item)
        
        return early_exit_results, items_to_process
    
    def _build_early_exit_result(self, item: dict[str, Any]) -> dict[str, Any]:
        """Build early exit result for items without required metadata."""
        check_id = item.get("check_id")
        checklist_item = item.get("checklist_item", {})
        code_scope = item.get("code_scope") or checklist_item.get("code_scope", {})
        
        return {
            "check_id": check_id,
            "property_id": item.get("property_id"),
            "code_scope": code_scope,
            "final_classification": "out-of-scope",
            "bug_bounty_eligible": False,
            "summary": "Early exit: insufficient item metadata.",
            "audit_trail": {
                "phase1_abstract_interpretation": {
                    "summary": "Early exit: missing required identifiers.",
                    "state_anomalies_found": [],
                },
                "phase2_symbolic_execution": {
                    "summary": "Not performed due to early exit.",
                    "counterexample_found": False,
                    "counterexample": None,
                },
                "phase3_invariant_proving": {
                    "summary": "Not performed due to early exit.",
                    "proof_successful": False,
                    "guard_identified": None,
                },
            },
        }
    
    def enrich_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich items with subgraph data."""
        subgraph_cache: dict[str, dict] = {}
        enriched = []
        
        for item in items:
            enriched_item = item.copy()
            
            subgraph_file = item.get("subgraph_file")
            subgraph_id = item.get("subgraph_id")
            
            if subgraph_file and subgraph_id:
                if subgraph_file not in subgraph_cache:
                    try:
                        with open(subgraph_file) as f:
                            subgraph_cache[subgraph_file] = json.load(f)
                    except Exception:
                        subgraph_cache[subgraph_file] = {}
                
                for sg in subgraph_cache[subgraph_file].get("sub_graphs", []):
                    if sg.get("id") == subgraph_id:
                        enriched_item["subgraph"] = sg
                        break
            
            enriched.append(enriched_item)
        
        return enriched


class Phase04Orchestrator(BaseOrchestrator):
    """Orchestrator for Phase 04 (Audit Review)."""
    
    def load_items(self) -> list[dict[str, Any]]:
        """Load audit results from 03 partials."""
        import glob
        
        items = []
        for filepath in sorted(glob.glob("outputs/03_AUDITMAP_PARTIAL_*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                audit_items = data.get("audit_items", [])
                for item in audit_items:
                    if isinstance(item, dict) and item.get("check_id"):
                        items.append({
                            "check_id": item.get("check_id"),
                            "audit_result": item,
                            "source_file": filepath,
                        })
            except Exception as e:
                print(f"Warning: Failed to load {filepath}: {e}", file=sys.stderr)
        
        return items
