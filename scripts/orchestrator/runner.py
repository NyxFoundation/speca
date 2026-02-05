"""
Claude Runner Module

Handles the execution of Claude CLI for batch processing.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import aiofiles

from .config import PhaseConfig


class ClaudeRunner:
    """
    Executes Claude CLI commands for batch processing.
    
    Features:
    - Async execution with semaphore-based concurrency control
    - Automatic retry on transient failures
    - Structured logging
    - Result parsing
    """
    
    def __init__(
        self,
        config: PhaseConfig,
        semaphore: asyncio.Semaphore,
        max_retries: int = 2,
    ):
        self.config = config
        self.semaphore = semaphore
        self.max_retries = max_retries
        
        # Ensure directories exist
        self.output_dir = Path("outputs")
        self.log_dir = self.output_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        Path(".claude/debug").mkdir(parents=True, exist_ok=True)
    
    async def run_batch(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> list[dict[str, Any]] | None:
        """
        Execute Claude CLI for a batch of items.
        
        Returns:
            List of results on success, None on failure.
        """
        async with self.semaphore:
            for attempt in range(self.max_retries + 1):
                try:
                    result = await self._execute_batch(batch, worker_id, batch_index)
                    if result is not None:
                        return result
                except Exception as e:
                    print(
                        f"[W{worker_id}] Batch {batch_index} attempt {attempt + 1} failed: {e}",
                        file=sys.stderr,
                    )
                
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
            
            return None
    
    async def _execute_batch(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> list[dict[str, Any]] | None:
        """Internal method to execute a single batch."""
        timestamp = int(time.time())
        phase_id = self.config.phase_id
        directory_mode = self.config.output_mode == "directory"

        # Create queue file
        prefix = self.config.output_prefix
        if prefix:
            partial_base = f"{phase_id}_{prefix}_PARTIAL"
        else:
            partial_base = f"{phase_id}_PARTIAL"
        queue_path = self.output_dir / f"{phase_id}_ASYNC_QUEUE_W{worker_id}B{batch_index}_{timestamp}.json"
        log_file = self.log_dir / f"{phase_id}_w{worker_id}b{batch_index}_{timestamp}.log.jsonl"

        # Determine output paths based on output_mode
        if directory_mode:
            # Worker writes .mmd files + index.json into a per-batch directory
            batch_output_dir = self.output_dir / "graphs" / f"W{worker_id}B{batch_index}_{timestamp}"
            batch_output_dir.mkdir(parents=True, exist_ok=True)
            result_parse_path = batch_output_dir / "index.json"
            output_kwargs: dict[str, str] = {"output_dir": str(batch_output_dir)}
        else:
            result_parse_path = self.output_dir / f"{partial_base}_W{worker_id}B{batch_index}_{timestamp}.json"
            output_kwargs = {"output_file": str(result_parse_path)}

        # Save queue
        queue_payload = self._build_queue_payload(batch, worker_id)
        self._save_json(queue_path, queue_payload)

        # Build prompt
        prompt_content = self._build_prompt(
            worker_id=worker_id,
            queue_file=str(queue_path),
            batch_size=len(batch),
            iteration=batch_index,
            timestamp=timestamp,
            **output_kwargs,
        )

        # Build command
        cmd = [
            "claude",
            "--dangerously-skip-permissions",
            "--verbose",
            "--output-format", "stream-json",
            "-p", prompt_content,
        ]

        # Build environment
        env = self._build_env(
            worker_id=worker_id,
            queue_file=str(queue_path),
            batch_size=len(batch),
            iteration=batch_index,
            timestamp=timestamp,
            **output_kwargs,
        )

        # Execute
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self.config.workdir or str(Path.cwd()),
        )

        try:
            # Stream stdout to log file
            async with aiofiles.open(log_file, mode="wb") as f:
                if proc.stdout:
                    while True:
                        chunk = await proc.stdout.read(65536)
                        if not chunk:
                            break
                        await f.write(chunk)

            await asyncio.wait_for(proc.wait(), timeout=self.config.timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            print(f"[W{worker_id}] Batch {batch_index} timed out", file=sys.stderr)
            return None

        # Check result
        if proc.returncode != 0:
            stderr = await proc.stderr.read() if proc.stderr else b""
            self._save_error_log(worker_id, batch_index, timestamp, proc.returncode, stderr)
            print(
                f"[W{worker_id}] Claude failed for batch {batch_index} (exit {proc.returncode})",
                file=sys.stderr,
            )
            return None

        # Parse results from output file / index.json, fallback to log
        results = self._parse_results(result_parse_path)
        if not results:
            results = self._parse_results_from_log(log_file)
            if results:
                print(
                    f"[W{worker_id}] Batch {batch_index}: recovered {len(results)} result(s) from inline response",
                    file=sys.stderr,
                )

        # Clean up: delete intermediate file only in file mode
        # In directory mode the .mmd files must be preserved
        if not directory_mode and result_parse_path.exists():
            result_parse_path.unlink()

        return results
    
    def _build_queue_payload(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
    ) -> dict[str, Any]:
        """Build the queue payload for Claude."""
        return {
            "worker_id": worker_id,
            "phase": self.config.phase_id,
            "items": batch,
            "total_items": len(batch),
        }
    
    def _build_prompt(self, **kwargs) -> str:
        """Build the prompt content with arguments."""
        # Read base prompt
        with open(self.config.prompt_path) as f:
            prompt_content = f.read()
        
        # Append arguments
        args = " ".join(f"{k.upper()}={v}" for k, v in kwargs.items())
        return f"{prompt_content}\n\n{args}"
    
    def _build_env(self, **kwargs) -> dict[str, str]:
        """Build environment variables for Claude execution."""
        env = os.environ.copy()
        
        # Add standard Claude environment variables
        env.update({
            "CLAUDE_CODE_PERMISSIONS": "bypassPermissions",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "100000",
        })
        
        # Add phase-specific variables
        for key, value in kwargs.items():
            env[key.upper()] = str(value)
        
        return env
    
    def _save_json(self, path: Path, data: Any) -> None:
        """Save JSON data to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _save_error_log(
        self,
        worker_id: int,
        batch_index: int,
        timestamp: int,
        exit_code: int,
        stderr: bytes,
    ) -> None:
        """Save error information for debugging."""
        error_log_file = self.log_dir / f"{self.config.phase_id}_w{worker_id}b{batch_index}_{timestamp}.error.log"
        
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
        
        # Try to get debug info
        debug_text = ""
        debug_latest = Path(".claude/debug/latest")
        try:
            if debug_latest.exists():
                debug_text = debug_latest.read_text(errors="replace")
        except Exception:
            pass
        
        with open(error_log_file, "w") as f:
            f.write(f"exit_code={exit_code}\n")
            if stderr_text:
                f.write("\n[stderr]\n")
                f.write(stderr_text)
            if debug_text:
                f.write("\n[claude_debug_latest]\n")
                f.write(debug_text)
    
    def _normalize_result_data(self, data: Any) -> list[dict[str, Any]]:
        """
        Normalize parsed JSON data into a flat list of result dicts.

        Handles both raw lists and wrapper dicts with a known result key
        (e.g. {"sub_graphs": [...]}).
        """
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        if isinstance(data, dict):
            for key in [self.config.result_key, "items", "results", "audit_items", "graphs", "specs"]:
                if key in data and isinstance(data[key], list):
                    return [item for item in data[key] if isinstance(item, dict)]
            # If no known key matched, return the dict itself as a single-item list
            return [data]

        return []

    def _parse_results_from_log(self, log_file: Path) -> list[dict[str, Any]]:
        """
        Fallback: extract results from inline text in the Claude CLI log.

        When Claude returns results as markdown text (```json blocks) instead
        of writing to the output file, this method recovers those results from
        the stream-json log.
        """
        import re

        if not log_file.exists():
            return []

        # Find the final "result" message in the JSONL log
        result_text = ""
        try:
            with open(log_file) as f:
                for line in f:
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "result" and msg.get("result"):
                            result_text = msg["result"]
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            return []

        if not result_text:
            return []

        # Extract JSON from ```json ... ``` blocks
        json_blocks = re.findall(r"```json\s*(.*?)```", result_text, re.DOTALL)

        results: list[dict[str, Any]] = []
        for block in json_blocks:
            try:
                data = json.loads(block.strip())
            except json.JSONDecodeError:
                continue
            results.extend(self._normalize_result_data(data))

        return results

    def _parse_results(self, output_path: Path) -> list[dict[str, Any]]:
        """Parse results from output file."""
        if not output_path.exists():
            return []

        try:
            with open(output_path) as f:
                data = json.load(f)
        except Exception:
            return []

        return self._normalize_result_data(data)
