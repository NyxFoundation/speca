"""Hermes Mixture-of-Agents runner (speca#88 a/b/c-3).

Runs one phase batch through THREE independent models and fuses their results
with the recall-first union+cross-verify aggregation in :mod:`orchestrator.moa`
(method b). The models are reached through the Hermes agent's OpenAI-compatible
proxy (``hermes proxy``), which routes to ollama-cloud, so no provider API key
lives in speca's environment.

Each sub-model is a plain :class:`APIRunner` (its own agentic tool loop over the
target codebase); this runner just fans a batch out to the three and fuses.

Config (env):
- ``SPECA_HERMES_PROXY_URL``  OpenAI-compatible base url of ``hermes proxy``
                              (default ``http://127.0.0.1:11435/v1``).
- ``SPECA_HERMES_MOA_MODELS`` comma-separated model list
                              (default ``deepseek-v4-pro,qwen3.5:397b,kimi-k2.7-code``).
- ``SPECA_HERMES_PROXY_KEY``  optional bearer the proxy expects (default none).
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from .api_runner import APIRunner
from .config import PhaseConfig
from .moa import aggregate
from .runner import CircuitBreaker, CircuitBreakerTripped, BudgetExceeded
from .watchdog import CostTracker

DEFAULT_PROXY_URL = "http://127.0.0.1:11435/v1"
DEFAULT_MODELS = ("deepseek-v4-pro", "qwen3.5:397b", "kimi-k2.7-code")


def resolve_models() -> list[str]:
    raw = os.environ.get("SPECA_HERMES_MOA_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(DEFAULT_MODELS)


class _HermesModel(APIRunner):
    """One MoA member: an APIRunner pointed at the Hermes proxy for one model."""

    DEFAULT_BASE_URL = DEFAULT_PROXY_URL
    DEFAULT_MODEL = DEFAULT_MODELS[0]
    BASE_URL_ENV = "SPECA_HERMES_PROXY_URL"
    API_KEY_ENV = "SPECA_HERMES_PROXY_KEY"
    MODEL_ENV = "SPECA_HERMES_MODEL_UNUSED"  # model is passed explicitly per member


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
        base_url = os.environ.get("SPECA_HERMES_PROXY_URL", DEFAULT_PROXY_URL)
        # Each member shares the circuit breaker / cost tracker so systemic
        # issues (proxy down, budget) trip once for the whole MoA.
        self.members: dict[str, APIRunner] = {
            model: _HermesModel(
                config,
                semaphore,
                max_retries=max_retries,
                circuit_breaker=self.circuit_breaker,
                cost_tracker=cost_tracker,
                base_url=base_url,
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
        async def _one(model: str, runner: APIRunner):
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
