"""
Unified Orchestrator Framework for Security Agent

This module provides a common, modular orchestration framework that can be used
across all phases (01, 02, 03, 04) of the security audit pipeline.

Architecture:
    BaseOrchestrator (abstract)
        ├── PhaseConfig (dataclass) - Phase-specific configuration
        ├── QueueManager - Queue loading, splitting, and state management
        ├── BatchStrategy - Token-based or count-based batching
        ├── ClaudeRunner - Async Claude CLI execution
        └── ResultCollector - Output parsing and aggregation

Usage:
    from orchestrator import create_orchestrator
    
    orchestrator = create_orchestrator("01b", workers=4, max_concurrent=8)
    await orchestrator.run()
"""

from .base import BaseOrchestrator
from .config import PhaseConfig, PHASE_CONFIGS
from .queue import QueueManager
from .batch import BatchStrategy, TokenBasedBatch, CountBasedBatch
from .runner import ClaudeRunner
from .collector import ResultCollector
from .resume import ResumeManager
from .factory import create_orchestrator

__all__ = [
    "BaseOrchestrator",
    "PhaseConfig",
    "PHASE_CONFIGS",
    "QueueManager",
    "BatchStrategy",
    "TokenBasedBatch",
    "CountBasedBatch",
    "ClaudeRunner",
    "ResultCollector",
    "ResumeManager",
    "create_orchestrator",
]
