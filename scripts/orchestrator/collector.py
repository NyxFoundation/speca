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
    - Aggregate results from multiple batches
    - Save partial and final results
    - Generate summary statistics
    """
    
    def __init__(self, config: PhaseConfig):
        self.config = config
        self.output_dir = Path("outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def save(self, results: list[dict[str, Any]]) -> Path:
        """
        Save results to the output file.
        
        Returns:
            Path to the saved file.
        """
        timestamp = int(time.time())
        output_path = self.output_dir / f"{self.config.phase_id}_FINAL_{timestamp}.json"
        
        output_data = {
            self.config.result_key: results,
            "metadata": {
                "phase": self.config.phase_id,
                "phase_name": self.config.name,
                "total_items": len(results),
                "timestamp": timestamp,
                "summary": self._generate_summary(results),
            },
        }
        
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        
        print(f"Results saved to: {output_path}")
        return output_path
    
    def save_partial(
        self,
        results: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> Path:
        """Save partial results from a single batch."""
        timestamp = int(time.time())
        output_path = self.output_dir / f"{self.config.phase_id}_PARTIAL_W{worker_id}B{batch_index}_{timestamp}.json"
        
        output_data = {
            self.config.result_key: results,
            "metadata": {
                "phase": self.config.phase_id,
                "worker_id": worker_id,
                "batch_index": batch_index,
                "item_count": len(results),
                "timestamp": timestamp,
            },
        }
        
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        
        return output_path
    
    def _generate_summary(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate summary statistics for results."""
        summary: dict[str, Any] = {
            "total": len(results),
        }
        
        # Phase-specific summaries
        if self.config.phase_id == "03":
            summary.update(self._summarize_audit_results(results))
        elif self.config.phase_id == "04":
            summary.update(self._summarize_review_results(results))
        elif self.config.phase_id == "02":
            summary.update(self._summarize_checklist(results))
        
        return summary
    
    def _summarize_audit_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Summarize Phase 03 audit results."""
        classifications = {}
        bug_bounty_eligible = 0
        
        for result in results:
            classification = result.get("final_classification", "unknown")
            classifications[classification] = classifications.get(classification, 0) + 1
            
            if result.get("bug_bounty_eligible"):
                bug_bounty_eligible += 1
        
        return {
            "by_classification": classifications,
            "bug_bounty_eligible": bug_bounty_eligible,
        }
    
    def _summarize_review_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Summarize Phase 04 review results."""
        verdicts = {}
        
        for result in results:
            verdict = result.get("review_verdict", "unknown")
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
        
        return {
            "by_verdict": verdicts,
        }
    
    def _summarize_checklist(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """Summarize Phase 02 checklist results."""
        severities = {}
        
        for result in results:
            severity = result.get("severity", "unknown")
            severities[severity] = severities.get(severity, 0) + 1
        
        return {
            "by_severity": severities,
        }


def merge_partial_results(
    phase_id: str,
    output_path: Path | None = None,
) -> Path:
    """
    Merge all partial results for a phase into a single file.
    
    This is useful for combining results from multiple workers.
    """
    import glob
    
    output_dir = Path("outputs")
    pattern = f"{phase_id}_PARTIAL_*.json"
    
    all_results = []
    source_files = []
    
    for filepath in sorted(glob.glob(str(output_dir / pattern))):
        try:
            with open(filepath) as f:
                data = json.load(f)
            
            # Find the result key
            for key in ["items", "found_specs", "sub_graphs", "trust_model",
                        "checklist", "properties", "audit_items", "reviewed_items"]:
                if key in data and isinstance(data[key], list):
                    all_results.extend(data[key])
                    source_files.append(filepath)
                    break
        except Exception as e:
            print(f"Warning: Failed to load {filepath}: {e}")
    
    # Deduplicate by ID
    seen_ids = set()
    unique_results = []
    
    for result in all_results:
        # Try different ID fields
        result_id = result.get("check_id") or result.get("id") or result.get("property_id")
        if result_id:
            if result_id not in seen_ids:
                seen_ids.add(result_id)
                unique_results.append(result)
        else:
            unique_results.append(result)
    
    # Save merged results
    timestamp = int(time.time())
    if output_path is None:
        output_path = output_dir / f"{phase_id}_MERGED_{timestamp}.json"
    
    output_data = {
        "items": unique_results,
        "metadata": {
            "phase": phase_id,
            "total_items": len(unique_results),
            "source_files": source_files,
            "timestamp": timestamp,
        },
    }
    
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"Merged {len(unique_results)} results from {len(source_files)} files to: {output_path}")
    return output_path
