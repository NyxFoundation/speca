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

if TYPE_CHECKING:
    from .archiver import Archiver


def create_orchestrator(
    phase_id: str,
    num_workers: int = 4,
    max_concurrent: int = 8,
    archiver: "Archiver | None" = None,
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
    """
    # Validate phase exists
    config = get_phase_config(phase_id)

    # Select appropriate orchestrator class
    if phase_id == "01b":
        return Phase01bOrchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)
    elif phase_id.startswith("01"):
        return Phase01Orchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)
    elif phase_id == "02c":
        return Phase02cOrchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)
    elif phase_id == "03":
        return Phase03Orchestrator(num_workers, max_concurrent, archiver=archiver)
    elif phase_id == "04":
        return Phase04Orchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)
    else:
        # Fallback to base orchestrator
        return BaseOrchestrator(phase_id, num_workers, max_concurrent, archiver=archiver)
