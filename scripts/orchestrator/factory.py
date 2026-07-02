"""
Orchestrator Factory Module

Provides factory functions for creating phase-specific orchestrators.
"""

from typing import TYPE_CHECKING

from .base import (
    BaseOrchestrator,
    Phase01Orchestrator,
    Phase01bOrchestrator,
    Phase02cOrchestrator,
    Phase03Orchestrator,
    Phase04Orchestrator,
)
from .config import get_phase_config
from .phase0_runner import is_phase0

if TYPE_CHECKING:
    from .archiver import Archiver

if TYPE_CHECKING:
    from .archiver import Archiver


def create_orchestrator(
    phase_id: str,
    num_workers: int = 4,
    max_concurrent: int = 8,
    archiver: "Archiver | None" = None,
    property_provider: str = "prompt",
    verification_backend: str = "none",
) -> BaseOrchestrator:
    """
    Create an orchestrator for the specified phase.

    Args:
        phase_id: The phase identifier (e.g., "01b", "02c", "03", "04")
        num_workers: Number of parallel workers
        max_concurrent: Maximum concurrent Claude executions
        archiver: Optional archiver for trace capture (pass None to disable).

    Returns:
        A configured orchestrator instance for the phase.

    Raises:
        ValueError: When called for phase 0a/0b/0c. Those phases use
        ``Phase0RunnerBase`` directly — callers should route via
        ``run_phase.py``'s Phase 0 branch (see Slice H3). Surfacing this
        instead of silently returning a Base orchestrator prevents the
        async batch pipeline from ever booting up against a Phase 0 config.
    """
    # Phase 0 (setup phases) have a different lifecycle and live outside the
    # async BatchOrchestrator. Refuse to construct one here so a caller that
    # forgets the dispatch hits a loud error instead of an obscure run-time
    # failure deep inside QueueManager.
    if is_phase0(phase_id):
        raise ValueError(
            f"Phase {phase_id} is a setup phase — use "
            "`orchestrator.phase0_runner.get_phase0_runner` instead of "
            "`create_orchestrator`."
        )

    # Validate phase exists (raises ValueError for unknown phase_id)
    get_phase_config(phase_id)

    # Select appropriate orchestrator class. Each constructor calls
    # get_phase_config(phase_id).model_copy() internally, so the overrides
    # below only touch the orchestrator's own copy — never the global singleton.
    if phase_id == "01b":
        orch = Phase01bOrchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)
    elif phase_id.startswith("01"):
        orch = Phase01Orchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)
    elif phase_id == "02c":
        orch = Phase02cOrchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)
    elif phase_id == "03":
        orch = Phase03Orchestrator(num_workers, max_concurrent, archiver=archiver)
    elif phase_id == "04":
        orch = Phase04Orchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)
    else:
        orch = BaseOrchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)

    # Apply provider/backend overrides on the orchestrator's own config copy.
    if phase_id == "01e" and property_provider != "prompt":
        orch.config.property_provider = property_provider
    if phase_id == "04" and verification_backend != "none":
        orch.config.verification_backend = verification_backend

    return orch
