#!/usr/bin/env python3
"""
Phase 03 Audit Map Async Orchestrator

This script handles phase 03 using asyncio to parallelize claude CLI calls,
while maintaining the subscription-based billing model.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import aiofiles
from tqdm import tqdm

OUTPUT_DIR = Path("outputs")
LOG_DIR = OUTPUT_DIR / "logs"
SKILL_PATH = Path(".claude/skills/formal-audit/SKILL.md")
CHECKLIST_PARTIALS_PATTERN = "outputs/02_CHECKLIST_PARTIAL_*.json"
PROPERTY_PARTIALS_PATTERN = "outputs/01e_PROP_PARTIAL_*.json"
MAX_CONTEXT_TOKENS = 190_000  # Safety margin for 200K context window
BASE_PROMPT_TOKENS = 5_000  # Estimated tokens for skill prompt + prompt template
PROMPT_FILE = Path("prompts/03_auditmap_worker.md")


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def estimate_tokens(text: str) -> int:
    """A simple estimation of token count."""
    return len(text) // 4


def build_property_to_subgraph_map_via_elements(
    property_files_pattern: str,
) -> dict[str, tuple[str | None, str]]:
    """
    Build a map from property_id to (subgraph_id, subgraph_file).

    For each property file:
    1. Load metadata.source_files (subgraph files used in this batch)
    2. Load all those subgraph files into memory
    3. For each property, find which subgraph contains its primary element
    4. Record the mapping
    """
    import glob

    property_to_subgraph: dict[str, tuple[str | None, str]] = {}

    for prop_file in sorted(glob.glob(property_files_pattern)):
        prop_data = load_json(Path(prop_file)) or {}
        source_files = prop_data.get("metadata", {}).get("source_files", [])

        subgraph_cache: dict[str, dict[str, Any]] = {}
        for sg_file in source_files:
            if os.path.exists(sg_file):
                subgraph_cache[sg_file] = load_json(Path(sg_file)) or {}

        for prop in prop_data.get("properties", []):
            if not isinstance(prop, dict):
                continue
            prop_id = prop.get("id")
            if not prop_id:
                continue

            covers = prop.get("covers", {})
            primary_element = covers.get("primary_element")
            if not primary_element:
                edges = covers.get("edges", [])
                nodes = covers.get("nodes", [])
                if edges:
                    primary_element = edges[0]
                elif nodes:
                    primary_element = nodes[0]

            if not primary_element:
                continue

            found = False
            for sg_file, sg_data in subgraph_cache.items():
                for subgraph in sg_data.get("sub_graphs", []):
                    edge_ids = [e.get("id") for e in subgraph.get("edges", [])]
                    node_ids = [n.get("id") for n in subgraph.get("nodes", [])]
                    if primary_element in edge_ids or primary_element in node_ids:
                        subgraph_id = subgraph.get("id")
                        if subgraph_id:
                            property_to_subgraph[prop_id] = (subgraph_id, sg_file)
                            found = True
                            break
                if found:
                    break

                for ambiguity in sg_data.get("ambiguities", []):
                    if ambiguity.get("id") == primary_element:
                        property_to_subgraph[prop_id] = (None, sg_file)
                        found = True
                        break
                if found:
                    break

                for assumption in sg_data.get("implicit_assumptions", []):
                    if assumption.get("id") == primary_element:
                        property_to_subgraph[prop_id] = (None, sg_file)
                        found = True
                        break
                if found:
                    break

    return property_to_subgraph


def build_queue_payload(items: List[Dict[str, Any]], worker_id: int, total_workers: int) -> Dict[str, Any]:
    return {
        "worker_id": worker_id,
        "phase": "03",
        "total_workers": total_workers,
        "items": items,
        "processed": [],
        "total_items": len(items),
    }


def parse_audit_results(output_path: Path) -> List[Dict[str, Any]]:
    data = load_json(output_path)
    if data is None:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        audit_items = data.get("audit_items")
        if isinstance(audit_items, list):
            return [item for item in audit_items if isinstance(item, dict)]
    return []


class AuditOrchestratorAsync:
    def __init__(self, num_workers: int, max_concurrent: int):
        self.num_workers = max(1, num_workers)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.results: List[Dict[str, Any]] = []
        self.all_checklist_items: Dict[str, Dict[str, Any]] = {}
        self.property_subgraph_map: Dict[str, Tuple[str | None, str]] = {}
        self._batch_counter = 0

    def _load_all_checklist_items(self) -> None:
        import glob

        print("Loading all checklist items...")
        self.property_subgraph_map = build_property_to_subgraph_map_via_elements(
            PROPERTY_PARTIALS_PATTERN
        )

        items: dict[str, Dict[str, Any]] = {}
        for filepath in sorted(glob.glob(CHECKLIST_PARTIALS_PATTERN)):
            data = load_json(Path(filepath)) or {}
            entries = data.get("checklist_items") or data.get("checklist") or []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                check_id = entry.get("id") or entry.get("check_id")
                if not check_id:
                    continue

                item: Dict[str, Any] = {
                    "check_id": check_id,
                    "checklist_item": entry,
                    "checklist_file": filepath,
                }
                if "property_id" in entry:
                    item["property_id"] = entry.get("property_id")
                if "code_scope" in entry:
                    item["code_scope"] = entry.get("code_scope")

                property_id = entry.get("property_id")
                if property_id:
                    subgraph_info = self.property_subgraph_map.get(property_id)
                    if subgraph_info:
                        subgraph_id, subgraph_file = subgraph_info
                        item["subgraph_id"] = subgraph_id
                        item["subgraph_file"] = subgraph_file

                items[check_id] = item

        self.all_checklist_items = items

    def _is_early_exit(self, item: Dict[str, Any]) -> bool:
        checklist_item = item.get("checklist_item")
        property_id = item.get("property_id")
        if not property_id and isinstance(checklist_item, dict):
            property_id = checklist_item.get("property_id")
        return not property_id

    def _create_token_based_batches(self, items: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        print("Creating token-based batches...")
        batches: List[List[Dict[str, Any]]] = []
        current_batch: List[Dict[str, Any]] = []
        current_batch_tokens = BASE_PROMPT_TOKENS
        subgraph_cache: Dict[str, Dict[str, Any]] = {}

        for item in items:
            enriched_item = item.copy()
            relevant_subgraph = self._get_relevant_subgraph(item, subgraph_cache)
            if relevant_subgraph:
                enriched_item["subgraph"] = relevant_subgraph

            item_json = json.dumps(enriched_item)
            item_tokens = estimate_tokens(item_json)

            if current_batch and (current_batch_tokens + item_tokens > MAX_CONTEXT_TOKENS):
                batches.append(current_batch)
                current_batch = []
                current_batch_tokens = BASE_PROMPT_TOKENS

            current_batch.append(enriched_item)
            current_batch_tokens += item_tokens

        if current_batch:
            batches.append(current_batch)

        print(f"Created {len(batches)} batches.")
        return batches

    def _build_early_exit_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        check_id = item.get("check_id")
        checklist_item = item.get("checklist_item") if isinstance(item.get("checklist_item"), dict) else {}
        code_scope = item.get("code_scope") or checklist_item.get("code_scope") or {}

        return {
            "check_id": check_id,
            "property_id": item.get("property_id") or checklist_item.get("property_id"),
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
                "phase2_5_reachability_analysis": {
                    "summary": "Not performed due to early exit.",
                    "entry_points": [],
                    "data_flow_path": "",
                    "validation_layers": [],
                    "attacker_controlled": False,
                    "classification": "unreachable",
                    "notes": "",
                },
                "phase3_invariant_proving": {
                    "summary": "Not performed due to early exit.",
                    "proof_successful": False,
                    "guard_identified": None,
                },
                "phase3_5_scope_filtering": {
                    "bug_bounty_eligible": False,
                    "reason": "out-of-scope",
                    "recommendation": "",
                    "notes": "",
                },
            },
        }

    def _get_relevant_subgraph(
        self,
        item: Dict[str, Any],
        subgraph_cache: Dict[str, Dict[str, Any]] | None = None,
    ) -> Dict[str, Any] | None:
        subgraph_file = item.get("subgraph_file")
        subgraph_id = item.get("subgraph_id")
        if not subgraph_file or not subgraph_id:
            return None

        if subgraph_cache is not None:
            if subgraph_file not in subgraph_cache:
                subgraph_cache[subgraph_file] = load_json(Path(subgraph_file)) or {}
            sg_data = subgraph_cache[subgraph_file]
        else:
            sg_data = load_json(Path(subgraph_file)) or {}
        for sg in sg_data.get("sub_graphs", []):
            if sg.get("id") == subgraph_id:
                return sg
        return None

    async def _run_claude_cli(
        self,
        batch: List[Dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> List[Dict[str, Any]]:
        async with self.semaphore:
            timestamp = int(time.time())
            batch_size = len(batch)
            LOG_DIR.mkdir(parents=True, exist_ok=True)

            queue_path = OUTPUT_DIR / f"03_ASYNC_QUEUE_W{worker_id}B{batch_index}_{timestamp}.json"
            output_path = OUTPUT_DIR / f"03_AUDITMAP_PARTIAL_W{worker_id}B{batch_index}_{timestamp}.json"
            log_file = (
                LOG_DIR / f"03_auditmap_w{worker_id}b{batch_index}_{timestamp}.log.jsonl"
            )

            save_json(queue_path, build_queue_payload(batch, worker_id, self.num_workers))

            with open(PROMPT_FILE) as f:
                prompt_content = f.read()

            extra_args = (
                f"WORKER_ID={worker_id} QUEUE_FILE={queue_path} "
                f"BATCH_SIZE={batch_size} OUTPUT_FILE={output_path} "
                f"ITERATION={batch_index} TIMESTAMP={timestamp}"
            )
            prompt_content = f"{prompt_content}\n\n{extra_args}"

            cmd = [
                "claude",
                "--dangerously-skip-permissions",
                "--output-format",
                "stream-json",
                "-p",
                prompt_content,
            ]

            env = os.environ.copy()
            env.update(
                {
                    "WORKER_ID": str(worker_id),
                    "QUEUE_FILE": str(queue_path),
                    "BATCH_SIZE": str(batch_size),
                    "OUTPUT_FILE": str(output_path),
                    "ITERATION": str(batch_index),
                    "TIMESTAMP": str(timestamp),
                    "CLAUDE_CODE_PERMISSIONS": "bypassPermissions",
                    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "100000",
                }
            )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(Path.cwd()),
            )
            try:
                async with aiofiles.open(log_file, mode="wb") as f:
                    if proc.stdout:
                        while True:
                            line = await proc.stdout.readline()
                            if not line:
                                break
                            await f.write(line)
                await asyncio.wait_for(proc.wait(), timeout=3600)
            except asyncio.TimeoutError:
                proc.kill()
                return []

            stderr = await proc.stderr.read() if proc.stderr else b""
            if stderr:
                error_log_file = (
                    LOG_DIR
                    / f"03_auditmap_w{worker_id}b{batch_index}_{timestamp}.error.log"
                )
                try:
                    error_log_file.write_bytes(stderr)
                except Exception:
                    pass

            if proc.returncode != 0:
                print(
                    f"[W{worker_id}] Claude failed for batch {batch_index} (exit {proc.returncode})",
                    file=sys.stderr,
                )
                return []

            results = parse_audit_results(output_path)
            if not results:
                print(
                    f"[W{worker_id}] No audit results found for batch {batch_index}",
                    file=sys.stderr,
                )
            return results

    async def run(self) -> None:
        self._load_all_checklist_items()

        full_audit_queue: List[Dict[str, Any]] = []
        early_exit_results: List[Dict[str, Any]] = []

        for item in self.all_checklist_items.values():
            if self._is_early_exit(item):
                early_exit_results.append(self._build_early_exit_result(item))
            else:
                full_audit_queue.append(item)

        print(f"Identified {len(early_exit_results)} items for early exit.")
        print(f"Sending {len(full_audit_queue)} items for full audit.")

        batches = self._create_token_based_batches(full_audit_queue)

        tasks = []
        task_sizes: Dict[asyncio.Task[List[Dict[str, Any]]], int] = {}
        for batch in batches:
            worker_id = self._batch_counter % self.num_workers
            self._batch_counter += 1
            task = asyncio.create_task(
                self._run_claude_cli(batch, worker_id, self._batch_counter)
            )
            tasks.append(task)
            task_sizes[task] = len(batch)

        if tasks:
            total_items = len(full_audit_queue)
            with tqdm(total=total_items, desc="Auditing Items", unit="item") as pbar:
                for task in asyncio.as_completed(tasks):
                    result = await task
                    self.results.extend(result)
                    pbar.update(task_sizes.get(task, 0))

        final_results = early_exit_results + self.results
        timestamp = int(time.time())
        final_output_path = OUTPUT_DIR / f"03_AUDITMAP_FINAL_{timestamp}.json"
        save_json(final_output_path, {"audit_results": final_results})
        print(f"Orchestration complete. Final results saved to {final_output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-concurrent", type=int, default=4)
    args = parser.parse_args()

    orchestrator = AuditOrchestratorAsync(args.workers, args.max_concurrent)
    asyncio.run(orchestrator.run())


if __name__ == "__main__":
    main()
