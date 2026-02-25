"""
Unified Orchestrator Framework for Security Agent

This module provides a common, modular orchestration framework that can be used
across all phases (01, 02, 03, 04) of the security audit pipeline.

Architecture:
    BaseOrchestrator (abstract)
        ├── PhaseConfig (Pydantic model) - Phase-specific configuration
        ├── QueueManager - Queue loading, splitting, and state management
        ├── BatchStrategy - Token-based or count-based batching
        ├── ClaudeRunner - Async Claude CLI execution
        │   ├── CircuitBreaker - Anomaly detection and cost control
        │   ├── LogAnomalyDetector - Heuristic log scanning
        │   ├── LogWatcher - Real-time async log monitoring
        │   └── CostTracker - Token usage & budget enforcement
        ├── ResultCollector - Output parsing, validation, and aggregation
        └── schemas - Pydantic data models for inter-phase data contracts

Usage:
    from orchestrator import create_orchestrator
    
    orchestrator = create_orchestrator("01b", workers=4, max_concurrent=8)
    await orchestrator.run()
"""

from .base import BaseOrchestrator, PhaseAbortError
from .config import PhaseConfig, PHASE_CONFIGS
from .queue import QueueManager
from .batch import BatchStrategy, TokenBasedBatch, CountBasedBatch
from .runner import ClaudeRunner, CircuitBreaker, CircuitBreakerTripped, LogAnomalyDetector
from .collector import ResultCollector
from .resume import ResumeManager
from .factory import create_orchestrator
from .watchdog import LogWatcher, LogWatcherConfig, CostTracker, BudgetExceeded
from . import schemas

__all__ = [
    "BaseOrchestrator",
    "PhaseAbortError",
    "PhaseConfig",
    "PHASE_CONFIGS",
    "QueueManager",
    "BatchStrategy",
    "TokenBasedBatch",
    "CountBasedBatch",
    "ClaudeRunner",
    "CircuitBreaker",
    "CircuitBreakerTripped",
    "LogAnomalyDetector",
    "LogWatcher",
    "LogWatcherConfig",
    "CostTracker",
    "BudgetExceeded",
    "ResultCollector",
    "ResumeManager",
    "create_orchestrator",
    "schemas",
]
