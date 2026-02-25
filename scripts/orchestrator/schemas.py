"""
Pydantic Data Models for Security Agent Pipeline

Defines strict schemas for data flowing between phases.
These models serve as the single source of truth for:
  - Input/output validation at phase boundaries
  - Type-safe access in orchestrator code
  - Documentation of the data contract between phases

Each model corresponds to a specific data structure used in the pipeline.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Severity levels used across the pipeline.

    Members are ordered from most to least severe so that severity
    comparison works:  ``Severity.CRITICAL > Severity.HIGH`` is ``True``.
    The ``rank`` property returns a numeric value (lower = more severe)
    for use in threshold comparisons.
    """
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFORMATIONAL = "Informational"

    @property
    def rank(self) -> int:
        """Numeric rank (0 = most severe)."""
        return _SEVERITY_RANK[self]

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        # Lower rank = more severe, so "greater-or-equal severity" means
        # rank is numerically less-or-equal.
        return self.rank <= other.rank

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank < other.rank

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank >= other.rank

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank > other.rank

    @classmethod
    def from_str(cls, value: str) -> Severity | None:
        """Parse a severity string (case-insensitive).  Returns None on failure."""
        if not value:
            return None
        normalised = value.strip().capitalize()
        try:
            return cls(normalised)
        except ValueError:
            return None


# Rank lookup (populated after class definition to avoid forward-ref issues)
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFORMATIONAL: 4,
}


class ReachabilityClassification(str, Enum):
    """Reachability classification for properties and checklist items."""
    EXTERNAL_REACHABLE = "external-reachable"
    INTERNAL_ONLY = "internal-only"
    API_ONLY = "api-only"


class BugBountyScope(str, Enum):
    """Bug bounty scope classification."""
    IN_SCOPE = "in-scope"
    OUT_OF_SCOPE = "out-of-scope"
    CONDITIONAL = "conditional"


class AuditClassification(str, Enum):
    """Final classification from the formal audit.

    Includes both the original schema values and the Phase 03 prompt output values.
    """
    VULNERABLE = "vulnerable"
    VULNERABILITY = "vulnerability"
    SAFE = "safe"
    NOT_A_VULNERABILITY = "not-a-vulnerability"
    INCONCLUSIVE = "inconclusive"
    POTENTIAL_VULNERABILITY = "potential-vulnerability"
    OUT_OF_SCOPE = "out-of-scope"
    INFORMATIONAL = "informational"


class ReviewVerdict(str, Enum):
    """Review verdict from Phase 04."""
    CONFIRMED = "Confirmed"
    DISPUTED = "Disputed"
    NEEDS_MORE_INFO = "Needs More Info"


class ChecklistMindset(str, Enum):
    """Mindset used for checklist generation."""
    BOUNDARY_GUARD = "Boundary Guard"
    FORMAL_VERIFICATION_ENGINEER = "Formal Verification Engineer"


# ---------------------------------------------------------------------------
# Phase 01a – Discovery
# ---------------------------------------------------------------------------

class DiscoveredSpec(BaseModel):
    """A single specification URL discovered in Phase 01a."""
    url: str
    title: str = ""
    status: str = "pending"


class Phase01aState(BaseModel):
    """Output of Phase 01a: discovered specification URLs."""
    found_specs: list[DiscoveredSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Phase 01b – Subgraph Extraction
# ---------------------------------------------------------------------------

class ProgramGraph(BaseModel):
    """Formal program graph PG = (Q, q_init, q_final, Act, E)."""
    Q: list[str] = Field(default_factory=list, description="Finite set of nodes")
    q_init: str = Field(default="", description="Initial node")
    q_final: str = Field(default="", description="Final node")
    Act: list[str] = Field(default_factory=list, description="Set of actions")
    E: list[list[str]] = Field(
        default_factory=list,
        description="Edges as [source, action, target] triples",
    )


class SubGraph(BaseModel):
    """A single subgraph extracted from a specification."""
    id: str
    name: str = ""
    mermaid_file: str = ""
    program_graph: ProgramGraph = Field(default_factory=ProgramGraph)
    invariants: list[str] = Field(default_factory=list)


class SpecSubGraphs(BaseModel):
    """Subgraphs extracted from a single specification URL."""
    source_url: str
    title: str = ""
    sub_graphs: list[SubGraph] = Field(default_factory=list)


class Phase01bPartial(BaseModel):
    """Output of Phase 01b: subgraphs extracted from specifications."""
    specs: list[SpecSubGraphs] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trust Model (referenced by Phase 01e)
# ---------------------------------------------------------------------------

class TrustModelActor(BaseModel):
    """An actor in the trust model."""
    id: str
    name: str = ""
    description: str = ""
    trust_level: str = ""


class TrustBoundary(BaseModel):
    """A trust boundary between actors."""
    id: str
    from_actor: str = ""
    to_actor: str = ""
    description: str = ""
    entry_point_type: str = ""
    bug_bounty_scope: str = "conditional"
    attacker_controlled: bool = False
    data_flow: str = ""


class TrustAssumption(BaseModel):
    """A trust assumption in the model."""
    id: str
    text: str = ""
    related_boundary_ids: list[str] = Field(default_factory=list)
    criticality: str = ""


class StrideAnalysisItem(BaseModel):
    """A single STRIDE analysis finding."""
    id: str = ""
    trust_boundary_id: str = ""
    threat_type: str = ""
    description: str = ""
    mitigation: str = ""
    exploitability: str = ""
    bug_bounty_scope: str = "conditional"
    severity: str = ""


class TrustModel(BaseModel):
    """The trust model structure."""
    actors: list[TrustModelActor] = Field(default_factory=list)
    trust_boundaries: list[TrustBoundary] = Field(default_factory=list)
    assumptions: list[TrustAssumption] = Field(default_factory=list)
    stride_analysis: list[StrideAnalysisItem] = Field(default_factory=list)


class BugBountyScopeInfo(BaseModel):
    """Bug bounty scope information."""
    program_name: str = ""
    program_url: str = ""
    inherited_from: str = ""
    in_scope_components: list[str] = Field(default_factory=list)
    out_of_scope_components: list[str] = Field(default_factory=list)
    scope_notes: list[str] = Field(default_factory=list)
    # Severity classification from the bug bounty program.
    # Each key is a severity level (Critical/High/Medium/Low/Informational)
    # with criteria, examples, and impact description.
    severity_classification: dict[str, Any] = Field(default_factory=dict)


class Phase01dPartial(BaseModel):
    """Output of Phase 01d: trust model analysis."""
    source_files: list[str] = Field(default_factory=list)
    bug_bounty_scope: BugBountyScopeInfo = Field(default_factory=BugBountyScopeInfo)
    trust_model: TrustModel = Field(default_factory=TrustModel)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Phase 01e – Properties
# ---------------------------------------------------------------------------

class PropertyReachability(BaseModel):
    """Reachability information for a property (slim: 4 fields only)."""
    classification: str = ""
    entry_points: list[str] = Field(default_factory=list)
    attacker_controlled: bool = False
    bug_bounty_scope: str = "conditional"


class Property(BaseModel):
    """A single formal property from Phase 01e.

    ``covers`` is the primary element ID string (e.g. ``"FN-001"``).
    """
    property_id: str
    text: str = ""
    type: str = ""
    assertion: str = ""
    severity: str = ""
    covers: str = ""  # Primary element ID (slim — was an object before)
    reachability: PropertyReachability = Field(default_factory=PropertyReachability)
    exploitability: str = ""
    bug_bounty_eligible: bool = False


class Phase01ePartial(BaseModel):
    """Output of Phase 01e: properties extracted from trust model (slim)."""
    properties: list[Property] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Phase 02c – Code Pre-resolution (properties with code)
# ---------------------------------------------------------------------------

class ChecklistReachability(BaseModel):
    """Reachability information for a checklist item."""
    classification: str = ""
    entry_points: list[str] = Field(default_factory=list)
    attacker_controlled: bool = False
    bug_bounty_scope: str = "conditional"


class LineRange(BaseModel):
    """Line range in a source file."""
    start: int
    end: int


class CodeLocation(BaseModel):
    """A single code location (file + symbol + line range)."""
    file: str                     # File path relative to repository root
    symbol: str                   # Symbol name (function/class/method in name_path format)
    line_range: LineRange         # Start and end line numbers
    role: str = "primary"         # Role: "primary", "caller", "callee", "related"
    note: str = ""                # Phase 02c observation (e.g., "calls recompute instead of cached accessor")


class CodeScope(BaseModel):
    """Code location information for a checklist item.
    
    Supports multiple related code locations for comprehensive coverage.
    For example, a security check might involve:
    - Primary: the function being tested
    - Callers: functions that call the primary
    - Callees: functions called by the primary
    - Related: other relevant code locations
    """
    locations: list[CodeLocation] = Field(default_factory=list)
    resolution_status: str = ""  # "resolved", "not_found", "specification_only", "out_of_scope", "skipped", "error"
    resolution_error: str = ""


class PropertyWithCode(Property):
    """Property with pre-resolved code locations from Phase 02c."""
    code_scope: CodeScope = Field(default_factory=CodeScope)
    code_excerpt: str = ""


class ChecklistItem(BaseModel):
    """A single checklist item from Phase 02 (kept for backwards compatibility)."""
    check_id: str
    property_id: str = ""
    title: str = ""
    severity: str = ""
    mindset: str | None = None  # Optional — omitted in slim output
    is_boundary_check: bool | None = None  # Optional — omitted in slim output
    reachability: ChecklistReachability = Field(default_factory=ChecklistReachability)
    test_procedure: str = ""
    bug_class: str = ""
    risk_category: str | None = None  # Optional — omitted in slim output
    notes: str = ""
    # Optional fields from graph element
    graph_element_under_test: str | None = None  # Optional — omitted in slim output
    code_scope: CodeScope = Field(default_factory=CodeScope)  # Typed code location
    code_excerpt: str = ""  # Pre-resolved code snippet


class Phase02Partial(BaseModel):
    """Output of Phase 02: checklist items."""
    checklist: list[ChecklistItem] = Field(default_factory=list)
    # Alias: some outputs use 'checklist_items' instead of 'checklist'
    checklist_items: list[ChecklistItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _merge_checklist_keys(self) -> "Phase02Partial":
        """Merge checklist_items into checklist for consistency."""
        if self.checklist_items and self.checklist:
            # Merge both lists, deduplicating by check_id
            seen_ids = {item.check_id for item in self.checklist}
            for item in self.checklist_items:
                if item.check_id not in seen_ids:
                    self.checklist.append(item)
                    seen_ids.add(item.check_id)
        elif self.checklist_items and not self.checklist:
            self.checklist = self.checklist_items
        return self


class Phase02cPartial(BaseModel):
    """Output of Phase 02c: properties with pre-resolved code locations."""
    properties_with_code: list[PropertyWithCode] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Phase 03 – Audit Map
# ---------------------------------------------------------------------------

class Phase1AbstractInterpretation(BaseModel):
    """Phase 1 audit trail: abstract interpretation results."""
    summary: str = ""
    state_anomalies_found: list[Any] = Field(default_factory=list)


class Phase2SymbolicExecution(BaseModel):
    """Phase 2 audit trail: symbolic execution results."""
    summary: str = ""
    counterexample_found: bool = False
    counterexample: Any = None


class Phase2_5ReachabilityAnalysis(BaseModel):
    """Phase 2.5 audit trail: reachability analysis results."""
    summary: str = ""
    entry_points: list[str] = Field(default_factory=list)
    data_flow_path: str = ""
    validation_layers: list[str] = Field(default_factory=list)
    attacker_controlled: bool = False
    classification: str = "unreachable"
    notes: str = ""


class Phase3InvariantProving(BaseModel):
    """Phase 3 audit trail: invariant proving results."""
    summary: str = ""
    proof_successful: bool = False
    guard_identified: Any = None


class Phase3_5ScopeFiltering(BaseModel):
    """Phase 3.5 audit trail: scope filtering results."""
    bug_bounty_eligible: bool = False
    reason: str = ""
    recommendation: str = ""
    notes: str = ""


class AuditTrail(BaseModel):
    """Complete audit trail from the three-phase formal audit."""
    phase1_abstract_interpretation: Phase1AbstractInterpretation = Field(
        default_factory=Phase1AbstractInterpretation
    )
    phase2_symbolic_execution: Phase2SymbolicExecution = Field(
        default_factory=Phase2SymbolicExecution
    )
    phase2_5_reachability_analysis: Phase2_5ReachabilityAnalysis = Field(
        default_factory=Phase2_5ReachabilityAnalysis
    )
    phase3_invariant_proving: Phase3InvariantProving = Field(
        default_factory=Phase3InvariantProving
    )
    phase3_5_scope_filtering: Phase3_5ScopeFiltering = Field(
        default_factory=Phase3_5ScopeFiltering
    )


class AuditMapItem(BaseModel):
    """A single audit result from Phase 03."""
    model_config = ConfigDict(populate_by_name=True)

    property_id: str
    check_id: str = Field(default="", alias="checklist_id")  # Accepts both check_id and checklist_id
    code_scope: CodeScope | str = Field(default_factory=CodeScope, alias="code_path")  # Accepts CodeScope or code_path string
    code_snippet: str = Field(default="", alias="proof_trace")  # Accepts both code_snippet and proof_trace
    classification: str = ""
    bug_bounty_eligible: bool = False
    summary: str = ""
    attack_scenario: str = ""  # Additional field from Phase 03 prompt output
    audit_trail: AuditTrail = Field(default_factory=AuditTrail)

    @model_validator(mode="after")
    def _sync_fields(self) -> "AuditMapItem":
        """Populate check_id from property_id and coerce code_scope string to CodeScope."""
        if not self.check_id and self.property_id:
            self.check_id = self.property_id
        # Coerce code_path string into a CodeScope object
        if isinstance(self.code_scope, str):
            path_str = self.code_scope
            self.code_scope = CodeScope(
                locations=[CodeLocation(file=path_str, symbol="", line_range=LineRange(start=0, end=0))] if path_str else [],
                resolution_status="resolved" if path_str else "",
            )
        return self


class Phase03Partial(BaseModel):
    """Output of Phase 03: audit map items."""
    audit_items: list[AuditMapItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Phase 04 – Audit Review
# ---------------------------------------------------------------------------

class OriginalFinding(BaseModel):
    """Summary of the original finding from Phase 03."""
    classification: str = ""
    summary: str = ""


class ReviewedItem(BaseModel):
    """A single reviewed item from Phase 04."""
    property_id: str = ""
    check_id: str = ""  # Kept for downstream compatibility
    original_finding: OriginalFinding = Field(default_factory=OriginalFinding)
    review_verdict: ReviewVerdict | str = ""
    adjusted_severity: str = ""
    reviewer_notes: str = ""
    final_recommendation: str = ""


class Phase04Partial(BaseModel):
    """Output of Phase 04: reviewed audit items."""
    reviewed_items: list[ReviewedItem] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Queue payload (shared across all phases)
# ---------------------------------------------------------------------------

class QueuePayload(BaseModel):
    """Standard queue payload sent to Claude workers.

    Queue files contain only item IDs; full item data lives in a separate
    context file (keyed by ID) to reduce context window pressure.
    """
    worker_id: int
    phase: str
    item_ids: list[str]
    total_items: int
    context_file: str  # path to the companion context file


# ---------------------------------------------------------------------------
# Partial output metadata (shared across all phases)
# ---------------------------------------------------------------------------

class PartialMetadata(BaseModel):
    """Metadata attached to every PARTIAL output file."""
    phase: str
    worker_id: int
    batch_index: int
    item_count: int
    timestamp: int
    processed_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Target info (Phase 03 → Phase 04 handoff)
# ---------------------------------------------------------------------------

class TargetInfo(BaseModel):
    """Target repository information (outputs/TARGET_INFO.json).

    Created by the 02c CI workflow before Phase 02c runs. Consumed by
    Phases 02c, 03, and 04 for target repository/commit consistency.
    """
    target_repo: str
    target_ref_type: str = ""
    target_ref_label: str = ""
    target_commit: str = ""
    target_commit_short: str = ""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_discovered_spec(data: dict[str, Any]) -> tuple[DiscoveredSpec | None, list[str]]:
    """
    Validate a raw dict as a DiscoveredSpec.

    Returns:
        (parsed_item, errors) – parsed_item is None when validation fails.
    """
    errors: list[str] = []
    try:
        item = DiscoveredSpec.model_validate(data)
        if not item.url:
            errors.append("url is empty")
        return item, errors
    except Exception as exc:
        return None, [str(exc)]


def validate_subgraph(data: dict[str, Any]) -> tuple[SubGraph | None, list[str]]:
    """
    Validate a raw dict as a SubGraph.

    Returns:
        (parsed_item, errors) – parsed_item is None when validation fails.
    """
    errors: list[str] = []
    try:
        item = SubGraph.model_validate(data)
        if not item.id:
            errors.append("id is empty")
        if not item.name:
            errors.append("name is empty")
        # When mermaid_file is present, the structured PG lives in the .mmd
        # file and program_graph/invariants may be absent from the JSON.
        if not item.mermaid_file:
            pg = item.program_graph
            if not pg.Q:
                errors.append("program_graph.Q is empty (no nodes)")
            if not pg.E:
                errors.append("program_graph.E is empty (no edges)")
        return item, errors
    except Exception as exc:
        return None, [str(exc)]


def validate_property(data: dict[str, Any]) -> tuple[Property | None, list[str]]:
    """
    Validate a raw dict as a Property.

    Returns:
        (parsed_item, errors) – parsed_item is None when validation fails.
    """
    errors: list[str] = []
    try:
        item = Property.model_validate(data)
        if not item.property_id:
            errors.append("property_id is empty")
        if not item.type:
            errors.append("type is empty")
        if not item.severity:
            errors.append("severity is empty")
        if not item.covers:
            errors.append("covers is empty (expected primary element ID string)")
        return item, errors
    except Exception as exc:
        return None, [str(exc)]


def validate_checklist_item(data: dict[str, Any]) -> tuple[ChecklistItem | None, list[str]]:
    """
    Validate a raw dict as a ChecklistItem.

    Returns:
        (parsed_item, errors) – parsed_item is None when validation fails.
    """
    errors: list[str] = []
    try:
        item = ChecklistItem.model_validate(data)
        # Additional business-rule checks
        if not item.check_id:
            errors.append("check_id is empty")
        if not item.property_id:
            errors.append("property_id is empty")
        if not item.test_procedure:
            errors.append("test_procedure is empty")
        return item, errors
    except Exception as exc:
        return None, [str(exc)]


def validate_audit_map_item(data: dict[str, Any]) -> tuple[AuditMapItem | None, list[str]]:
    """
    Validate a raw dict as an AuditMapItem.

    Returns:
        (parsed_item, errors) – parsed_item is None when validation fails.
    """
    errors: list[str] = []
    try:
        item = AuditMapItem.model_validate(data)
        if not item.property_id:
            errors.append("property_id is empty")
        if not item.classification:
            errors.append("classification is empty")
        return item, errors
    except Exception as exc:
        return None, [str(exc)]


def validate_reviewed_item(data: dict[str, Any]) -> tuple[ReviewedItem | None, list[str]]:
    """
    Validate a raw dict as a ReviewedItem.

    Returns:
        (parsed_item, errors) – parsed_item is None when validation fails.
    """
    errors: list[str] = []
    try:
        item = ReviewedItem.model_validate(data)
        if not item.property_id and not item.check_id:
            errors.append("property_id is empty")
        if not item.review_verdict:
            errors.append("review_verdict is empty")
        return item, errors
    except Exception as exc:
        return None, [str(exc)]
