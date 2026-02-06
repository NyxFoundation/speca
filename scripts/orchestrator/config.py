"""
Phase Configuration Module

Defines the configuration for each phase of the security audit pipeline.
This centralizes all phase-specific settings in one place.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Any


@dataclass
class PhaseConfig:
    """Configuration for a single phase of the audit pipeline."""
    
    # Basic identification
    phase_id: str
    name: str
    description: str
    
    # File paths
    skill_path: Path
    prompt_path: Path
    queue_pattern: str
    output_pattern: str
    
    # Dependencies
    depends_on: list[str] = field(default_factory=list)
    input_patterns: list[str] = field(default_factory=list)
    
    # Batching configuration
    batch_strategy: str = "token"
    max_context_tokens: int = 190_000
    base_prompt_tokens: int = 5_000
    max_batch_size: int = 10
    
    # Execution configuration
    workdir: str | None = None
    timeout_seconds: int = 3600
    
    # Queue item configuration
    item_id_field: str = "check_id"
    result_id_field: str = ""  # ID field in result items (falls back to item_id_field)

    # Result parsing
    result_key: str = "items"

    # Output naming: semantic prefix for PARTIAL files (e.g., "TRUSTMODEL" → 01d_TRUSTMODEL_PARTIAL_W...)
    output_prefix: str = ""

    # Output mode: "file" (default) writes a single JSON; "directory" writes
    # .mmd graphs + index.json under outputs/graphs/<batch>/
    output_mode: str = "file"
    
    # Early exit conditions
    early_exit_check: Callable[[dict], bool] | None = None
    early_exit_builder: Callable[[dict], dict] | None = None

    @property
    def effective_result_id_field(self) -> str:
        """ID field name in result items. Falls back to item_id_field."""
        return self.result_id_field or self.item_id_field


# Phase configurations - ALL use token-based batching
PHASE_CONFIGS: dict[str, PhaseConfig] = {
    "01a": PhaseConfig(
        phase_id="01a",
        name="Specification Discovery",
        description="Crawl and discover specification documents",
        skill_path=Path(".claude/skills/spec-discovery/SKILL.md"),
        prompt_path=Path("prompts/01a_crawl.md"),
        queue_pattern="",  # No queue - initial phase
        output_pattern="outputs/01a_STATE.json",
        depends_on=[],
        batch_strategy="count",
        max_batch_size=1,
        item_id_field="url",
    ),
    
    "01b": PhaseConfig(
        phase_id="01b",
        name="Subgraph Extraction",
        description="Extract structured subgraphs from specifications",
        skill_path=Path(".claude/skills/subgraph-extractor/SKILL.md"),
        prompt_path=Path("prompts/01b_extract_worker.md"),
        queue_pattern="outputs/01b_QUEUE_{worker_id}.json",
        output_pattern="outputs/graphs/*/index.json",
        depends_on=["01a"],
        input_patterns=["outputs/01a_STATE.json"],
        batch_strategy="count",
        max_batch_size=2,
        item_id_field="url",
        result_id_field="source_url",
        result_key="specs",
        output_prefix="SUBGRAPHS",
        output_mode="directory",
    ),

    "01c": PhaseConfig(
        phase_id="01c",
        name="Subgraph Verification",
        description="Verify and validate extracted subgraphs",
        skill_path=Path(".claude/skills/subgraph-verifier/SKILL.md"),
        prompt_path=Path("prompts/01c_verify_worker.md"),
        queue_pattern="outputs/01c_QUEUE_{worker_id}.json",
        output_pattern="outputs/01b_SUBGRAPHS/spec_*_verified_*.json",
        depends_on=["01b"],
        input_patterns=["outputs/01b_PARTIAL_*.json"],
        batch_strategy="count",
        max_batch_size=10,
        item_id_field="file_path",
        output_prefix="VERIFIED",
    ),

    "01d": PhaseConfig(
        phase_id="01d",
        name="Trust Model Analysis",
        description="Analyze trust boundaries and security assumptions",
        skill_path=Path(".claude/skills/trust-model-analyst/SKILL.md"),
        prompt_path=Path("prompts/01d_trustmodel_worker.md"),
        queue_pattern="outputs/01d_QUEUE_{worker_id}.json",
        output_pattern="outputs/01d_TRUSTMODEL_PARTIAL_*.json",
        depends_on=["01b"],
        input_patterns=["outputs/01b_PARTIAL_*.json"],
        batch_strategy="count",
        max_batch_size=1,
        item_id_field="file_path",
        result_key="trust_model",
        output_prefix="TRUSTMODEL",
    ),

    "01e": PhaseConfig(
        phase_id="01e",
        name="Property Generation",
        description="Generate formal properties from trust model",
        skill_path=Path(".claude/skills/property-generator/SKILL.md"),
        prompt_path=Path("prompts/01e_prop_worker.md"),
        queue_pattern="outputs/01e_QUEUE_{worker_id}.json",
        output_pattern="outputs/01e_PROP_PARTIAL_*.json",
        depends_on=["01d"],
        input_patterns=["outputs/01d_PARTIAL_*.json"],
        batch_strategy="count",
        max_batch_size=1,
        item_id_field="property_id",
        result_key="properties",
        output_prefix="PROP",
    ),

    "02": PhaseConfig(
        phase_id="02",
        name="Checklist Generation",
        description="Generate security audit checklist from properties",
        skill_path=Path(".claude/skills/checklist-specialist/SKILL.md"),
        prompt_path=Path("prompts/02_checklist_worker.md"),
        queue_pattern="outputs/02_QUEUE_{worker_id}.json",
        output_pattern="outputs/02_CHECKLIST_PARTIAL_*.json",
        depends_on=["01e"],
        input_patterns=["outputs/01e_PARTIAL_*.json"],
        batch_strategy="count",
        max_batch_size=50,
        item_id_field="id",
        result_key="checklist",
        output_prefix="CHECKLIST",
    ),

    "03": PhaseConfig(
        phase_id="03",
        name="Audit Map Generation",
        description="Perform formal audit analysis on checklist items",
        skill_path=Path(".claude/skills/formal-audit/SKILL.md"),
        prompt_path=Path("prompts/03_auditmap_worker.md"),
        queue_pattern="outputs/03_ASYNC_QUEUE_*.json",
        output_pattern="outputs/03_AUDITMAP_PARTIAL_*.json",
        depends_on=["02"],
        input_patterns=["outputs/02_PARTIAL_*.json"],
        batch_strategy="count",
        max_batch_size=50,
        item_id_field="check_id",
        result_key="audit_items",
        workdir="target_workspace",
        output_prefix="AUDITMAP",
    ),

    "04": PhaseConfig(
        phase_id="04",
        name="Audit Review",
        description="Review and validate audit findings",
        skill_path=Path(".claude/skills/audit-reviewer/SKILL.md"),
        prompt_path=Path("prompts/04_review_worker.md"),
        queue_pattern="outputs/04_QUEUE_{worker_id}.json",
        output_pattern="outputs/04_REVIEW_PARTIAL_*.json",
        depends_on=["03"],
        input_patterns=["outputs/03_PARTIAL_*.json"],
        batch_strategy="count",
        max_batch_size=2,
        item_id_field="check_id",
        result_key="reviewed_items",
        workdir="target_workspace",
        output_prefix="REVIEW",
    ),
}


def get_phase_config(phase_id: str) -> PhaseConfig:
    """Get configuration for a specific phase."""
    if phase_id not in PHASE_CONFIGS:
        raise ValueError(f"Unknown phase: {phase_id}. Available: {list(PHASE_CONFIGS.keys())}")
    return PHASE_CONFIGS[phase_id]


def get_phase_chain(target_phase: str) -> list[str]:
    """Get the ordered list of phases needed to reach the target phase."""
    config = get_phase_config(target_phase)
    chain = []
    
    # Recursively build dependency chain
    for dep in config.depends_on:
        chain.extend(get_phase_chain(dep))
    
    chain.append(target_phase)
    
    # Remove duplicates while preserving order
    seen = set()
    return [p for p in chain if not (p in seen or seen.add(p))]
