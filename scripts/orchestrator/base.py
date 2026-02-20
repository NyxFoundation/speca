"""
Base Orchestrator Module

Provides the abstract base class for all phase orchestrators.
"""

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from tqdm import tqdm

from .config import PhaseConfig, get_phase_config
from .queue import QueueManager
from .batch import BatchStrategy, TokenBasedBatch, CountBasedBatch
from .runner import ClaudeRunner, CircuitBreaker, CircuitBreakerTripped, BudgetExceeded
from .watchdog import CostTracker
from .collector import ResultCollector
from .resume import ResumeManager
from .schemas import (
    ChecklistItem,
    Phase01aState,
    Phase01bPartial,
    Phase01cPartial,
    Phase01dPartial,
    Phase01ePartial,
    Phase02Partial,
    Phase02cPartial,
    Phase03Partial,
    AuditMapItem,
    Severity,
    validate_checklist_item,
    validate_audit_map_item,
    validate_subgraph,
    validate_property,
    validate_reviewed_item,
)


# ---------------------------------------------------------------------------
# Helper: log Pydantic validation warnings
# ---------------------------------------------------------------------------

def _log_validation_warning(
    filepath: str,
    ve: ValidationError,
    *,
    prefix: str = "",
) -> None:
    """Print structured Pydantic validation warnings to stderr."""
    label = f"{prefix} " if prefix else ""
    print(
        f"⚠️  {label}Schema validation warning for {filepath}: "
        f"{ve.error_count()} error(s)",
        file=sys.stderr,
    )
    for err in ve.errors():
        print(f"    {err['loc']}: {err['msg']}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Helper: generate slug from text for meaningful IDs
# ---------------------------------------------------------------------------

_SLUG_ABBREVS = {
    "transaction": "txn", "p2p": "p2p", "engine api": "engapi",
    "consensus": "cons", "validator": "val", "attestation": "attest",
    "beacon": "beacon", "execution": "exec", "block": "blk",
    "state": "state", "sync": "sync", "gossip": "gossip",
    "networking": "net", "devp2p": "devp2p", "libp2p": "libp2p",
}


def generate_slug(text: str, max_len: int = 12) -> str:
    """Generate a short slug from descriptive text for use in IDs.

    Uses a known abbreviation map first, then falls back to
    alphanumeric slugification, and finally a hash if nothing remains.
    """
    lower = text.lower().strip()
    for phrase, abbrev in _SLUG_ABBREVS.items():
        if phrase in lower:
            return abbrev[:max_len]
    slug = re.sub(r'[^a-z0-9]+', '-', lower).strip('-')
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip('-')
    return slug or hashlib.sha256(text.encode()).hexdigest()[:8]


class BaseOrchestrator(ABC):
    """
    Abstract base class for phase orchestrators.
    
    Provides common functionality for:
    - Queue management
    - Batch creation
    - Parallel Claude execution
    - Result collection
    - **Circuit breaker** for anomaly detection and cost control
    - **Cost tracking** with automatic budget enforcement
    
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
        
        # Shared circuit breaker for all workers in this phase
        self.circuit_breaker = CircuitBreaker(self.config)

        # Cost tracker — shared across all workers
        self.cost_tracker: CostTracker | None = None
        if self.config.max_budget_usd > 0:
            self.cost_tracker = CostTracker(
                max_budget_usd=self.config.max_budget_usd,
            )

        # Components
        self.queue_manager = QueueManager(self.config)
        self.batch_strategy = self._create_batch_strategy()
        self.runner = ClaudeRunner(
            self.config,
            self.semaphore,
            circuit_breaker=self.circuit_breaker,
            cost_tracker=self.cost_tracker,
        )
        self.collector = ResultCollector(self.config)
        self.resume_manager = ResumeManager(self.config)
        
        # State
        self.results: list[dict[str, Any]] = []
        self.failed_batches: list[tuple[int, int]] = []
        self._batch_counter = 0
        self._circuit_breaker_tripped = False
        self._budget_exceeded = False
    
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
        6. Report circuit breaker / validation statistics
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

        # Step 6: Print statistics
        self._print_run_statistics(duration, total_results)
        
        # Step 7: Report failures
        if self._budget_exceeded:
            print(
                f"\n\U0001f6d1 Phase {self.config.phase_id} ABORTED — budget exceeded "
                f"after {duration:.1f}s",
                file=sys.stderr,
            )
            print(f"   Saved results so far: {total_results}")
            sys.exit(2)

        if self._circuit_breaker_tripped:
            print(
                f"\n🛑 Phase {self.config.phase_id} ABORTED by circuit breaker "
                f"after {duration:.1f}s",
                file=sys.stderr,
            )
            print(f"   Saved results so far: {total_results}")
            sys.exit(2)

        if self.failed_batches:
            print(f"\n⚠️  {len(self.failed_batches)} batch(es) failed (successful results saved as partials)", file=sys.stderr)
            for worker_id, batch_index in self.failed_batches:
                print(f"  - Worker {worker_id}, Batch {batch_index}", file=sys.stderr)
            print(f"   Saved results: {total_results}")
            sys.exit(1)
        
        print(f"\n✅ Phase {self.config.phase_id} completed in {duration:.1f}s")
        print(f"   Total results: {total_results}")

    def _print_run_statistics(self, duration: float, total_results: int) -> None:
        """Print circuit breaker and validation statistics."""
        cb_stats = self.circuit_breaker.get_stats()
        val_stats = self.collector.get_validation_summary()

        print(f"\n{'─'*40}")
        print(f"Run Statistics (Phase {self.config.phase_id})")
        print(f"{'─'*40}")
        print(f"  Duration:              {duration:.1f}s")
        print(f"  Total results:         {total_results}")
        print(f"  Batch successes:       {cb_stats['total_successes']}")
        print(f"  Batch failures:        {cb_stats['total_failures']}")
        print(f"  Total retries:         {cb_stats['total_retries']}")
        print(f"  Empty results:         {cb_stats['empty_results']}")
        print(f"  Validation warnings:   {val_stats['validation_warnings']}")
        print(f"  Validation errors:     {val_stats['validation_errors']}")

        # Cost statistics
        cost_stats = None
        if self.cost_tracker:
            cost_stats = self.cost_tracker.get_stats()
            print(f"  ---- Cost ----")
            print(f"  Input tokens:          {cost_stats['total_input_tokens']:,}")
            print(f"  Cache read tokens:     {cost_stats['total_cache_read_tokens']:,}")
            print(f"  Cache create tokens:   {cost_stats['total_cache_creation_tokens']:,}")
            print(f"  Output tokens:         {cost_stats['total_output_tokens']:,}")
            print(f"  Estimated cost:        ${cost_stats['total_cost_usd']:.2f}")
            print(f"  Budget:                ${cost_stats['max_budget_usd']:.2f}")
            print(f"  Budget utilization:    {cost_stats['budget_utilization_pct']:.1f}%")
        _sep = '\u2500' * 40
        print(_sep)

        # Write to GitHub Step Summary if running in GitHub Actions
        self._write_github_step_summary(
            duration, total_results, cb_stats, val_stats, cost_stats,
        )

    def _write_github_step_summary(
        self,
        duration: float,
        total_results: int,
        cb_stats: dict[str, Any],
        val_stats: dict[str, Any],
        cost_stats: dict[str, Any] | None,
    ) -> None:
        """
        Write a Markdown summary to ``$GITHUB_STEP_SUMMARY``.

        This renders a rich table in the GitHub Actions "Summary" tab for
        each workflow run, making it easy to spot anomalies at a glance.
        If the environment variable is not set (i.e. running locally),
        this method is a no-op.
        """
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if not summary_path:
            return

        # Determine status emoji
        if self._budget_exceeded:
            status = "\U0001f6d1 Budget Exceeded"
        elif self._circuit_breaker_tripped:
            status = "\U0001f6d1 Circuit Breaker Tripped"
        elif self.failed_batches:
            status = "\u26a0\ufe0f Partial Failure"
        else:
            status = "\u2705 Success"

        lines: list[str] = []
        lines.append(f"## Phase {self.config.phase_id}: {self.config.name}")
        lines.append("")
        lines.append(f"**Status:** {status}")
        lines.append("")

        # --- Execution summary table ---
        lines.append("### Execution Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("| :--- | ---: |")
        lines.append(f"| Duration | {duration:.1f}s |")
        lines.append(f"| Total results | {total_results} |")
        lines.append(f"| Batch successes | {cb_stats['total_successes']} |")
        lines.append(f"| Batch failures | {cb_stats['total_failures']} |")
        lines.append(f"| Total retries | {cb_stats['total_retries']} |")
        lines.append(f"| Empty results | {cb_stats['empty_results']} |")
        lines.append(f"| Validation warnings | {val_stats['validation_warnings']} |")
        lines.append(f"| Validation errors | {val_stats['validation_errors']} |")
        lines.append("")

        # --- Cost table (if available) ---
        if cost_stats:
            lines.append("### Cost Report")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("| :--- | ---: |")
            lines.append(f"| Input tokens | {cost_stats.get('total_input_tokens', 0):,} |")
            lines.append(f"| Cache read tokens | {cost_stats.get('total_cache_read_tokens', 0):,} |")
            lines.append(f"| Cache creation tokens | {cost_stats.get('total_cache_creation_tokens', 0):,} |")
            lines.append(f"| Output tokens | {cost_stats.get('total_output_tokens', 0):,} |")
            lines.append(f"| Estimated cost | ${cost_stats.get('total_cost_usd', 0):.2f} |")
            lines.append(f"| Budget | ${cost_stats.get('max_budget_usd', 0):.2f} |")
            lines.append(f"| Budget utilization | {cost_stats.get('budget_utilization_pct', 0):.1f}% |")
            lines.append("")

            # Budget bar (visual indicator)
            pct = min(cost_stats['budget_utilization_pct'], 100.0)
            filled = int(pct / 5)  # 20 chars = 100%
            bar = '\u2588' * filled + '\u2591' * (20 - filled)
            if pct >= 80:
                lines.append(f"> \U0001f534 **Budget: [{bar}] {pct:.1f}%**")
            elif pct >= 50:
                lines.append(f"> \U0001f7e1 Budget: [{bar}] {pct:.1f}%")
            else:
                lines.append(f"> \U0001f7e2 Budget: [{bar}] {pct:.1f}%")
            lines.append("")

        # --- Failed batches detail ---
        if self.failed_batches:
            lines.append("### Failed Batches")
            lines.append("")
            lines.append("| Worker | Batch |")
            lines.append("| :---: | :---: |")
            for worker_id, batch_index in self.failed_batches:
                lines.append(f"| {worker_id} | {batch_index} |")
            lines.append("")

        md = "\n".join(lines)

        try:
            with open(summary_path, "a") as f:
                f.write(md)
                f.write("\n")
        except OSError as e:
            print(f"Warning: could not write to GITHUB_STEP_SUMMARY: {e}", file=sys.stderr)

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
        """
        Execute all batches in parallel with progress tracking.

        Integrates circuit breaker: if ``CircuitBreakerTripped`` is raised by
        any worker, all remaining tasks are cancelled and partial results are
        preserved.
        """

        async def _run_with_meta(
            batch: list[dict[str, Any]],
            worker_id: int,
            batch_index: int,
        ) -> tuple[list[dict[str, Any]] | None, int, int, int]:
            """Wrap runner call to carry metadata through asyncio.as_completed."""
            result = await self.runner.run_batch(batch, worker_id, batch_index)
            return result, worker_id, batch_index, len(batch)

        tasks: list[asyncio.Task] = []
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
                except CircuitBreakerTripped as cb:
                    self._circuit_breaker_tripped = True
                    print(
                        f"\n\U0001f6d1 Circuit breaker tripped: {cb.reason}",
                        file=sys.stderr,
                    )
                    print(
                        f"   Stats: {cb.stats}",
                        file=sys.stderr,
                    )
                    # Cancel all remaining tasks
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    break
                except BudgetExceeded as be:
                    self._budget_exceeded = True
                    print(
                        f"\n\U0001f4b8 Budget exceeded: {be}",
                        file=sys.stderr,
                    )
                    print(
                        f"   Stats: {be.stats}",
                        file=sys.stderr,
                    )
                    # Cancel all remaining tasks
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    break
                except Exception as e:
                    print(f"Task failed with error: {e}", file=sys.stderr)
                    self.failed_batches.append((0, 0))
                finally:
                    pbar.update(batch_size)
    


class Phase01Orchestrator(BaseOrchestrator):
    """Orchestrator for Phase 01 (Specification Analysis) sub-phases."""

    def load_items(self) -> list[dict[str, Any]]:
        """
        Load items for Phase 01 with Pydantic validation at phase boundaries.

        - 01a: Returns a single seed item (no input file).
        - 01b: Loads discovered specs from 01a_STATE.json with validation.
        - 01c/01d: Loads file paths as items with structural validation.
        - 01e: Loads trust model outputs with validation.
        - Others: Standard queue loading.
        """
        if self.config.phase_id == "01a":
            return [{"id": "seed", "source": "manual"}]

        if self.config.phase_id == "01b":
            return self._load_01b_items()

        if self.config.phase_id == "01c":
            return self._load_01c_items()

        if self.config.phase_id == "01d":
            return self._load_01d_items()

        if self.config.phase_id == "01e":
            return self._load_01e_items()

        return super().load_items()

    # -- Phase 01b: load discovered specs from 01a output ----------------

    def _load_01b_items(self) -> list[dict[str, Any]]:
        """Load discovered specs from 01a_STATE.json with Pydantic validation."""
        import glob as glob_mod

        items: list[dict[str, Any]] = []
        for pattern in self.config.input_patterns:
            for filepath in sorted(glob_mod.glob(pattern)):
                try:
                    with open(filepath) as f:
                        data = json.load(f)

                    # Validate 01a output structure
                    try:
                        state = Phase01aState.model_validate(data)
                        print(
                            f"  ✓ {filepath}: {len(state.found_specs)} specs validated"
                        )
                    except ValidationError as ve:
                        _log_validation_warning(filepath, ve, prefix="01a→01b")
                        # Fall through to raw parsing

                    for spec in data.get("found_specs", []):
                        if isinstance(spec, dict) and spec.get("url"):
                            items.append(spec)
                except Exception as e:
                    print(
                        f"Warning: Failed to load {filepath}: {e}",
                        file=sys.stderr,
                    )
        return items

    # -- Phase 01c: load subgraph files for verification -----------------

    def _load_01c_items(self) -> list[dict[str, Any]]:
        """Load subgraph files for verification with Pydantic validation."""
        import glob as glob_mod

        items: list[dict[str, Any]] = []
        validation_warnings = 0

        for pattern in self.config.input_patterns:
            for filepath in sorted(glob_mod.glob(pattern)):
                try:
                    with open(filepath) as f:
                        data = json.load(f)

                    # Validate 01b partial structure
                    try:
                        partial = Phase01bPartial.model_validate(data)
                        for spec in partial.specs:
                            for sg in spec.sub_graphs:
                                _, errs = validate_subgraph(sg.model_dump())
                                if errs:
                                    for err in errs:
                                        print(
                                            f"    ⚠️  {filepath} subgraph {sg.id}: {err}",
                                            file=sys.stderr,
                                        )
                    except ValidationError as ve:
                        _log_validation_warning(filepath, ve, prefix="01b→01c")
                        validation_warnings += 1

                    # Regardless of validation, load file path items
                    items.append({"file_path": filepath})
                except Exception as e:
                    print(
                        f"Warning: Failed to load {filepath}: {e}",
                        file=sys.stderr,
                    )

        if validation_warnings:
            print(
                f"⚠️  {validation_warnings} file(s) had schema validation warnings (01b→01c)",
                file=sys.stderr,
            )
        return items

    # -- Phase 01d: load subgraph files for trust model analysis ---------

    def _load_01d_items(self) -> list[dict[str, Any]]:
        """Load subgraph files for trust model analysis with Pydantic validation."""
        import glob as glob_mod

        items: list[dict[str, Any]] = []
        validation_warnings = 0

        for pattern in self.config.input_patterns:
            for filepath in sorted(glob_mod.glob(pattern)):
                try:
                    with open(filepath) as f:
                        data = json.load(f)

                    # Validate 01b partial structure
                    try:
                        Phase01bPartial.model_validate(data)
                    except ValidationError as ve:
                        _log_validation_warning(filepath, ve, prefix="01b→01d")
                        validation_warnings += 1

                    items.append({"file_path": filepath})
                except Exception as e:
                    print(
                        f"Warning: Failed to load {filepath}: {e}",
                        file=sys.stderr,
                    )

        if validation_warnings:
            print(
                f"⚠️  {validation_warnings} file(s) had schema validation warnings (01b→01d)",
                file=sys.stderr,
            )
        return items

    # -- Phase 01e: load trust model outputs for property generation -----

    def _load_01e_items(self) -> list[dict[str, Any]]:
        """Load trust model outputs for property generation with Pydantic validation."""
        import glob as glob_mod

        items: list[dict[str, Any]] = []
        validation_warnings = 0

        for pattern in self.config.input_patterns:
            for filepath in sorted(glob_mod.glob(pattern)):
                try:
                    with open(filepath) as f:
                        data = json.load(f)

                    # Validate 01d partial structure
                    try:
                        Phase01dPartial.model_validate(data)
                    except ValidationError as ve:
                        _log_validation_warning(filepath, ve, prefix="01d→01e")
                        validation_warnings += 1

                    items.append({"file_path": filepath})
                except Exception as e:
                    print(
                        f"Warning: Failed to load {filepath}: {e}",
                        file=sys.stderr,
                    )

        if validation_warnings:
            print(
                f"⚠️  {validation_warnings} file(s) had schema validation warnings (01d→01e)",
                file=sys.stderr,
            )
        return items

    def enrich_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich items with necessary context."""
        if self.config.phase_id == "01a":
            # For 01a, we need to ensure KEYWORDS and SPEC_URLS are available
            keywords = os.environ.get("KEYWORDS")
            spec_urls = os.environ.get("SPEC_URLS")
            if not keywords or not spec_urls:
                 print("Warning: KEYWORDS or SPEC_URLS not set, using defaults")
            return items

        if self.config.phase_id == "01e":
            items = self._assign_property_id_prefixes(items)
            return self._enrich_with_subgraph_context(items)
        if self.config.phase_id == "01d":
            return self._enrich_with_subgraph_context(items)
        return items

    def _assign_property_id_prefixes(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Assign meaningful _id_prefix to each item for property ID generation.

        Derives a slug from the trust model's trust boundary data, ensuring
        uniqueness via a disambiguation counter.
        """
        slug_counters: dict[str, int] = {}
        for item in items:
            file_path = item.get("file_path", "")
            slug = self._derive_slug_from_trust_model(file_path)
            count = slug_counters.get(slug, 0)
            slug_counters[slug] = count + 1
            unique_slug = slug if count == 0 else f"{slug}{count}"
            item["_id_prefix"] = f"PROP-{unique_slug}"
        return items

    def _derive_slug_from_trust_model(self, file_path: str) -> str:
        """Derive a slug from trust model data.

        Reads the trust model JSON and uses the most common
        entry_point_type from trust_boundaries to generate the slug.
        Falls back to a hash of the file name on failure.
        """
        if not file_path:
            return hashlib.sha256(b"unknown").hexdigest()[:8]
        try:
            with open(file_path) as f:
                data = json.load(f)

            # Try trust_model.trust_boundaries[].entry_point_type
            trust_model = data.get("trust_model", data)
            boundaries = trust_model.get("trust_boundaries", [])
            if boundaries:
                # Collect entry_point_type values and pick the most common
                type_counts: dict[str, int] = {}
                for boundary in boundaries:
                    ept = boundary.get("entry_point_type", "")
                    if ept:
                        type_counts[ept] = type_counts.get(ept, 0) + 1
                if type_counts:
                    most_common = max(type_counts, key=type_counts.get)  # type: ignore[arg-type]
                    return generate_slug(most_common)

            # Fallback: use the file name stem
            stem = Path(file_path).stem
            return generate_slug(stem)
        except Exception:
            # Hash fallback
            return hashlib.sha256(file_path.encode()).hexdigest()[:8]
    
    def _enrich_with_subgraph_context(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Add subgraph data to items."""
        subgraph_cache: dict[str, dict] = {}
        
        enriched = []
        for item in items:
            enriched_item = item.copy()
            
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
        """Load properties from 01e partials with Pydantic validation and deduplication."""
        import glob

        items = {}  # Deduplication map
        validation_warnings = 0

        # Simple pattern: always {phase}_PARTIAL_*.json
        for filepath in sorted(glob.glob("outputs/01e_PARTIAL_*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)

                # Validate 01e partial structure
                try:
                    partial = Phase01ePartial.model_validate(data)
                    print(
                        f"  ✓ {filepath}: {len(partial.properties)} properties validated"
                    )
                except ValidationError as ve:
                    _log_validation_warning(filepath, ve, prefix="01e→02")
                    validation_warnings += 1

                for prop in data.get("properties", []):
                    if isinstance(prop, dict):
                        # Validate individual properties
                        parsed, errs = validate_property(prop)
                        if errs:
                            prop_id_raw = prop.get("id", "<unknown>")
                            for err in errs:
                                print(
                                    f"    ⚠️  {filepath} property {prop_id_raw}: {err}",
                                    file=sys.stderr,
                                )

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

        if validation_warnings:
            print(
                f"⚠️  {validation_warnings} file(s) had schema validation warnings (01e→02)",
                file=sys.stderr,
            )
        
        return list(items.values())

    def apply_early_exit(
        self,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Apply early exit for properties without required fields.

        Filters applied (in order):
        1. Missing property ID → skip
        2. Bug-bounty out-of-scope → skip
        3. Severity below ``min_severity`` config threshold → skip
        """
        early_exit_results = []
        items_to_process = []

        # Resolve the severity threshold once (None = no filtering)
        min_sev = Severity.from_str(self.config.min_severity) if self.config.min_severity else None
        if min_sev is not None:
            print(f"  Severity gate: min_severity={min_sev.value} (dropping below)")

        severity_skipped = 0

        for item in items:
            prop = item.get("property", {})

            # Check required fields
            if not prop.get("id"):
                early_exit_results.append(self._build_skip_result(item, "missing property id"))
                continue

            # Skip ONLY out-of-scope properties
            # Keep all other items (in-scope, conditional, unknown) for Phase 03 verification
            # This ensures we don't miss potential vulnerabilities due to overly strict filtering
            reachability = prop.get("reachability", {})
            bug_bounty_scope = reachability.get("bug_bounty_scope", "unknown")

            if bug_bounty_scope == "out-of-scope":
                early_exit_results.append(self._build_skip_result(item, "out-of-scope"))
                continue

            # Severity gate — drop properties below the configured threshold
            if min_sev is not None:
                prop_severity = Severity.from_str(prop.get("severity", ""))
                if prop_severity is None or prop_severity < min_sev:
                    label = prop.get("severity", "(empty)")
                    early_exit_results.append(
                        self._build_skip_result(item, f"below min_severity ({label})")
                    )
                    severity_skipped += 1
                    continue

            items_to_process.append(item)

        if severity_skipped and min_sev is not None:
            print(f"  Severity gate: skipped {severity_skipped} properties below {min_sev.value}")

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

    def enrich_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Assign meaningful _id_prefix for checklist ID generation."""
        for item in items:
            prop_id = item.get("property_id", "")
            # Strip PROP- prefix to form the checklist slug
            slug = prop_id[5:] if prop_id.startswith("PROP-") else prop_id
            item["_id_prefix"] = f"CHK-{slug}"
        return items


class Phase02cOrchestrator(BaseOrchestrator):
    """Orchestrator for Phase 02c (Code Location Pre-resolution)."""
    
    def load_items(self) -> list[dict[str, Any]]:
        """Load checklist items from 02 partials with Pydantic validation."""
        import glob

        items = {}
        validation_warnings = 0

        # Simple pattern: read from Phase 02 outputs
        for filepath in sorted(glob.glob("outputs/02_PARTIAL_*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)

                # Validate the partial file structure using Pydantic
                try:
                    partial = Phase02Partial.model_validate(data)
                    print(
                        f"  ✓ {filepath}: {len(partial.checklist)} checklist items validated"
                    )
                except ValidationError as ve:
                    _log_validation_warning(filepath, ve, prefix="02→02c")
                    validation_warnings += 1

                # Extract checklist items
                checklist_items = data.get("checklist", [])
                for entry in checklist_items:
                    if not isinstance(entry, dict):
                        continue

                    # Validate individual checklist items
                    parsed_item, item_errors = validate_checklist_item(entry)
                    if item_errors:
                        check_id_raw = entry.get("check_id", "<unknown>")
                        for err in item_errors:
                            print(
                                f"    ⚠️  {filepath} item {check_id_raw}: {err}",
                                file=sys.stderr,
                            )

                    check_id = entry.get("check_id")
                    if not check_id:
                        continue

                    # Avoid duplicates (keep first occurrence)
                    if check_id not in items:
                        items[check_id] = {
                            "check_id": check_id,
                            "checklist_item": entry,
                            "source_file": filepath,
                        }

            except Exception as e:
                print(f"Warning: Failed to load {filepath}: {e}", file=sys.stderr)

        if validation_warnings:
            print(
                f"⚠️  {validation_warnings} file(s) had schema validation warnings (02→02c)",
                file=sys.stderr,
            )
        
        return list(items.values())


class Phase03Orchestrator(BaseOrchestrator):
    """
    Orchestrator for Phase 03 (Audit Map Generation).
    
    This is the reference implementation that other phases should follow.
    """
    
    def __init__(self, num_workers: int = 4, max_concurrent: int = 8):
        super().__init__("03", num_workers, max_concurrent)
        self.property_subgraph_map: dict[str, tuple[str | None, str]] = {}
    
    def load_items(self) -> list[dict[str, Any]]:
        """Load checklist items from 02c partials (with 02 as fallback) with Pydantic validation."""
        import glob

        # Build property to subgraph mapping
        self._build_property_subgraph_map()

        items = {}
        validation_warnings = 0

        # Priority: Read 02c first (with pre-resolved code locations), then 02 as fallback
        all_files = []
        all_files.extend(sorted(glob.glob("outputs/02c_PARTIAL_*.json")))
        all_files.extend(sorted(glob.glob("outputs/02_PARTIAL_*.json")))

        for filepath in all_files:
            try:
                with open(filepath) as f:
                    data = json.load(f)

                # Validate the partial file structure using Pydantic
                # Support both Phase02Partial (checklist) and Phase02cPartial (checklist_with_code)
                try:
                    if "02c" in filepath:
                        partial = Phase02cPartial.model_validate(data)
                        entries_raw = data.get("checklist_with_code", [])
                    else:
                        partial = Phase02Partial.model_validate(data)
                        entries_raw = data.get("checklist", [])
                except ValidationError as ve:
                    _log_validation_warning(filepath, ve, prefix="02c/02→03")
                    validation_warnings += 1
                    # Fall back to raw dict parsing
                    entries_raw = data.get("checklist_with_code") or data.get("checklist", [])

                for entry in entries_raw:
                    if not isinstance(entry, dict):
                        continue

                    # Validate individual checklist items
                    parsed_item, item_errors = validate_checklist_item(entry)
                    if item_errors:
                        check_id_raw = entry.get("check_id", "<unknown>")
                        for err in item_errors:
                            print(
                                f"    ⚠️  {filepath} item {check_id_raw}: {err}",
                                file=sys.stderr,
                            )

                    check_id = entry.get("check_id")
                    if not check_id:
                        continue

                    # Skip if already loaded from 02c (priority to pre-resolved items)
                    if check_id in items:
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

        if validation_warnings:
            print(
                f"⚠️  {validation_warnings} file(s) had schema validation warnings (02c/02→03)",
                file=sys.stderr,
            )
        
        return list(items.values())
    
    def _build_property_subgraph_map(self) -> None:
        """Build mapping from property_id to (subgraph_id, subgraph_file)."""
        import glob

        # Use renamed files (01e_PARTIAL_*.json)
        for prop_file in sorted(glob.glob("outputs/01e_PARTIAL_*.json")):
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
        """Apply early exit for out-of-scope items only."""
        early_exit_results = []
        items_to_process = []
        
        for item in items:
            checklist_item = item.get("checklist_item", {})
            code_scope = item.get("code_scope") or checklist_item.get("code_scope", {})

            if isinstance(code_scope, dict) and code_scope.get("resolution_status") == "out_of_scope":
                early_exit_results.append(self._build_early_exit_result(item, "out-of-scope"))
                continue

            items_to_process.append(item)
        
        return early_exit_results, items_to_process
    
    def _build_early_exit_result(self, item: dict[str, Any], reason: str) -> dict[str, Any]:
        """Build early exit result for out-of-scope items."""
        check_id = item.get("check_id")
        checklist_item = item.get("checklist_item", {})
        code_scope = item.get("code_scope") or checklist_item.get("code_scope", {})
        
        return {
            "check_id": check_id,
            "property_id": item.get("property_id"),
            "code_scope": code_scope,
            "final_classification": "out-of-scope",
            "bug_bounty_eligible": False,
            "summary": f"Early exit: {reason}.",
            "audit_trail": {
                "phase1_abstract_interpretation": {
                    "summary": f"Early exit: {reason}.",
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
        """Load audit results from 03 partials with Pydantic validation."""
        import glob
        
        items = []
        validation_warnings = 0
        for filepath in sorted(glob.glob("outputs/03_AUDITMAP_PARTIAL_*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)

                # Validate the partial file structure using Pydantic
                try:
                    Phase03Partial.model_validate(data)
                except ValidationError as ve:
                    _log_validation_warning(filepath, ve, prefix="03→04")
                    validation_warnings += 1

                audit_items = data.get("audit_items", [])
                for item in audit_items:
                    if isinstance(item, dict) and item.get("check_id"):
                        # Validate individual audit items
                        parsed, errs = validate_audit_map_item(item)
                        if errs:
                            for err in errs:
                                print(
                                    f"    ⚠️  {filepath} item {item.get('check_id', '?')}: {err}",
                                    file=sys.stderr,
                                )
                        items.append({
                            "check_id": item.get("check_id"),
                            "audit_result": item,
                            "source_file": filepath,
                        })
            except Exception as e:
                print(f"Warning: Failed to load {filepath}: {e}", file=sys.stderr)

        if validation_warnings:
            print(
                f"⚠️  {validation_warnings} file(s) had schema validation warnings (03→04)",
                file=sys.stderr,
            )
        
        return items
