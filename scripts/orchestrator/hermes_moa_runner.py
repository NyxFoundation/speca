"""Hermes Mixture-of-Agents runner (speca#88 a/b/c-3).

Runs one phase batch through THREE independent models and fuses their results
with the recall-first union+cross-verify aggregation in :mod:`orchestrator.moa`
(method b). The 3 models are ollama-cloud models reached over the OpenAI-
compatible ``ollama.com/v1`` endpoint using the ``OLLAMA_API_KEY`` credential
(the same key the Hermes agent manages for its ollama-cloud provider — export
it into the env before running; no key is committed).

Each sub-model is a plain :class:`OllamaAPIRunner` (its own agentic tool loop
over the target codebase — tool-calling verified on all 3 models); this runner
just fans a batch out to the three and fuses.

Config (env):
- ``OLLAMA_API_KEY``          ollama-cloud bearer (required).
- ``OLLAMA_BASE_URL``         endpoint (default ``https://ollama.com/v1``).
- ``SPECA_HERMES_MOA_MODELS`` comma-separated model list
                              (default ``deepseek-v4-pro,qwen3.5:397b,kimi-k2.7-code``).
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from .api_runner import OllamaAPIRunner
from .config import PhaseConfig
from .moa import aggregate
from .runner import CircuitBreaker, CircuitBreakerTripped, BudgetExceeded
from .watchdog import CostTracker

DEFAULT_PROXY_URL = "https://ollama.com/v1"
DEFAULT_MODELS = ("deepseek-v4-pro", "qwen3.5:397b", "kimi-k2.7-code")


def resolve_models() -> list[str]:
    raw = os.environ.get("SPECA_HERMES_MOA_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(DEFAULT_MODELS)


class HermesMoARunner:
    """Fan a batch out to N Hermes-proxied models and fuse (moa.aggregate)."""

    def __init__(
        self,
        config: PhaseConfig,
        semaphore: asyncio.Semaphore,
        max_retries: int = 2,
        circuit_breaker: CircuitBreaker | None = None,
        cost_tracker: CostTracker | None = None,
    ):
        self.config = config
        self.semaphore = semaphore
        self.circuit_breaker = circuit_breaker or CircuitBreaker(config)
        self.cost_tracker = cost_tracker
        self.models = resolve_models()
        base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_PROXY_URL)
        api_key = os.environ.get("OLLAMA_API_KEY", "")
        # Each member shares the circuit breaker / cost tracker so systemic
        # issues (endpoint down, budget) trip once for the whole MoA.
        self.members: dict[str, OllamaAPIRunner] = {
            model: OllamaAPIRunner(
                config,
                semaphore,
                max_retries=max_retries,
                circuit_breaker=self.circuit_breaker,
                cost_tracker=cost_tracker,
                base_url=base_url,
                api_key=api_key,
                model=model,
            )
            for model in self.models
        }
        self.model = "+".join(self.models)  # for logging parity with APIRunner

    async def run_batch(
        self, batch: list[dict[str, Any]], worker_id: int, batch_index: int
    ) -> list[dict[str, Any]] | None:
        """Run the batch through every member concurrently, then fuse.

        A member that errors (or trips the circuit) resolves to ``None`` and is
        excluded from the fusion — as long as at least one member returned, the
        recall-first aggregation still yields results. Budget/circuit-breaker
        exceptions propagate (they are systemic, not per-member).
        """
        async def _one(model: str, runner: OllamaAPIRunner):
            try:
                return model, await runner.run_batch(batch, worker_id, batch_index)
            except (CircuitBreakerTripped, BudgetExceeded):
                raise
            except Exception as e:  # noqa: BLE001 — one model failing must not kill the MoA
                print(
                    f"[W{worker_id}] MoA member {model} failed on batch "
                    f"{batch_index}: {e}",
                    file=sys.stderr,
                )
                return model, None

        settled = await asyncio.gather(
            *(_one(m, r) for m, r in self.members.items())
        )
        per_model = {m: res for m, res in settled if res}
        if not per_model:
            return None  # every member failed → treat as a failed batch

        fused = aggregate(per_model, id_field=self.config.item_id_field)
        flagged = sum(1 for f in fused if f.get("moa", {}).get("flagged_by"))
        print(
            f"[W{worker_id}] MoA batch {batch_index}: "
            f"{len(per_model)}/{len(self.members)} models -> {len(fused)} fused "
            f"({flagged} flagged)",
            file=sys.stderr,
        )
        return fused
