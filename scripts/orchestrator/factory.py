"""
Orchestrator Factory Module

Provides factory functions for creating phase-specific orchestrators.
"""

from .base import (
    BaseOrchestrator,
    Phase01Orchestrator,
    Phase02cOrchestrator,
    Phase03Orchestrator,
    Phase04Orchestrator,
)
from .config import get_phase_config


def create_orchestrator(
    phase_id: str,
    num_workers: int = 4,
    max_concurrent: int = 8,
) -> BaseOrchestrator:
    """
    Create an orchestrator for the specified phase.

    Args:
        phase_id: The phase identifier (e.g., "01b", "02c", "03", "04")
        num_workers: Number of parallel workers
        max_concurrent: Maximum concurrent Claude executions

    Returns:
        A configured orchestrator instance for the phase.
    """
    # Validate phase exists
    config = get_phase_config(phase_id)

    # Select appropriate orchestrator class
    if phase_id.startswith("01"):
        return Phase01Orchestrator(phase_id, num_workers, max_concurrent)
    elif phase_id == "02c":
        return Phase02cOrchestrator(phase_id, num_workers, max_concurrent)
    elif phase_id == "03":
        return Phase03Orchestrator(num_workers, max_concurrent)
    elif phase_id == "04":
        return Phase04Orchestrator(phase_id, num_workers, max_concurrent)
    else:
        # Fallback to base orchestrator
        return BaseOrchestrator(phase_id, num_workers, max_concurrent)
