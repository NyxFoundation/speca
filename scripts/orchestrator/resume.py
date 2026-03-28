"""
Resume Manager Module

Scans existing PARTIAL files or directory outputs to identify already-processed items,
enabling incremental re-execution of a phase.
"""

import glob
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from .config import PhaseConfig
from .paths import get_output_root


class ResumeManager:
    """
    Determines which items have already been processed by inspecting
    PARTIAL output files on disk.

    Usage in BaseOrchestrator.run():
        remaining, skipped = self.resume_manager.filter_remaining(all_items)
    """

    def __init__(self, config: PhaseConfig):
        self.config = config
        self.output_dir = get_output_root()
        self.logs_dir = self.output_dir / "logs"

    def get_processed_ids(self) -> set[str]:
        """
        Scan PARTIAL output files and extract IDs from result items.

        Falls back to ``metadata.processed_ids`` when present (faster
        path for future runs where the collector records IDs explicitly).

        Corrupted files are logged and skipped.
        """
        return self._get_processed_ids_from_partial_files()

    def _get_processed_ids_from_partial_files(self) -> set[str]:
        """
        Scan {phase_id}_PARTIAL_*.json files for processed IDs.
        """
        pattern = str(self.output_dir / f"{self.config.phase_id}_PARTIAL_*.json")
        id_field = self.config.effective_result_id_field
        result_key = self.config.result_key
        processed: set[str] = set()

        for filepath in sorted(glob.glob(pattern)):
            try:
                with open(filepath, encoding="utf-8") as f:
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

    def get_incomplete_batches(self) -> list[Path]:
        """
        Find batch directories that have mmd files but no corresponding
        PARTIAL file.

        These are considered incomplete and should be cleaned up before
        re-processing to avoid conflicts.

        Returns:
            List of paths to incomplete batch directories
        """
        if self.config.output_mode != "directory":
            return []

        graphs_dir = self.output_dir / "graphs"
        if not graphs_dir.exists():
            return []

        # Build set of W{n}B{m} prefixes referenced by existing PARTIAL files
        partial_pattern = str(self.output_dir / f"{self.config.phase_id}_PARTIAL_*.json")
        referenced_prefixes: set[str] = set()
        for filepath in glob.glob(partial_pattern):
            match = re.search(r"(W\d+B\d+)", Path(filepath).name, re.IGNORECASE)
            if match:
                referenced_prefixes.add(match.group(1).upper())

        incomplete: list[Path] = []
        for batch_dir in graphs_dir.iterdir():
            if not batch_dir.is_dir():
                continue
            has_mmd = any(batch_dir.rglob("*.mmd"))
            if not has_mmd:
                continue
            dir_prefix_match = re.search(r"(W\d+B\d+)", batch_dir.name, re.IGNORECASE)
            dir_prefix = dir_prefix_match.group(1).upper() if dir_prefix_match else ""
            if dir_prefix not in referenced_prefixes:
                incomplete.append(batch_dir)

        return incomplete

    def _get_log_files_for_batch(self, batch_dir: Path) -> list[Path]:
        """
        Find log files corresponding to a batch directory.
        
        Batch directory name format: W{worker}B{batch}_{timestamp}
        Log file name format: {phase_id}_w{worker}b{batch}_{timestamp}.log.jsonl
        
        Args:
            batch_dir: Path to the batch directory (e.g., outputs/graphs/W0B9_1770272943)
        
        Returns:
            List of paths to corresponding log files
        """
        if not self.logs_dir.exists():
            return []

        batch_name = batch_dir.name  # e.g., W0B9_1770272943
        # Convert to lowercase for log file matching: w0b9_1770272943
        batch_name_lower = batch_name.lower()
        
        # Pattern: {phase_id}_{batch_name_lower}*.log.jsonl
        phase_id = self.config.phase_id.lower()
        pattern = f"{phase_id}_{batch_name_lower}*.log.jsonl"
        
        log_files: list[Path] = []
        for log_file in self.logs_dir.glob(pattern):
            log_files.append(log_file)
        
        return log_files

    def cleanup_incomplete_batches(self, dry_run: bool = True) -> dict[str, list[Path]]:
        """
        Remove incomplete batch directories (mmd files without matching
        PARTIAL file) and their corresponding log files.
        
        Args:
            dry_run: If True, only report what would be deleted without actually deleting.
        
        Returns:
            Dictionary with 'batches' and 'logs' keys containing lists of deleted paths
        """
        incomplete = self.get_incomplete_batches()
        
        deleted: dict[str, list[Path]] = {
            "batches": [],
            "logs": [],
        }
        
        for batch_dir in incomplete:
            mmd_count = len(list(batch_dir.rglob("*.mmd")))
            log_files = self._get_log_files_for_batch(batch_dir)
            
            if dry_run:
                print(f"Would delete batch: {batch_dir} ({mmd_count} mmd files)")
                for log_file in log_files:
                    print(f"  Would delete log: {log_file.name}")
            else:
                print(f"Deleting batch: {batch_dir} ({mmd_count} mmd files)")
                shutil.rmtree(batch_dir)
                deleted["batches"].append(batch_dir)
                
                for log_file in log_files:
                    print(f"  Deleting log: {log_file.name}")
                    log_file.unlink()
                    deleted["logs"].append(log_file)

        return deleted

    def get_cleanup_summary(self) -> dict[str, Any]:
        """
        Get a summary of what would be cleaned up without actually deleting.
        
        Returns:
            Dictionary with summary information
        """
        incomplete = self.get_incomplete_batches()
        
        summary = {
            "incomplete_batches": len(incomplete),
            "total_mmd_files": 0,
            "total_log_files": 0,
            "batches": [],
        }
        
        for batch_dir in incomplete:
            mmd_count = len(list(batch_dir.rglob("*.mmd")))
            log_files = self._get_log_files_for_batch(batch_dir)
            
            summary["total_mmd_files"] += mmd_count
            summary["total_log_files"] += len(log_files)
            summary["batches"].append({
                "name": batch_dir.name,
                "mmd_files": mmd_count,
                "log_files": [f.name for f in log_files],
            })
        
        return summary

    def cleanup_all_outputs(self, dry_run: bool = True) -> int:
        """
        Delete ALL output files and logs for this phase.
        Used when --force is specified to ensure a clean run.

        Returns:
            Number of files/directories deleted.
        """
        count = 0
        # Track already-counted log files to avoid double-counting
        counted_logs: set[str] = set()

        # 1. Delete PARTIAL files (file mode)
        pattern = str(self.output_dir / f"{self.config.phase_id}_PARTIAL_*.json")
        for filepath in glob.glob(pattern):
            if dry_run:
                print(f"Would delete: {filepath}")
            else:
                Path(filepath).unlink()
                print(f"Deleted: {filepath}")
            count += 1

        # 2. Delete directory outputs (directory mode)
        if self.config.output_mode == "directory":
             graphs_dir = self.output_dir / "graphs"
             if graphs_dir.exists():
                 # Phase 01b is the only phase using directory mode.
                 # Safe approach: check if log files for this batch match the phase.
                 for batch_dir in graphs_dir.iterdir():
                     if not batch_dir.is_dir(): continue
                     logs = self._get_log_files_for_batch(batch_dir)
                     # correct phase logs exist for this batch?
                     if logs:
                         if dry_run:
                             print(f"Would delete batch: {batch_dir}")
                             for log in logs:
                                 print(f"  Would delete log: {log}")
                                 counted_logs.add(str(log))
                         else:
                             shutil.rmtree(batch_dir)
                             print(f"Deleted batch: {batch_dir}")
                             for log in logs:
                                 counted_logs.add(str(log))
                                 log.unlink()
                                 print(f"Deleted log: {log}")
                             count += 1

        # 3. Delete leftover logs (file mode or orphaned)
        # _get_log_files_for_batch handles directory mode logs.
        # For file mode, logs are: {phase_id}_w{worker}b{batch}_{timestamp}.log.jsonl
        log_pattern = str(self.logs_dir / f"{self.config.phase_id}_*.log.jsonl")
        for logpath in glob.glob(log_pattern):
             if str(Path(logpath)) in counted_logs:
                 continue  # Already counted/deleted in directory mode
             if Path(logpath).exists():
                if dry_run:
                    print(f"Would delete log: {logpath}")
                else:
                    Path(logpath).unlink()
                    print(f"Deleted log: {logpath}")
                count += 1

        return count

