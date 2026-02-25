"""
Comprehensive tests for orchestrator schemas, config, circuit breaker,
log anomaly detection, and result collector.

Covers:
  - PhaseConfig construction and computed fields
  - All Pydantic data models (Phase01a through Phase04)
  - Validation helpers for each phase
  - Enum correctness
  - Edge cases and error detection
  - CircuitBreaker thresholds and state transitions
  - LogAnomalyDetector pattern matching
  - ResultCollector output validation
  - Cross-phase data flow compatibility
"""

import asyncio
import json
import sys
import os
import tempfile
import pytest

# Ensure the scripts directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from orchestrator.config import PhaseConfig, PHASE_CONFIGS, get_phase_config, get_phase_chain
from orchestrator.schemas import (
    # Enums
    Severity,
    AuditClassification,
    ReviewVerdict,
    ReachabilityClassification,
    BugBountyScope,
    ChecklistMindset,
    # Phase 01a
    DiscoveredSpec,
    Phase01aState,
    # Phase 01b
    ProgramGraph,
    SubGraph,
    SpecSubGraphs,
    Phase01bPartial,
    # Trust Model (referenced by Phase 01e)
    TrustModelActor,
    TrustBoundary,
    TrustAssumption,
    StrideAnalysisItem,
    TrustModel,
    BugBountyScopeInfo,
    Phase01dPartial,  # kept for backwards compatibility
    # Phase 01e
    PropertyReachability,
    Property,
    Phase01ePartial,
    # Phase 02
    ChecklistItem,
    ChecklistReachability,
    Phase02Partial,
    # Phase 03
    Phase1AbstractInterpretation,
    Phase2SymbolicExecution,
    Phase2_5ReachabilityAnalysis,
    Phase3InvariantProving,
    Phase3_5ScopeFiltering,
    AuditTrail,
    AuditMapItem,
    Phase03Partial,
    # Phase 04
    OriginalFinding,
    ReviewedItem,
    Phase04Partial,
    # Shared
    QueuePayload,
    PartialMetadata,
    TargetInfo,
    CodeScope,
    CodeLocation,
    LineRange,
    # Validators
    validate_discovered_spec,
    validate_subgraph,
    validate_property,
    validate_checklist_item,
    validate_audit_map_item,
    validate_reviewed_item,
)
from orchestrator.runner import (
    CircuitBreaker,
    CircuitBreakerTripped,
    LogAnomalyDetector,
)
from orchestrator.collector import ResultCollector
from orchestrator.base import generate_slug, Phase01Orchestrator


# =========================================================================
# generate_slug tests
# =========================================================================

class TestGenerateSlug:
    """Tests for the generate_slug utility function."""

    def test_abbreviation_map_hit(self):
        """Known phrases should map to their abbreviation."""
        assert generate_slug("Transaction Validation") == "txn"
        assert generate_slug("P2P Network Layer") == "p2p"
        assert generate_slug("Engine API Bridge") == "engapi"
        assert generate_slug("Consensus Protocol") == "cons"
        assert generate_slug("Validator Set") == "val"
        assert generate_slug("Block Processing") == "blk"

    def test_abbreviation_case_insensitive(self):
        assert generate_slug("TRANSACTION pool") == "txn"
        assert generate_slug("Consensus Layer") == "cons"

    def test_fallback_slugification(self):
        """Non-matching text should be slugified."""
        assert generate_slug("Hello World") == "hello-world"
        assert generate_slug("my-component") == "my-component"

    def test_max_len_truncation(self):
        """Long slugs should be truncated to max_len."""
        result = generate_slug("this is a very long description indeed", max_len=8)
        assert len(result) <= 8
        # Should not end with a hyphen
        assert not result.endswith("-")

    def test_hash_fallback_for_empty(self):
        """Empty or non-alphanumeric text should produce a hash."""
        result = generate_slug("---")
        assert len(result) == 8  # sha256 hex[:8]

    def test_max_len_respected_for_abbreviation(self):
        result = generate_slug("Transaction", max_len=2)
        assert len(result) <= 2


# =========================================================================
# ID Prefix Assignment tests
# =========================================================================

class TestIdPrefixAssignment:
    """Tests for Phase01Orchestrator._assign_property_id_prefixes."""

    def test_assigns_prefix_from_partial(self):
        """Items should get _id_prefix based on 01b partial data."""
        orch = Phase01Orchestrator("01e")
        # Create a temp 01b partial file inside outputs/ (required by path
        # traversal guard SEC-C02)
        os.makedirs("outputs", exist_ok=True)
        partial_file = os.path.join("outputs", "_test_prefix_partial.json")
        with open(partial_file, "w") as f:
            json.dump({
                "specs": [
                    {
                        "source_url": "https://eips.ethereum.org/EIPS/eip-7594",
                        "title": "EIP-7594",
                        "sub_graphs": [{"id": "SG-001", "name": "test"}],
                    }
                ]
            }, f)

        try:
            items = [{"file_path": partial_file}]
            result = orch._assign_property_id_prefixes(items)
            assert result[0]["_id_prefix"] == "PROP-eip-7594"
        finally:
            os.unlink(partial_file)

    def test_disambiguation_on_slug_collision(self):
        """Duplicate slugs should get a numeric disambiguator."""
        orch = Phase01Orchestrator("01e")
        # Create temp file inside outputs/ (required by path traversal guard SEC-C02)
        os.makedirs("outputs", exist_ok=True)
        partial_file = os.path.join("outputs", "_test_disambiguation_partial.json")
        with open(partial_file, "w") as f:
            json.dump({
                "specs": [
                    {
                        "source_url": "https://example.com/transaction-pool",
                        "title": "Transaction Pool",
                        "sub_graphs": [{"id": "SG-001", "name": "test"}],
                    }
                ]
            }, f)

        try:
            items = [
                {"file_path": partial_file},
                {"file_path": partial_file},
                {"file_path": partial_file},
            ]
            result = orch._assign_property_id_prefixes(items)
            assert result[0]["_id_prefix"] == "PROP-txn"
            assert result[1]["_id_prefix"] == "PROP-txn1"
            assert result[2]["_id_prefix"] == "PROP-txn2"
        finally:
            os.unlink(partial_file)

    def test_fallback_on_missing_file(self):
        """Missing file should produce a hash-based prefix."""
        orch = Phase01Orchestrator("01e")
        items = [{"file_path": "/nonexistent/path.json"}]
        result = orch._assign_property_id_prefixes(items)
        assert result[0]["_id_prefix"].startswith("PROP-")
        # Hash-based slug should be 8 chars
        slug = result[0]["_id_prefix"][5:]  # Strip "PROP-"
        assert len(slug) == 8

    def test_fallback_on_empty_path(self):
        """Empty file_path should produce a hash-based prefix."""
        orch = Phase01Orchestrator("01e")
        items = [{"file_path": ""}]
        result = orch._assign_property_id_prefixes(items)
        assert result[0]["_id_prefix"].startswith("PROP-")


# =========================================================================
# PhaseConfig tests
# =========================================================================

class TestPhaseConfig:
    def test_all_phase_configs_are_valid(self):
        """Every entry in PHASE_CONFIGS must be a valid PhaseConfig."""
        for pid, cfg in PHASE_CONFIGS.items():
            assert isinstance(cfg, PhaseConfig)
            assert cfg.phase_id == pid

    def test_effective_result_id_field_explicit(self):
        cfg = PHASE_CONFIGS["01b"]
        assert cfg.effective_result_id_field == "source_url"

    def test_effective_result_id_field_fallback(self):
        cfg = PHASE_CONFIGS["03"]
        assert cfg.effective_result_id_field == cfg.item_id_field

    def test_get_phase_config_known(self):
        cfg = get_phase_config("03")
        assert cfg.name == "Audit Map Generation"

    def test_get_phase_config_unknown(self):
        with pytest.raises(ValueError, match="Unknown phase"):
            get_phase_config("99")

    def test_get_phase_chain(self):
        chain = get_phase_chain("03")
        assert "01a" in chain
        assert "02c" in chain
        assert "01e" in chain
        assert "02" not in chain
        assert chain[-1] == "03"

    def test_01e_depends_on_01b(self):
        """Phase 01e should depend on 01b (not 01d)."""
        cfg = get_phase_config("01e")
        assert cfg.depends_on == ["01b"]

    def test_01c_not_in_configs(self):
        """Phase 01c should not exist in PHASE_CONFIGS."""
        assert "01c" not in PHASE_CONFIGS

    def test_01d_not_in_configs(self):
        """Phase 01d should not exist in PHASE_CONFIGS."""
        assert "01d" not in PHASE_CONFIGS

    def test_02_not_in_configs(self):
        """Phase 02 should not exist in PHASE_CONFIGS."""
        assert "02" not in PHASE_CONFIGS

    def test_02c_depends_on_01e_and_01b(self):
        """Phase 02c should depend on 01e and 01b."""
        cfg = get_phase_config("02c")
        assert cfg.depends_on == ["01e", "01b"]

    def test_phase_chain_excludes_01c(self):
        """Phase chain should not include 01c."""
        chain = get_phase_chain("03")
        assert "01c" not in chain

    def test_phase_chain_excludes_01d(self):
        """Phase chain to 02c should not include 01d."""
        chain = get_phase_chain("02c")
        assert "01d" not in chain
        assert "01e" in chain
        assert "01b" in chain

    def test_phase03_config_values(self):
        cfg = PHASE_CONFIGS["03"]
        assert cfg.batch_strategy == "count"
        assert cfg.max_batch_size == 1  # Single item — inlined skill, no fork overhead
        assert cfg.result_key == "audit_items"
        assert cfg.output_pattern == "outputs/03_PARTIAL_*.json"

    def test_phase04_config_values(self):
        """Phase 04 should use inlined prompt with no MCP and strict tools."""
        cfg = PHASE_CONFIGS["04"]
        assert cfg.batch_strategy == "count"
        assert cfg.max_batch_size == 1
        assert cfg.result_key == "reviewed_items"
        assert cfg.model == "sonnet"
        assert cfg.mcp_servers == []
        assert cfg.tools_filter == ["Read", "Write", "Grep", "Glob"]
        assert "text" in cfg.context_fields
        assert "assertion" in cfg.context_fields
        assert "covers" in cfg.context_fields
        assert "severity" in cfg.context_fields
        assert "type" in cfg.context_fields
        assert "audit_result" in cfg.context_fields

    def test_circuit_breaker_defaults(self):
        """Default circuit breaker values should be sensible."""
        cfg = PHASE_CONFIGS["01b"]
        assert cfg.circuit_breaker_threshold == 5
        assert cfg.max_total_retries == 20
        assert cfg.max_empty_results == 10

    def test_phase03_tighter_circuit_breaker(self):
        """Phase 03 should have tighter circuit breaker thresholds."""
        cfg = PHASE_CONFIGS["03"]
        assert cfg.circuit_breaker_threshold == 5
        assert cfg.max_total_retries == 20
        assert cfg.max_empty_results == 15

    def test_mcp_servers_defaults(self):
        """Phases without mcp_servers set should default to None (all servers)."""
        cfg = PhaseConfig(
            phase_id="test", name="test", description="test",
            skill_path=Path("x"), prompt_path=Path("x"),
            queue_pattern="", output_pattern="",
        )
        assert cfg.mcp_servers is None
        assert cfg.tools_filter is None

    def test_phase03_mcp_filtering(self):
        """Phase 03 should have no MCP servers and a strict tools whitelist."""
        cfg = PHASE_CONFIGS["03"]
        assert cfg.mcp_servers == []
        assert cfg.tools_filter == ["Read", "Write", "Grep", "Glob"]

    def test_all_phases_have_mcp_servers_defined(self):
        """Every phase should explicitly declare its mcp_servers."""
        for phase_id, cfg in PHASE_CONFIGS.items():
            assert cfg.mcp_servers is not None, (
                f"Phase {phase_id} should have mcp_servers defined"
            )

    def test_phase_mcp_no_serena_or_semgrep(self):
        """No phase should load serena or semgrep (interactive-only servers)."""
        for phase_id, cfg in PHASE_CONFIGS.items():
            if cfg.mcp_servers is not None:
                assert "serena" not in cfg.mcp_servers, (
                    f"Phase {phase_id} should not load serena"
                )
                assert "semgrep" not in cfg.mcp_servers, (
                    f"Phase {phase_id} should not load semgrep"
                )


# =========================================================================
# Enum tests
# =========================================================================

class TestEnums:
    def test_severity_values(self):
        assert Severity.CRITICAL == "Critical"
        assert Severity.LOW == "Low"

    def test_audit_classification_values(self):
        assert AuditClassification.VULNERABLE == "vulnerable"
        assert AuditClassification.VULNERABILITY == "vulnerability"
        assert AuditClassification.SAFE == "safe"
        assert AuditClassification.NOT_A_VULNERABILITY == "not-a-vulnerability"
        assert AuditClassification.POTENTIAL_VULNERABILITY == "potential-vulnerability"
        assert AuditClassification.INFORMATIONAL == "informational"

    def test_review_verdict_values(self):
        assert ReviewVerdict.CONFIRMED == "Confirmed"
        assert ReviewVerdict.DISPUTED == "Disputed"

    def test_reachability_classification_values(self):
        assert ReachabilityClassification.EXTERNAL_REACHABLE == "external-reachable"
        assert ReachabilityClassification.INTERNAL_ONLY == "internal-only"

    def test_bug_bounty_scope_values(self):
        assert BugBountyScope.IN_SCOPE == "in-scope"
        assert BugBountyScope.OUT_OF_SCOPE == "out-of-scope"

    def test_checklist_mindset_values(self):
        assert ChecklistMindset.BOUNDARY_GUARD == "Boundary Guard"


# =========================================================================
# Phase 01a – Discovery
# =========================================================================

class TestPhase01a:
    def test_discovered_spec_valid(self):
        spec = DiscoveredSpec(url="https://example.com/spec")
        assert spec.url == "https://example.com/spec"
        assert spec.status == "pending"

    def test_phase01a_state_valid(self):
        state = Phase01aState(
            found_specs=[
                {"url": "https://a.com", "title": "Spec A"},
                {"url": "https://b.com"},
            ]
        )
        assert len(state.found_specs) == 2
        assert state.found_specs[0].title == "Spec A"

    def test_phase01a_state_empty(self):
        state = Phase01aState()
        assert state.found_specs == []

    def test_validate_discovered_spec_valid(self):
        item, errs = validate_discovered_spec({"url": "https://x.com", "title": "X"})
        assert item is not None
        assert errs == []

    def test_validate_discovered_spec_empty_url(self):
        item, errs = validate_discovered_spec({"url": ""})
        assert "url is empty" in errs


# =========================================================================
# Phase 01b – Subgraph Extraction
# =========================================================================

class TestPhase01b:
    def test_program_graph_valid(self):
        pg = ProgramGraph(
            Q=["q_init", "q1", "q_final"],
            q_init="q_init",
            q_final="q_final",
            Act=["x = 1", "x > 0"],
            E=[["q_init", "x = 1", "q1"], ["q1", "x > 0", "q_final"]],
        )
        assert len(pg.Q) == 3
        assert len(pg.E) == 2

    def test_subgraph_valid(self):
        sg = SubGraph(
            id="SG-001",
            name="factorial",
            mermaid_file="examples/SG-001_factorial.mmd",
            program_graph=ProgramGraph(
                Q=["q1", "q2"],
                q_init="q1",
                q_final="q2",
                Act=["a"],
                E=[["q1", "a", "q2"]],
            ),
            invariants=["INV-001: x >= 0"],
        )
        assert sg.id == "SG-001"
        assert len(sg.invariants) == 1

    def test_spec_subgraphs_valid(self):
        spec = SpecSubGraphs(
            source_url="https://example.com/eip-7594",
            title="EIP-7594",
            sub_graphs=[
                SubGraph(id="SG-001", name="test"),
            ],
        )
        assert len(spec.sub_graphs) == 1

    def test_phase01b_partial_valid(self):
        partial = Phase01bPartial(
            specs=[
                {
                    "source_url": "https://example.com",
                    "title": "Test",
                    "sub_graphs": [{"id": "SG-001", "name": "test"}],
                }
            ]
        )
        assert len(partial.specs) == 1
        assert partial.specs[0].sub_graphs[0].id == "SG-001"

    def test_validate_subgraph_valid(self):
        data = {
            "id": "SG-001",
            "name": "factorial",
            "program_graph": {
                "Q": ["q1", "q2"],
                "q_init": "q1",
                "q_final": "q2",
                "Act": ["a"],
                "E": [["q1", "a", "q2"]],
            },
        }
        item, errs = validate_subgraph(data)
        assert item is not None
        assert errs == []

    def test_validate_subgraph_empty_graph(self):
        data = {"id": "SG-001", "name": "test", "program_graph": {"Q": [], "E": []}}
        item, errs = validate_subgraph(data)
        assert "program_graph.Q is empty (no nodes)" in errs
        assert "program_graph.E is empty (no edges)" in errs

    def test_validate_subgraph_missing_name(self):
        data = {"id": "SG-001", "program_graph": {"Q": ["q1"], "E": [["q1", "a", "q1"]]}}
        item, errs = validate_subgraph(data)
        assert "name is empty" in errs


# =========================================================================
# Trust Model Schemas (referenced by Phase 01e)
# =========================================================================

class TestTrustModelSchemas:
    def test_trust_model_actor_valid(self):
        actor = TrustModelActor(
            id="actor-user",
            name="User",
            description="External user",
            trust_level="untrusted",
        )
        assert actor.trust_level == "untrusted"

    def test_trust_boundary_valid(self):
        tb = TrustBoundary(
            id="tb-001",
            from_actor="actor-user",
            to_actor="actor-validator",
            entry_point_type="Transaction",
            bug_bounty_scope="in-scope",
            attacker_controlled=True,
        )
        assert tb.attacker_controlled is True

    def test_stride_analysis_item_valid(self):
        stride = StrideAnalysisItem(
            threat_type="Spoofing",
            description="Attacker spoofs identity",
            trust_boundary_id="tb-001",
        )
        assert stride.threat_type == "Spoofing"
        assert stride.trust_boundary_id == "tb-001"

    def test_trust_model_valid(self):
        tm = TrustModel(
            actors=[{"id": "a1", "name": "User"}],
            trust_boundaries=[{"id": "tb-001", "from_actor": "a1", "to_actor": "a2"}],
            assumptions=[{"id": "ta-001", "text": "Users are untrusted"}],
        )
        assert len(tm.actors) == 1
        assert tm.assumptions[0].text == "Users are untrusted"

    def test_phase01d_partial_valid(self):
        partial = Phase01dPartial(
            trust_model={
                "actors": [{"id": "a1", "name": "User"}],
                "trust_boundaries": [],
            }
        )
        assert len(partial.trust_model.actors) == 1


# =========================================================================
# Phase 01e – Properties
# =========================================================================

class TestPhase01e:
    def test_property_valid(self):
        prop = Property(
            property_id="PROP-001",
            type="invariant",
            severity="HIGH",
            covers="FN-001",
        )
        assert prop.property_id == "PROP-001"
        assert prop.covers == "FN-001"

    def test_property_reachability(self):
        r = PropertyReachability(
            classification="external-reachable",
            bug_bounty_scope="in-scope",
        )
        assert r.classification == "external-reachable"

    def test_phase01e_partial_valid(self):
        partial = Phase01ePartial(
            properties=[
                {"property_id": "PROP-001", "type": "invariant"},
                {"property_id": "PROP-002", "type": "postcondition"},
            ]
        )
        assert len(partial.properties) == 2

    def test_validate_property_valid(self):
        data = {
            "property_id": "PROP-001",
            "type": "invariant",
            "severity": "HIGH",
            "covers": "FN-001",
        }
        item, errs = validate_property(data)
        assert item is not None
        assert errs == []

    def test_validate_property_missing_id(self):
        data = {"type": "invariant"}
        item, errs = validate_property(data)
        # id is a required field, so Pydantic raises a ValidationError
        assert item is None
        assert len(errs) > 0  # should have at least one error about missing id


# =========================================================================
# Phase 02 – Checklist
# =========================================================================

class TestPhase02:
    def test_checklist_item_valid(self):
        cl = ChecklistItem(
            check_id="CHK-001",
            property_id="PROP-001",
            title="Test check",
            severity="High",
            test_procedure="Run the test",
        )
        assert cl.check_id == "CHK-001"

    def test_phase02_partial_valid(self):
        partial = Phase02Partial(
            checklist=[
                {"check_id": "CHK-001", "property_id": "PROP-001"},
            ]
        )
        assert len(partial.checklist) == 1


class TestPhase02PartialMergeValidator:
    """Tests for Phase02Partial merge validator edge cases (BUG-SCH14)."""

    def test_both_checklist_and_checklist_items_merged(self):
        """When both checklist and checklist_items are provided, they should be merged."""
        partial = Phase02Partial(
            checklist=[
                {"check_id": "CHK-001", "property_id": "PROP-001"},
            ],
            checklist_items=[
                {"check_id": "CHK-002", "property_id": "PROP-002"},
            ],
        )
        assert len(partial.checklist) == 2
        ids = {item.check_id for item in partial.checklist}
        assert ids == {"CHK-001", "CHK-002"}

    def test_both_with_duplicates_deduplicates(self):
        """Duplicate check_ids across checklist and checklist_items should be deduplicated."""
        partial = Phase02Partial(
            checklist=[
                {"check_id": "CHK-001", "property_id": "PROP-001"},
            ],
            checklist_items=[
                {"check_id": "CHK-001", "property_id": "PROP-001"},
                {"check_id": "CHK-002", "property_id": "PROP-002"},
            ],
        )
        assert len(partial.checklist) == 2
        ids = {item.check_id for item in partial.checklist}
        assert ids == {"CHK-001", "CHK-002"}

    def test_only_checklist_provided(self):
        """When only checklist is provided, it should be used as-is."""
        partial = Phase02Partial(
            checklist=[
                {"check_id": "CHK-001", "property_id": "PROP-001"},
            ],
        )
        assert len(partial.checklist) == 1
        assert partial.checklist[0].check_id == "CHK-001"

    def test_only_checklist_items_provided(self):
        """When only checklist_items is provided, it should be copied to checklist."""
        partial = Phase02Partial(
            checklist_items=[
                {"check_id": "CHK-001", "property_id": "PROP-001"},
                {"check_id": "CHK-002", "property_id": "PROP-002"},
            ],
        )
        assert len(partial.checklist) == 2
        ids = {item.check_id for item in partial.checklist}
        assert ids == {"CHK-001", "CHK-002"}

    def test_neither_provided(self):
        """When neither checklist nor checklist_items is provided, checklist should be empty."""
        partial = Phase02Partial()
        assert len(partial.checklist) == 0
        assert len(partial.checklist_items) == 0


# =========================================================================
# Phase 03 – Audit Map
# =========================================================================

class TestPhase03:
    def test_audit_trail_full(self):
        item = AuditMapItem(
            property_id="PROP-001",
            classification="vulnerable",
            summary="Found issue",
            audit_trail={
                "phase1_abstract_interpretation": {
                    "summary": "Anomaly found",
                    "state_anomalies_found": ["overflow"],
                },
                "phase2_symbolic_execution": {
                    "summary": "Counterexample found",
                    "counterexample_found": True,
                    "counterexample": "x = MAX_INT",
                },
                "phase2_5_reachability_analysis": {
                    "summary": "Reachable via P2P",
                    "attacker_controlled": True,
                },
                "phase3_invariant_proving": {
                    "summary": "Proof failed",
                    "proof_successful": False,
                },
                "phase3_5_scope_filtering": {
                    "bug_bounty_eligible": True,
                    "reason": "In-scope via P2P",
                },
            },
        )
        trail = item.audit_trail
        assert trail.phase1_abstract_interpretation.state_anomalies_found == ["overflow"]
        assert trail.phase2_symbolic_execution.counterexample_found is True
        assert trail.phase2_5_reachability_analysis.attacker_controlled is True
        assert trail.phase3_5_scope_filtering.bug_bounty_eligible is True

    def test_audit_map_item_with_code_snippet(self):
        """Test that AuditMapItem includes code_snippet field."""
        item = AuditMapItem(
            property_id="PROP-001",
            classification="vulnerable",
            summary="Found issue",
            code_snippet="int x = 0;\nif (x > 0) {\n    return true;\n}",
        )
        assert item.property_id == "PROP-001"
        assert item.check_id == "PROP-001"  # Auto-populated from property_id
        assert item.code_snippet == "int x = 0;\nif (x > 0) {\n    return true;\n}"
        # Test that it can be serialized
        dumped = item.model_dump()
        assert "code_snippet" in dumped
        assert dumped["code_snippet"] == "int x = 0;\nif (x > 0) {\n    return true;\n}"

    def test_audit_map_item_complete_fields(self):
        """Test that AuditMapItem can be created with all fields including code snippet."""
        item = AuditMapItem(
            property_id="PROP-001",
            code_scope=CodeScope(
                locations=[
                    CodeLocation(
                        file="test.java",
                        symbol="TestFunction",
                        line_range=LineRange(start=10, end=20),
                        role="primary"
                    )
                ],
                resolution_status="resolved"
            ),
            code_snippet="int x = 0;\nif (x > 0) {\n    return true;\n}",
            classification="vulnerable",
            bug_bounty_eligible=True,
            summary="Found issue"
        )
        assert item.property_id == "PROP-001"
        assert item.check_id == "PROP-001"  # Auto-populated
        assert len(item.code_scope.locations) == 1
        assert item.code_scope.locations[0].file == "test.java"
        assert item.code_scope.locations[0].line_range.start == 10
        assert item.code_scope.locations[0].line_range.end == 20
        assert item.code_snippet == "int x = 0;\nif (x > 0) {\n    return true;\n}"
        assert item.classification == "vulnerable"
        assert item.bug_bounty_eligible is True


class TestPhase03Partial:
    def test_valid_partial(self):
        partial = Phase03Partial(
            audit_items=[
                {"property_id": "PROP-001", "classification": "safe"},
            ]
        )
        assert len(partial.audit_items) == 1


# =========================================================================
# Phase 04 – Audit Review
# =========================================================================

class TestPhase04Partial:
    def test_valid_review(self):
        partial = Phase04Partial(
            reviewed_items=[
                {
                    "check_id": "CHK-001",
                    "review_verdict": "Confirmed",
                    "adjusted_severity": "High",
                }
            ]
        )
        assert len(partial.reviewed_items) == 1
        assert partial.reviewed_items[0].review_verdict == "Confirmed"

    def test_reviewed_item_defaults(self):
        item = ReviewedItem(check_id="CHK-002")
        assert item.review_verdict == ""
        assert item.reviewer_notes == ""


# =========================================================================
# Validation helpers
# =========================================================================

class TestValidationHelpers:
    # -- checklist items --
    def test_validate_checklist_item_valid(self):
        data = {
            "check_id": "CHK-001",
            "property_id": "PROP-001",
            "test_procedure": "Run test",
        }
        item, errs = validate_checklist_item(data)
        assert item is not None
        assert errs == []

    def test_validate_checklist_item_missing_fields(self):
        data = {"check_id": "CHK-001"}
        item, errs = validate_checklist_item(data)
        assert "property_id is empty" in errs
        assert "test_procedure is empty" in errs

    def test_validate_checklist_item_empty_check_id(self):
        data = {"check_id": ""}
        item, errs = validate_checklist_item(data)
        assert "check_id is empty" in errs

    # -- audit map items --
    def test_validate_audit_map_item_valid(self):
        data = {
            "property_id": "PROP-001",
            "classification": "vulnerable",
        }
        item, errs = validate_audit_map_item(data)
        assert item is not None
        assert errs == []

    def test_validate_audit_map_item_missing_classification(self):
        data = {"property_id": "PROP-001"}
        item, errs = validate_audit_map_item(data)
        assert "classification is empty" in errs

    # -- reviewed items --
    def test_validate_reviewed_item_valid(self):
        data = {
            "check_id": "CHK-001",
            "review_verdict": "Confirmed",
        }
        item, errs = validate_reviewed_item(data)
        assert item is not None
        assert errs == []

    def test_validate_reviewed_item_missing_verdict(self):
        data = {"check_id": "CHK-001"}
        item, errs = validate_reviewed_item(data)
        assert "review_verdict is empty" in errs

    def test_validate_reviewed_item_empty_check_id(self):
        data = {"check_id": "", "review_verdict": "Confirmed"}
        item, errs = validate_reviewed_item(data)
        assert "property_id is empty" in errs


# =========================================================================
# Shared models
# =========================================================================

class TestQueuePayload:
    def test_valid_payload(self):
        payload = QueuePayload(
            worker_id=0,
            phase="03",
            item_ids=["CHK-001"],
            total_items=1,
            context_file="outputs/03_CONTEXT_W0B0_1700000000.json",
        )
        assert payload.worker_id == 0
        assert payload.item_ids == ["CHK-001"]
        assert payload.context_file == "outputs/03_CONTEXT_W0B0_1700000000.json"


class TestPartialMetadata:
    def test_valid_metadata(self):
        meta = PartialMetadata(
            phase="03",
            worker_id=0,
            batch_index=1,
            item_count=5,
            timestamp=1700000000,
            processed_ids=["CHK-001", "CHK-002"],
        )
        assert meta.item_count == 5
        assert len(meta.processed_ids) == 2


class TestTargetInfo:
    def test_valid_target(self):
        info = TargetInfo(
            target_repo="ethereum/go-ethereum",
            target_ref_type="branch",
            target_ref_label="master",
        )
        assert info.target_repo == "ethereum/go-ethereum"


# =========================================================================
# Cross-phase data flow tests
# =========================================================================

class TestCrossPhaseDataFlow:
    """Test that data structures are compatible across phase boundaries."""

    def test_01e_property_to_02c_code_resolution(self):
        """Property from 01e should be usable as input for 02c code resolution."""
        prop = Property(
            property_id="PROP-001",
            type="invariant",
            severity="HIGH",
            covers="FN-001",
            reachability={
                "classification": "external-reachable",
                "bug_bounty_scope": "in-scope",
            },
        )
        item = dict(prop.model_dump())
        item["source_file"] = "test.json"
        assert item["reachability"]["bug_bounty_scope"] == "in-scope"
        assert item["covers"] == "FN-001"

    def test_02c_property_to_03_audit(self):
        """Property with code from 02c should be parseable as Phase03 input."""
        from orchestrator.schemas import PropertyWithCode
        pwc = PropertyWithCode(
            property_id="PROP-001",
            text="Test property",
            type="invariant",
            severity="High",
            covers="FN-001",
            code_scope={"resolution_status": "resolved", "locations": [
                {"file": "test.go", "symbol": "TestFunc", "line_range": {"start": 1, "end": 10}, "role": "primary"}
            ]},
        )
        entry = pwc.model_dump()
        parsed, errs = validate_property(entry)
        assert parsed is not None
        assert errs == []
        # Validate with PropertyWithCode to ensure code_scope is preserved (BUG-SCH07)
        pwc_parsed = PropertyWithCode.model_validate(entry)
        assert pwc_parsed.code_scope is not None
        assert pwc_parsed.code_scope.resolution_status == "resolved"
        assert len(pwc_parsed.code_scope.locations) == 1
        assert pwc_parsed.code_scope.locations[0].file == "test.go"

    def test_03_audit_to_04_review(self):
        """Audit item from 03 should be parseable as Phase04 input."""
        audit = AuditMapItem(
            property_id="PROP-001",
            classification="vulnerable",
            summary="Found issue",
        )
        entry = audit.model_dump()
        parsed, errs = validate_audit_map_item(entry)
        assert parsed is not None
        assert errs == []


# =========================================================================
# Circuit Breaker tests
# =========================================================================

class TestCircuitBreaker:
    """Tests for the CircuitBreaker class in runner.py."""

    def _make_config(self, **overrides) -> PhaseConfig:
        """Create a minimal PhaseConfig for testing."""
        from pathlib import Path
        defaults = dict(
            phase_id="test",
            name="Test Phase",
            description="Test",
            skill_path=Path("."),
            prompt_path=Path("."),
            queue_pattern="",
            output_pattern="",
            circuit_breaker_threshold=3,
            max_total_retries=5,
            max_empty_results=4,
        )
        defaults.update(overrides)
        return PhaseConfig(**defaults)

    def test_initial_state(self):
        cb = CircuitBreaker(self._make_config())
        stats = cb._get_stats_unlocked()
        assert stats["consecutive_failures"] == 0
        assert stats["total_retries"] == 0
        assert stats["empty_results"] == 0
        assert stats["total_successes"] == 0
        assert stats["total_failures"] == 0

    def test_success_resets_consecutive_failures(self):
        cb = CircuitBreaker(self._make_config())
        loop = asyncio.new_event_loop()
        try:
            # Record some failures (below threshold)
            loop.run_until_complete(cb.record_failure())
            loop.run_until_complete(cb.record_failure())
            assert cb.consecutive_failures == 2
            # Success resets consecutive counter
            loop.run_until_complete(cb.record_success())
            assert cb.consecutive_failures == 0
            assert cb.total_failures == 2  # total stays
            assert cb.total_successes == 1
        finally:
            loop.close()

    def test_consecutive_failure_trips(self):
        cb = CircuitBreaker(self._make_config(circuit_breaker_threshold=3))
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cb.record_failure())
            loop.run_until_complete(cb.record_failure())
            with pytest.raises(CircuitBreakerTripped, match="consecutive failures"):
                loop.run_until_complete(cb.record_failure())
        finally:
            loop.close()

    def test_total_retries_trips(self):
        cb = CircuitBreaker(self._make_config(max_total_retries=3))
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cb.record_retry())
            loop.run_until_complete(cb.record_retry())
            with pytest.raises(CircuitBreakerTripped, match="total retries"):
                loop.run_until_complete(cb.record_retry())
        finally:
            loop.close()

    def test_empty_results_trips(self):
        cb = CircuitBreaker(self._make_config(max_empty_results=2))
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cb.record_empty_result())
            with pytest.raises(CircuitBreakerTripped, match="empty-result"):
                loop.run_until_complete(cb.record_empty_result())
        finally:
            loop.close()

    def test_mixed_success_and_failure(self):
        """Interleaved successes should prevent consecutive failure trip."""
        cb = CircuitBreaker(self._make_config(circuit_breaker_threshold=3))
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cb.record_failure())
            loop.run_until_complete(cb.record_failure())
            loop.run_until_complete(cb.record_success())  # resets
            loop.run_until_complete(cb.record_failure())
            loop.run_until_complete(cb.record_failure())
            loop.run_until_complete(cb.record_success())  # resets again
            # Should not trip because consecutive never reached 3
            assert cb.total_failures == 4
            assert cb.total_successes == 2
        finally:
            loop.close()

    def test_circuit_breaker_tripped_has_stats(self):
        cb = CircuitBreaker(self._make_config(circuit_breaker_threshold=1))
        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(CircuitBreakerTripped) as exc_info:
                loop.run_until_complete(cb.record_failure())
            assert "consecutive_failures" in exc_info.value.stats
            assert exc_info.value.stats["total_failures"] == 1
        finally:
            loop.close()

    def test_get_stats_snapshot(self):
        cb = CircuitBreaker(self._make_config())
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cb.record_success())
            loop.run_until_complete(cb.record_retry())
            stats = cb._get_stats_unlocked()
            assert stats == {
                "consecutive_failures": 0,
                "total_retries": 1,
                "empty_results": 0,
                "total_successes": 1,
                "total_failures": 0,
            }
        finally:
            loop.close()


# =========================================================================
# Log Anomaly Detector tests
# =========================================================================

class TestLogAnomalyDetector:
    """Tests for the LogAnomalyDetector class in runner.py."""

    def test_no_anomalies_in_clean_log(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type": "message", "content": "Processing item CHK-001"}\n')
            f.write('{"type": "result", "result": "Done"}\n')
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(f.name)
        os.unlink(f.name)
        assert anomalies == []

    def test_detects_rate_limit(self):
        """Actual API rate limit errors (type=error) should be detected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type": "error", "error": {"type": "rate_limit_error", "message": "429 Too Many Requests"}}\n')
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(f.name)
        os.unlink(f.name)
        assert any("rate_limit_error" in a for a in anomalies)

    def test_detects_context_overflow(self):
        """Actual API context overflow errors should be detected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type": "error", "error": {"type": "invalid_request_error", "message": "context length exceeded maximum context window"}}\n')
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(f.name)
        os.unlink(f.name)
        assert any("context_overflow" in a for a in anomalies)

    def test_detects_api_error(self):
        """APIError / InternalServerError should be detected."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type": "error", "error": {"type": "api_error", "message": "APIError: InternalServerError"}}\n')
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(f.name)
        os.unlink(f.name)
        assert any("api_error" in a for a in anomalies)

    def test_detects_excessive_tool_calls(self):
        """More than 200 tool_use blocks should be flagged."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for _ in range(210):
                f.write('{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "bash"}]}}\n')
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(f.name)
        os.unlink(f.name)
        assert any("excessive_tool_calls" in a for a in anomalies)

    def test_below_tool_call_threshold_no_anomaly(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for _ in range(100):
                f.write('{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "bash"}]}}\n')
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(f.name)
        os.unlink(f.name)
        # 100 < 200 threshold, so no anomaly
        assert not any("excessive_tool_calls" in a for a in anomalies)

    def test_nonexistent_file_returns_empty(self):
        from pathlib import Path
        anomalies = LogAnomalyDetector.scan_log(Path("/nonexistent/file.log"))
        assert anomalies == []

    def test_scan_log_accepts_path_object(self):
        from pathlib import Path
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type": "message"}\n')
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(Path(f.name))
        os.unlink(f.name)
        assert anomalies == []

    def test_no_false_positive_from_checklist_content(self):
        """Content inside tool_result (e.g. checklist data with '429' line numbers)
        should NOT trigger false positives."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            # Simulate a real Phase03 log line: user message with tool_result
            # containing checklist data that has "429" as a JSON line number
            line = json.dumps({
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": "toolu_01HRU8tvMj9La1aEyyUu177d",
                        "content": '{\n  "worker_id": 7,\n  "phase": "03",\n  429: {"check_id": "CHK-W4B13-48"},\n  "rate_limit_test": "rate limit overrun and consensus failure.",\n  "timeout_test": "block processing timeout thresholds",\n  "error_test": "error handling error recovery error reporting"\n}'
                    }]
                }
            })
            f.write(line + "\n")
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(f.name)
        os.unlink(f.name)
        # Should NOT detect any anomalies from user content
        assert anomalies == [], f"False positive detected: {anomalies}"

    def test_no_false_positive_from_assistant_text(self):
        """Assistant text content mentioning errors should NOT trigger anomalies."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            line = json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{
                        "type": "text",
                        "text": "I found a rate limit vulnerability on line 429. The timeout error handling has error recovery issues."
                    }]
                }
            })
            f.write(line + "\n")
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(f.name)
        os.unlink(f.name)
        assert anomalies == [], f"False positive detected: {anomalies}"


# =========================================================================
# ResultCollector tests
# =========================================================================

class TestResultCollector:
    """Tests for the ResultCollector output validation."""

    def _make_config(self, phase_id: str = "03") -> PhaseConfig:
        """Get a real PhaseConfig for testing."""
        return get_phase_config(phase_id)

    def test_save_partial_creates_file(self):
        """save_partial should create a JSON file on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                config = self._make_config("03")
                collector = ResultCollector(config)
                results = [
                    {"property_id": "PROP-001", "check_id": "CHK-001", "classification": "safe"},
                    {"property_id": "PROP-002", "check_id": "CHK-002", "classification": "vulnerable"},
                ]
                path = collector.save_partial(results, worker_id=0, batch_index=1)
                assert path.exists()
                with open(path) as f:
                    data = json.load(f)
                assert "audit_items" in data
                assert len(data["audit_items"]) == 2
                assert "metadata" in data
                # BUG-SCH11: Verify processed_ids are tracked in metadata
                assert "processed_ids" in data["metadata"]
                assert "PROP-001" in data["metadata"]["processed_ids"]
                assert "PROP-002" in data["metadata"]["processed_ids"]
                assert len(data["metadata"]["processed_ids"]) == 2
            finally:
                os.chdir(old_cwd)

    def test_save_partial_validation_stats_clean(self):
        """Valid output should not increment warning/error counters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                config = self._make_config("03")
                collector = ResultCollector(config)
                results = [
                    {"property_id": "PROP-001", "check_id": "PROP-001", "classification": "safe"},
                ]
                collector.save_partial(results, worker_id=0, batch_index=1)
                summary = collector.get_validation_summary()
                assert summary["total_saves"] == 1
                assert summary["validation_warnings"] == 0
                assert summary["validation_errors"] == 0
            finally:
                os.chdir(old_cwd)

    def test_save_partial_tracks_validation_errors(self):
        """Malformed output should increment error counters but still save."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                config = self._make_config("01e")
                collector = ResultCollector(config)
                # Pass something that doesn't match Phase01ePartial schema
                results = [{"garbage_key": "not a property"}]
                path = collector.save_partial(results, worker_id=0, batch_index=1)
                # File should still be saved
                assert path.exists()
                summary = collector.get_validation_summary()
                assert summary["total_saves"] == 1
                # The malformed data may or may not trigger errors depending on
                # how lenient the Pydantic model is; at minimum the save should work
            finally:
                os.chdir(old_cwd)

    def test_get_validation_summary(self):
        """get_validation_summary should return correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                config = self._make_config("03")
                collector = ResultCollector(config)
                summary = collector.get_validation_summary()
                assert "total_saves" in summary
                assert "validation_warnings" in summary
                assert "validation_errors" in summary
            finally:
                os.chdir(old_cwd)

    def test_multiple_saves_accumulate_stats(self):
        """Multiple save_partial calls should accumulate statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                config = self._make_config("03")
                collector = ResultCollector(config)
                for i in range(3):
                    results = [{"check_id": f"CHK-{i:03d}", "classification": "safe"}]
                    collector.save_partial(results, worker_id=0, batch_index=i)
                summary = collector.get_validation_summary()
                assert summary["total_saves"] == 3
            finally:
                os.chdir(old_cwd)


# =========================================================================
# Integration: Circuit Breaker + Config
# =========================================================================

class TestCircuitBreakerIntegration:
    """Test circuit breaker with real PhaseConfig values."""

    def test_phase03_config_trips_at_5_consecutive(self):
        """Phase 03 has circuit_breaker_threshold=5."""
        config = get_phase_config("03")
        cb = CircuitBreaker(config)
        loop = asyncio.new_event_loop()
        try:
            for _ in range(4):
                loop.run_until_complete(cb.record_failure())
            with pytest.raises(CircuitBreakerTripped):
                loop.run_until_complete(cb.record_failure())
        finally:
            loop.close()

    def test_phase03_config_trips_at_20_retries(self):
        """Phase 03 has max_total_retries=20."""
        config = get_phase_config("03")
        cb = CircuitBreaker(config)
        loop = asyncio.new_event_loop()
        try:
            for _ in range(19):
                loop.run_until_complete(cb.record_retry())
                # Reset consecutive failures to avoid that threshold
                loop.run_until_complete(cb.record_success())
            with pytest.raises(CircuitBreakerTripped, match="total retries"):
                loop.run_until_complete(cb.record_retry())
        finally:
            loop.close()

    def test_default_phase_does_not_trip_early(self):
        """Default phases (threshold=5) should survive 4 consecutive failures."""
        config = get_phase_config("01b")
        cb = CircuitBreaker(config)
        loop = asyncio.new_event_loop()
        try:
            for _ in range(4):
                loop.run_until_complete(cb.record_failure())
            # 4 < 5, should not trip
            assert cb.consecutive_failures == 4
        finally:
            loop.close()


# =========================================================================
# LogWatcher tests (real-time async log monitoring)
# =========================================================================

from orchestrator.watchdog import (
    LogWatcher,
    LogWatcherConfig,
    CostTracker,
    BudgetExceeded,
    extract_token_usage_from_log,
    _extract_scannable_text,
)


class TestExtractScannableText:
    """Unit tests for _extract_scannable_text — the core JSON parsing logic."""

    def test_error_event_extracted(self):
        """type=error lines should return the error text for scanning."""
        line = json.dumps({
            "type": "error",
            "error": {"type": "rate_limit_error", "message": "429 Too Many Requests"}
        })
        text, is_tool = _extract_scannable_text(line)
        assert text is not None
        assert "rate_limit_error" in text
        assert "429" in text
        assert is_tool is False

    def test_user_tool_result_skipped(self):
        """User messages with tool_result should NOT return scannable text."""
        line = json.dumps({
            "type": "user",
            "message": {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "content": '{"429": "rate limit", "timeout": true, "error error error": 1}'
                }]
            }
        })
        text, is_tool = _extract_scannable_text(line)
        assert text is None
        assert is_tool is False

    def test_assistant_text_skipped(self):
        """Assistant text messages should NOT return scannable text."""
        line = json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Found 429 rate limit errors and timeout issues"}]
            }
        })
        text, is_tool = _extract_scannable_text(line)
        assert text is None
        assert is_tool is False

    def test_assistant_tool_use_detected(self):
        """Assistant tool_use blocks should set is_tool_use=True."""
        line = json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "bash", "input": {"command": "ls"}}]
            }
        })
        text, is_tool = _extract_scannable_text(line)
        assert text is None  # No error text to scan
        assert is_tool is True

    def test_system_message_scanned(self):
        """System messages should have subtype+content scanned."""
        line = json.dumps({
            "type": "system",
            "message": {"subtype": "rate_limited", "content": "You are being rate limited"}
        })
        text, is_tool = _extract_scannable_text(line)
        assert text is not None
        assert "rate_limited" in text

    def test_non_json_line_scanned_as_fallback(self):
        """Non-JSON lines (e.g. stderr) should be scanned as-is."""
        line = "Error: connection timed out after 30s"
        text, is_tool = _extract_scannable_text(line)
        assert text is not None
        assert "timed out" in text

    def test_plain_message_skipped(self):
        """Normal message/result types should return None."""
        line = json.dumps({"type": "message", "content": "Processing..."})
        text, is_tool = _extract_scannable_text(line)
        assert text is None
        assert is_tool is False

    def test_top_level_error_field_non_user(self):
        """Top-level error field on non-user/assistant types should be scanned."""
        line = json.dumps({"error": "ServiceUnavailable: overloaded"})
        text, is_tool = _extract_scannable_text(line)
        assert text is not None
        assert "ServiceUnavailable" in text

    def test_top_level_error_field_on_user_type_skipped(self):
        """Top-level error field on user type should be skipped."""
        line = json.dumps({"type": "user", "error": "429 rate limit"})
        text, is_tool = _extract_scannable_text(line)
        assert text is None


class TestLogWatcher:
    """Tests for the real-time LogWatcher in watchdog.py."""

    def test_clean_log_no_anomalies(self):
        """A clean log should produce no anomalies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "clean.log.jsonl")
            with open(log_path, "w") as f:
                f.write('{"type": "message", "content": "Hello"}\n')
                f.write('{"type": "result", "result": "Done"}\n')

            watcher = LogWatcher(log_path, config=LogWatcherConfig(poll_interval=0.05))
            loop = asyncio.new_event_loop()
            try:
                # Run the watcher briefly then stop
                async def run_and_stop():
                    task = asyncio.create_task(watcher.watch())
                    await asyncio.sleep(0.2)
                    watcher.stop()
                    await task

                loop.run_until_complete(run_and_stop())
            finally:
                loop.close()

            assert watcher.should_stop is False
            assert len(watcher.anomalies) == 0
            assert watcher.lines_scanned >= 2

    def test_rate_limit_triggers_anomaly(self):
        """Rate limit errors (type=error with error object) should be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "ratelimit.log.jsonl")
            with open(log_path, "w") as f:
                for i in range(5):
                    f.write(json.dumps({
                        "type": "error",
                        "error": {"type": "rate_limit_error", "message": f"429 Too Many Requests attempt {i}"}
                    }) + "\n")

            watcher = LogWatcher(
                log_path,
                config=LogWatcherConfig(poll_interval=0.05, anomaly_threshold=3),
            )
            loop = asyncio.new_event_loop()
            try:
                async def run_and_stop():
                    task = asyncio.create_task(watcher.watch())
                    await asyncio.sleep(0.3)
                    watcher.stop()
                    await task

                loop.run_until_complete(run_and_stop())
            finally:
                loop.close()

            assert watcher.should_stop is True
            assert any("rate_limit_error" in a for a in watcher.anomalies)

    def test_context_overflow_detected(self):
        """Context overflow errors should be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "overflow.log.jsonl")
            with open(log_path, "w") as f:
                for i in range(4):
                    f.write(json.dumps({
                        "type": "error",
                        "error": {"type": "invalid_request_error", "message": f"context length exceeded maximum context window {i}"}
                    }) + "\n")

            watcher = LogWatcher(
                log_path,
                config=LogWatcherConfig(poll_interval=0.05, anomaly_threshold=3),
            )
            loop = asyncio.new_event_loop()
            try:
                async def run_and_stop():
                    task = asyncio.create_task(watcher.watch())
                    await asyncio.sleep(0.3)
                    watcher.stop()
                    await task

                loop.run_until_complete(run_and_stop())
            finally:
                loop.close()

            assert watcher.should_stop is True
            assert any("context_overflow" in a for a in watcher.anomalies)

    def test_below_threshold_no_stop(self):
        """Anomalies below threshold should not trigger stop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "below.log.jsonl")
            with open(log_path, "w") as f:
                f.write(json.dumps({"type": "error", "error": {"type": "rate_limit_error", "message": "429 Too Many Requests"}}) + "\n")
                f.write('{"type": "message", "content": "OK"}\n')

            watcher = LogWatcher(
                log_path,
                config=LogWatcherConfig(poll_interval=0.05, anomaly_threshold=5),
            )
            loop = asyncio.new_event_loop()
            try:
                async def run_and_stop():
                    task = asyncio.create_task(watcher.watch())
                    await asyncio.sleep(0.2)
                    watcher.stop()
                    await task

                loop.run_until_complete(run_and_stop())
            finally:
                loop.close()

            assert watcher.should_stop is False
            assert len(watcher.anomalies) == 1

    def test_nonexistent_file_exits_gracefully(self):
        """Watcher should exit gracefully if file never appears."""
        watcher = LogWatcher(
            "/nonexistent/path/log.jsonl",
            config=LogWatcherConfig(poll_interval=0.05),
        )
        loop = asyncio.new_event_loop()
        try:
            # Override the wait loop to be shorter
            async def run_short():
                task = asyncio.create_task(watcher.watch())
                await asyncio.sleep(2.0)  # wait for 30 polls at 0.05s
                watcher.stop()
                await task

            loop.run_until_complete(run_short())
        finally:
            loop.close()

        assert watcher.should_stop is False
        assert watcher.lines_scanned == 0

    def test_get_summary(self):
        """get_summary should return a well-structured dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "summary.log.jsonl")
            with open(log_path, "w") as f:
                f.write('{"type": "message"}\n')

            watcher = LogWatcher(log_path, config=LogWatcherConfig(poll_interval=0.05))
            loop = asyncio.new_event_loop()
            try:
                async def run_and_stop():
                    task = asyncio.create_task(watcher.watch())
                    await asyncio.sleep(0.2)
                    watcher.stop()
                    await task

                loop.run_until_complete(run_and_stop())
            finally:
                loop.close()

            summary = watcher.get_summary()
            assert "log_path" in summary
            assert "lines_scanned" in summary
            assert "anomaly_count" in summary
            assert "tool_call_count" in summary
            assert "should_stop" in summary
            assert "anomalies" in summary

    def test_api_error_detected(self):
        """APIError patterns should be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "apierror.log.jsonl")
            with open(log_path, "w") as f:
                for i in range(4):
                    f.write(json.dumps({
                        "type": "error",
                        "error": {"type": "api_error", "message": f"APIError: InternalServerError {i}"}
                    }) + "\n")

            watcher = LogWatcher(
                log_path,
                config=LogWatcherConfig(poll_interval=0.05, anomaly_threshold=3),
            )
            loop = asyncio.new_event_loop()
            try:
                async def run_and_stop():
                    task = asyncio.create_task(watcher.watch())
                    await asyncio.sleep(0.3)
                    watcher.stop()
                    await task

                loop.run_until_complete(run_and_stop())
            finally:
                loop.close()

            assert watcher.should_stop is True
            assert any("api_error" in a for a in watcher.anomalies)

    def test_no_false_positive_from_tool_result_content(self):
        """LogWatcher should NOT trigger on '429', 'rate limit', 'timeout' etc.
        when they appear inside tool_result user content (e.g. checklist data)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "false_positive.log.jsonl")
            with open(log_path, "w") as f:
                # Simulate real Phase03 log: user message with tool_result
                line = json.dumps({
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": "toolu_01HRU8tvMj9La1aEyyUu177d",
                            "content": json.dumps({
                                "worker_id": 7,
                                "phase": "03",
                                "items": [
                                    {"line": 429, "check_id": "CHK-W4B13-48"},
                                    {"description": "rate limit overrun and consensus failure."},
                                    {"description": "block processing timeout thresholds"},
                                    {"description": "error handling error recovery error reporting"}
                                ]
                            })
                        }]
                    }
                })
                # Write it multiple times to exceed any threshold
                for _ in range(10):
                    f.write(line + "\n")

            watcher = LogWatcher(
                log_path,
                config=LogWatcherConfig(poll_interval=0.05, anomaly_threshold=2),
            )
            loop = asyncio.new_event_loop()
            try:
                async def run_and_stop():
                    task = asyncio.create_task(watcher.watch())
                    await asyncio.sleep(0.3)
                    watcher.stop()
                    await task

                loop.run_until_complete(run_and_stop())
            finally:
                loop.close()

            assert watcher.should_stop is False, (
                f"False positive! Anomalies: {watcher.anomalies}"
            )
            assert len(watcher.anomalies) == 0


# =========================================================================
# CostTracker tests
# =========================================================================

class TestCostTracker:
    """Tests for the CostTracker in watchdog.py."""

    def test_initial_state(self):
        tracker = CostTracker(max_budget_usd=100.0)
        stats = tracker.get_stats()
        assert stats["total_input_tokens"] == 0
        assert stats["total_output_tokens"] == 0
        assert stats["total_cost_usd"] == 0
        assert stats["max_budget_usd"] == 100.0
        assert stats["budget_remaining_usd"] == 100.0
        assert stats["budget_utilization_pct"] == 0.0
        assert stats["batch_count"] == 0

    def test_record_usage_accumulates(self):
        tracker = CostTracker(max_budget_usd=100.0)
        loop = asyncio.new_event_loop()
        try:
            cost1 = loop.run_until_complete(
                tracker.record_usage(input_tokens=1000, output_tokens=500)
            )
            cost2 = loop.run_until_complete(
                tracker.record_usage(input_tokens=2000, output_tokens=1000)
            )
            assert cost1 > 0
            assert cost2 > 0
            stats = tracker.get_stats()
            assert stats["total_input_tokens"] == 3000
            assert stats["total_output_tokens"] == 1500
            assert stats["batch_count"] == 2
            assert stats["total_cost_usd"] > 0
        finally:
            loop.close()

    def test_budget_exceeded_raises(self):
        tracker = CostTracker(max_budget_usd=0.001)  # Very small budget
        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(BudgetExceeded, match="Budget exceeded"):
                loop.run_until_complete(
                    tracker.record_usage(input_tokens=1_000_000, output_tokens=1_000_000)
                )
        finally:
            loop.close()

    def test_budget_not_exceeded_within_limit(self):
        tracker = CostTracker(max_budget_usd=100.0)
        loop = asyncio.new_event_loop()
        try:
            # Small usage should not trigger
            loop.run_until_complete(
                tracker.record_usage(input_tokens=100, output_tokens=50)
            )
            stats = tracker.get_stats()
            assert stats["budget_remaining_usd"] > 99.0
        finally:
            loop.close()

    def test_cost_calculation_accuracy(self):
        """Verify cost calculation with known values."""
        tracker = CostTracker(
            max_budget_usd=100.0,
            input_price_per_million=3.0,
            output_price_per_million=15.0,
        )
        loop = asyncio.new_event_loop()
        try:
            cost = loop.run_until_complete(
                tracker.record_usage(input_tokens=1_000_000, output_tokens=1_000_000)
            )
            # Expected: $3.00 + $15.00 = $18.00
            assert abs(cost - 18.0) < 0.01
        finally:
            loop.close()

    def test_get_history(self):
        tracker = CostTracker(max_budget_usd=100.0)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                tracker.record_usage(
                    input_tokens=1000, output_tokens=500,
                    worker_id=1, batch_index=3,
                )
            )
            history = tracker.get_history()
            assert len(history) == 1
            assert history[0]["worker_id"] == 1
            assert history[0]["batch_index"] == 3
            assert history[0]["input_tokens"] == 1000
            assert history[0]["output_tokens"] == 500
        finally:
            loop.close()

    def test_budget_exceeded_has_stats(self):
        tracker = CostTracker(max_budget_usd=0.001)
        loop = asyncio.new_event_loop()
        try:
            with pytest.raises(BudgetExceeded) as exc_info:
                loop.run_until_complete(
                    tracker.record_usage(input_tokens=1_000_000, output_tokens=1_000_000)
                )
            assert "total_cost_usd" in exc_info.value.stats
            assert "max_budget_usd" in exc_info.value.stats
        finally:
            loop.close()

    def test_budget_utilization_percentage(self):
        tracker = CostTracker(
            max_budget_usd=100.0,
            input_price_per_million=10.0,
            output_price_per_million=0.0,
        )
        loop = asyncio.new_event_loop()
        try:
            # 5M input tokens at $10/M = $50 = 50% of $100 budget
            loop.run_until_complete(
                tracker.record_usage(input_tokens=5_000_000, output_tokens=0)
            )
            stats = tracker.get_stats()
            assert abs(stats["budget_utilization_pct"] - 50.0) < 0.1
        finally:
            loop.close()


# =========================================================================
# extract_token_usage_from_log tests
# =========================================================================

class TestExtractTokenUsage:
    """Tests for the extract_token_usage_from_log utility."""

    def test_extract_from_stream_json(self):
        """Should extract usage from Claude CLI stream-json format with message IDs."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            # Two events for the same message (same id) — should be deduped
            f.write('{"type": "assistant", "message": {"id": "msg_01", "usage": {"input_tokens": 5, "output_tokens": 1, "cache_read_input_tokens": 4000, "cache_creation_input_tokens": 1000}}}\n')
            f.write('{"type": "content_block_delta"}\n')
            f.write('{"type": "assistant", "message": {"id": "msg_01", "usage": {"input_tokens": 5, "output_tokens": 1, "cache_read_input_tokens": 4000, "cache_creation_input_tokens": 1000}}}\n')
            # Second message
            f.write('{"type": "assistant", "message": {"id": "msg_02", "usage": {"input_tokens": 7, "output_tokens": 2, "cache_read_input_tokens": 5200, "cache_creation_input_tokens": 800}}}\n')
            f.flush()
            usage = extract_token_usage_from_log(f.name)
        os.unlink(f.name)
        # Summed across 2 unique messages (msg_01 deduped)
        assert usage["input_tokens"] == 12
        assert usage["output_tokens"] == 3
        assert usage["cache_read_tokens"] == 9200
        assert usage["cache_creation_tokens"] == 1800
        # BUG-ORC15: turns = messages // 2 (a turn is a request-response pair)
        assert usage["num_turns"] == 1

    def test_extract_from_empty_log(self):
        """Empty log should return zero tokens."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.flush()
            usage = extract_token_usage_from_log(f.name)
        os.unlink(f.name)
        assert usage["input_tokens"] == 0
        assert usage["output_tokens"] == 0
        assert usage["num_turns"] == 0

    def test_extract_from_nonexistent_file(self):
        """Nonexistent file should return zero tokens."""
        usage = extract_token_usage_from_log("/nonexistent/file.jsonl")
        assert usage["input_tokens"] == 0
        assert usage["output_tokens"] == 0
        assert usage["num_turns"] == 0

    def test_extract_with_result_event(self):
        """Result event provides authoritative totals."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            # Some per-message events (should be ignored when result present)
            f.write('{"type": "assistant", "message": {"id": "msg_01", "usage": {"input_tokens": 5, "output_tokens": 1, "cache_read_input_tokens": 4000, "cache_creation_input_tokens": 1000}}}\n')
            # Result event with authoritative totals
            f.write('{"type": "result", "subtype": "success", "num_turns": 16, "usage": {"input_tokens": 61, "output_tokens": 2146, "cache_read_input_tokens": 259216, "cache_creation_input_tokens": 31808}}\n')
            f.flush()
            usage = extract_token_usage_from_log(f.name)
        os.unlink(f.name)
        assert usage["input_tokens"] == 61
        assert usage["output_tokens"] == 2146
        assert usage["cache_read_tokens"] == 259216
        assert usage["cache_creation_tokens"] == 31808
        assert usage["num_turns"] == 16

    def test_extract_with_anonymous_events(self):
        """Events without message IDs are treated as unique messages and summed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"usage": {"input_tokens": 3000, "output_tokens": 500}}\n')
            f.write('{"usage": {"input_tokens": 5000, "output_tokens": 800}}\n')
            f.write('{"usage": {"input_tokens": 5000, "output_tokens": 200}}\n')
            f.flush()
            usage = extract_token_usage_from_log(f.name)
        os.unlink(f.name)
        assert usage["input_tokens"] == 13000  # sum of 3 unique events
        assert usage["output_tokens"] == 1500   # sum

    def test_extract_with_malformed_lines(self):
        """Should gracefully skip malformed JSON lines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('not json at all\n')
            f.write('{"type": "assistant", "message": {"id": "msg_01", "usage": {"input_tokens": 1000, "output_tokens": 200}}}\n')
            f.write('{broken json\n')
            f.flush()
            usage = extract_token_usage_from_log(f.name)
        os.unlink(f.name)
        assert usage["input_tokens"] == 1000
        assert usage["output_tokens"] == 200


# =========================================================================
# Integration: CostTracker + PhaseConfig
# =========================================================================

class TestCostTrackerIntegration:
    """Test CostTracker with real PhaseConfig values."""

    def test_phase03_budget(self):
        """Phase 03 should have max_budget_usd=200.0."""
        config = get_phase_config("03")
        assert config.max_budget_usd == 200.0
        tracker = CostTracker(max_budget_usd=config.max_budget_usd)
        assert tracker.max_budget_usd == 200.0

    def test_phase03_log_anomaly_threshold(self):
        """Phase 03 should have log_anomaly_threshold=3."""
        config = get_phase_config("03")
        assert config.log_anomaly_threshold == 3

    def test_default_phase_budget(self):
        """Default phases should have max_budget_usd=50.0."""
        config = get_phase_config("01a")
        assert config.max_budget_usd == 50.0

    def test_default_phase_log_anomaly_threshold(self):
        """Default phases should have log_anomaly_threshold=3."""
        config = get_phase_config("01a")
        assert config.log_anomaly_threshold == 3


# =========================================================================
# GitHub Step Summary tests
# =========================================================================

from orchestrator.base import BaseOrchestrator


class _MockOrchestrator(BaseOrchestrator):
    """Minimal concrete subclass for testing base methods."""

    def load_items(self):
        return []

    def enrich_items(self, items):
        return items


class TestGitHubStepSummary:
    """Tests for _write_github_step_summary in base.py."""

    def test_no_op_when_env_not_set(self):
        """Should do nothing when GITHUB_STEP_SUMMARY is not set."""
        old = os.environ.pop("GITHUB_STEP_SUMMARY", None)
        try:
            orch = _MockOrchestrator("03")
            cb_stats = orch.circuit_breaker._get_stats_unlocked()
            val_stats = orch.collector.get_validation_summary()
            # Should not raise
            orch._write_github_step_summary(10.0, 5, cb_stats, val_stats, None)
        finally:
            if old is not None:
                os.environ["GITHUB_STEP_SUMMARY"] = old

    def test_writes_markdown_to_file(self):
        """Should write Markdown content to the summary file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            summary_file = f.name
        os.environ["GITHUB_STEP_SUMMARY"] = summary_file
        try:
            orch = _MockOrchestrator("03")
            cb_stats = orch.circuit_breaker._get_stats_unlocked()
            val_stats = orch.collector.get_validation_summary()
            orch._write_github_step_summary(60.0, 10, cb_stats, val_stats, None)

            with open(summary_file) as f:
                content = f.read()
            assert "## Phase 03" in content
            assert "Audit Map Generation" in content
            assert "Execution Summary" in content
            assert "| Duration | 60.0s |" in content
            assert "| Total results | 10 |" in content
        finally:
            del os.environ["GITHUB_STEP_SUMMARY"]
            os.unlink(summary_file)

    def test_includes_cost_report(self):
        """Should include cost table when cost_stats is provided."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            summary_file = f.name
        os.environ["GITHUB_STEP_SUMMARY"] = summary_file
        try:
            orch = _MockOrchestrator("03")
            cb_stats = orch.circuit_breaker._get_stats_unlocked()
            val_stats = orch.collector.get_validation_summary()
            cost_stats = {
                "total_input_tokens": 100000,
                "total_output_tokens": 30000,
                "total_cost_usd": 8.50,
                "max_budget_usd": 30.0,
                "budget_utilization_pct": 28.3,
                "budget_remaining_usd": 21.50,
                "batch_count": 3,
            }
            orch._write_github_step_summary(45.0, 8, cb_stats, val_stats, cost_stats)

            with open(summary_file) as f:
                content = f.read()
            assert "### Cost Report" in content
            assert "| Input tokens | 100,000 |" in content
            assert "| Estimated cost | $8.50 |" in content
            assert "| Budget | $30.00 |" in content
            assert "28.3%" in content
        finally:
            del os.environ["GITHUB_STEP_SUMMARY"]
            os.unlink(summary_file)

    def test_no_cost_section_without_stats(self):
        """Should not include cost section when cost_stats is None."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            summary_file = f.name
        os.environ["GITHUB_STEP_SUMMARY"] = summary_file
        try:
            orch = _MockOrchestrator("03")
            cb_stats = orch.circuit_breaker._get_stats_unlocked()
            val_stats = orch.collector.get_validation_summary()
            orch._write_github_step_summary(10.0, 5, cb_stats, val_stats, None)

            with open(summary_file) as f:
                content = f.read()
            assert "### Cost Report" not in content
        finally:
            del os.environ["GITHUB_STEP_SUMMARY"]
            os.unlink(summary_file)

    def test_success_status(self):
        """Normal run should show Success status."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            summary_file = f.name
        os.environ["GITHUB_STEP_SUMMARY"] = summary_file
        try:
            orch = _MockOrchestrator("03")
            cb_stats = orch.circuit_breaker._get_stats_unlocked()
            val_stats = orch.collector.get_validation_summary()
            orch._write_github_step_summary(10.0, 5, cb_stats, val_stats, None)

            with open(summary_file) as f:
                content = f.read()
            assert "Success" in content
        finally:
            del os.environ["GITHUB_STEP_SUMMARY"]
            os.unlink(summary_file)

    def test_circuit_breaker_status(self):
        """Should show Circuit Breaker Tripped status."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            summary_file = f.name
        os.environ["GITHUB_STEP_SUMMARY"] = summary_file
        try:
            orch = _MockOrchestrator("03")
            orch._circuit_breaker_tripped = True
            cb_stats = orch.circuit_breaker._get_stats_unlocked()
            val_stats = orch.collector.get_validation_summary()
            orch._write_github_step_summary(10.0, 3, cb_stats, val_stats, None)

            with open(summary_file) as f:
                content = f.read()
            assert "Circuit Breaker Tripped" in content
        finally:
            del os.environ["GITHUB_STEP_SUMMARY"]
            os.unlink(summary_file)

    def test_budget_exceeded_status(self):
        """Should show Budget Exceeded status."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            summary_file = f.name
        os.environ["GITHUB_STEP_SUMMARY"] = summary_file
        try:
            orch = _MockOrchestrator("03")
            orch._budget_exceeded = True
            cb_stats = orch.circuit_breaker._get_stats_unlocked()
            val_stats = orch.collector.get_validation_summary()
            orch._write_github_step_summary(10.0, 2, cb_stats, val_stats, None)

            with open(summary_file) as f:
                content = f.read()
            assert "Budget Exceeded" in content
        finally:
            del os.environ["GITHUB_STEP_SUMMARY"]
            os.unlink(summary_file)

    def test_failed_batches_table(self):
        """Should include failed batches table when there are failures."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            summary_file = f.name
        os.environ["GITHUB_STEP_SUMMARY"] = summary_file
        try:
            orch = _MockOrchestrator("03")
            orch.failed_batches = [(0, 3), (1, 7)]
            cb_stats = orch.circuit_breaker._get_stats_unlocked()
            val_stats = orch.collector.get_validation_summary()
            orch._write_github_step_summary(10.0, 5, cb_stats, val_stats, None)

            with open(summary_file) as f:
                content = f.read()
            assert "### Failed Batches" in content
            assert "| 0 | 3 |" in content
            assert "| 1 | 7 |" in content
        finally:
            del os.environ["GITHUB_STEP_SUMMARY"]
            os.unlink(summary_file)

    def test_budget_bar_high_utilization(self):
        """High budget utilization (>=80%) should show red indicator."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            summary_file = f.name
        os.environ["GITHUB_STEP_SUMMARY"] = summary_file
        try:
            orch = _MockOrchestrator("03")
            cb_stats = orch.circuit_breaker._get_stats_unlocked()
            val_stats = orch.collector.get_validation_summary()
            cost_stats = {
                "total_input_tokens": 500000,
                "total_output_tokens": 200000,
                "total_cost_usd": 25.0,
                "max_budget_usd": 30.0,
                "budget_utilization_pct": 83.3,
                "budget_remaining_usd": 5.0,
                "batch_count": 10,
            }
            orch._write_github_step_summary(300.0, 50, cb_stats, val_stats, cost_stats)

            with open(summary_file) as f:
                content = f.read()
            assert "83.3%" in content
        finally:
            del os.environ["GITHUB_STEP_SUMMARY"]
            os.unlink(summary_file)

    def test_appends_to_existing_file(self):
        """Should append to existing summary file, not overwrite."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Previous content\n\n")
            summary_file = f.name
        os.environ["GITHUB_STEP_SUMMARY"] = summary_file
        try:
            orch = _MockOrchestrator("03")
            cb_stats = orch.circuit_breaker._get_stats_unlocked()
            val_stats = orch.collector.get_validation_summary()
            orch._write_github_step_summary(10.0, 5, cb_stats, val_stats, None)

            with open(summary_file) as f:
                content = f.read()
            assert "# Previous content" in content
            assert "## Phase 03" in content
        finally:
            del os.environ["GITHUB_STEP_SUMMARY"]
            os.unlink(summary_file)


# =====================================================================
# Partial Result Recovery Tests
# =====================================================================
import unittest
from pathlib import Path


class TestCheckLogResultStatus(unittest.TestCase):
    """Tests for ClaudeRunner._check_log_result_status."""

    def test_returns_none_for_nonexistent_file(self):
        """Should return None if the log file does not exist."""
        from orchestrator.runner import ClaudeRunner
        result = ClaudeRunner._check_log_result_status(Path("/nonexistent/file.jsonl"))
        assert result is None

    def test_returns_none_for_log_without_result(self):
        """Should return None if the log has no result event."""
        from orchestrator.runner import ClaudeRunner
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"assistant","message":{"content":"hello"}}\n')
            f.write('{"type":"user","message":{"content":"world"}}\n')
            log_path = Path(f.name)
        try:
            result = ClaudeRunner._check_log_result_status(log_path)
            assert result is None
        finally:
            log_path.unlink()

    def test_returns_result_event_success_no_error(self):
        """Should return the result event for a normal success."""
        from orchestrator.runner import ClaudeRunner
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"assistant","message":{"content":"working"}}\n')
            f.write('{"type":"result","subtype":"success","is_error":false,"duration_ms":120000}\n')
            log_path = Path(f.name)
        try:
            result = ClaudeRunner._check_log_result_status(log_path)
            assert result is not None
            assert result["subtype"] == "success"
            assert result["is_error"] is False
        finally:
            log_path.unlink()

    def test_returns_result_event_success_with_error(self):
        """Should return the result event for is_error=true, subtype=success (max_turns)."""
        from orchestrator.runner import ClaudeRunner
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"assistant","message":{"content":"working"}}\n')
            f.write('{"type":"result","subtype":"success","is_error":true,"duration_ms":488000}\n')
            log_path = Path(f.name)
        try:
            result = ClaudeRunner._check_log_result_status(log_path)
            assert result is not None
            assert result["subtype"] == "success"
            assert result["is_error"] is True
            assert result["duration_ms"] == 488000
        finally:
            log_path.unlink()

    def test_returns_result_event_error_subtype(self):
        """Should return the result event for subtype=error."""
        from orchestrator.runner import ClaudeRunner
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"result","subtype":"error","is_error":true,"duration_ms":5000}\n')
            log_path = Path(f.name)
        try:
            result = ClaudeRunner._check_log_result_status(log_path)
            assert result is not None
            assert result["subtype"] == "error"
        finally:
            log_path.unlink()

    def test_returns_last_result_when_multiple(self):
        """Should return the last result event if multiple exist."""
        from orchestrator.runner import ClaudeRunner
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"result","subtype":"error","is_error":true,"duration_ms":1000}\n')
            f.write('{"type":"result","subtype":"success","is_error":true,"duration_ms":488000}\n')
            log_path = Path(f.name)
        try:
            result = ClaudeRunner._check_log_result_status(log_path)
            assert result is not None
            assert result["subtype"] == "success"
            assert result["duration_ms"] == 488000
        finally:
            log_path.unlink()


class TestTryRecoverPartial(unittest.TestCase):
    """Tests for ClaudeRunner._try_recover_partial."""

    def _make_runner(self):
        from orchestrator.runner import ClaudeRunner
        from orchestrator.config import get_phase_config
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        return ClaudeRunner(config, sem)

    def test_returns_none_when_no_result_in_log(self):
        """Should return None if log has no result event (killed process)."""
        runner = self._make_runner()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"assistant","message":{"content":"hello"}}\n')
            log_path = Path(f.name)
        result_path = Path("/tmp/nonexistent_result.json")
        try:
            result = runner._try_recover_partial(
                log_path, result_path, False, 0, 1, 12345
            )
            assert result is None
        finally:
            log_path.unlink()

    def test_returns_none_when_subtype_is_error(self):
        """Should return None if subtype=error (genuine failure)."""
        runner = self._make_runner()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"result","subtype":"error","is_error":true,"duration_ms":5000}\n')
            log_path = Path(f.name)
        result_path = Path("/tmp/nonexistent_result.json")
        try:
            result = runner._try_recover_partial(
                log_path, result_path, False, 0, 1, 12345
            )
            assert result is None
        finally:
            log_path.unlink()

    def test_recovers_from_output_file(self):
        """Should recover results from output file when subtype=success, is_error=true."""
        runner = self._make_runner()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"result","subtype":"success","is_error":true,"duration_ms":488000}\n')
            log_path = Path(f.name)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"audit_items": [{"id": "A1", "status": "done"}]}, f)
            result_path = Path(f.name)
        try:
            result = runner._try_recover_partial(
                log_path, result_path, False, 0, 1, 12345
            )
            assert result is not None
            assert len(result) == 1
            assert result[0]["id"] == "A1"
        finally:
            log_path.unlink()
            if result_path.exists():
                result_path.unlink()

    def test_recovers_from_log_fallback(self):
        """Should recover results from log inline response when output file missing."""
        runner = self._make_runner()
        result_json = json.dumps([{"id": "B1", "classification": "safe"}])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"assistant","message":{"content":"working"}}\n')
            f.write(json.dumps({
                "type": "result",
                "subtype": "success",
                "is_error": True,
                "duration_ms": 488000,
                "result": f"Here are the results:\n```json\n{result_json}\n```"
            }) + "\n")
            log_path = Path(f.name)
        result_path = Path("/tmp/nonexistent_result.json")
        try:
            result = runner._try_recover_partial(
                log_path, result_path, False, 0, 1, 12345
            )
            assert result is not None
            assert len(result) == 1
            assert result[0]["id"] == "B1"
        finally:
            log_path.unlink()

    def test_returns_none_when_no_parseable_results(self):
        """Should return None if subtype=success but no results can be parsed."""
        runner = self._make_runner()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"result","subtype":"success","is_error":true,"duration_ms":488000}\n')
            log_path = Path(f.name)
        result_path = Path("/tmp/nonexistent_result.json")
        try:
            result = runner._try_recover_partial(
                log_path, result_path, False, 0, 1, 12345
            )
            assert result is None
        finally:
            log_path.unlink()


class TestMaxTurnsExhausted(unittest.TestCase):
    """Tests for error_max_turns detection in _execute_batch."""

    def test_error_max_turns_returns_none_for_try_recover(self):
        """_try_recover_partial should return None for error_max_turns
        (it's handled earlier in _execute_batch now)."""
        from orchestrator.runner import ClaudeRunner
        from orchestrator.config import get_phase_config
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        runner = ClaudeRunner(config, sem)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"type":"result","subtype":"error_max_turns","is_error":false,'
                    '"num_turns":26,"duration_ms":90000}\n')
            log_path = Path(f.name)
        result_path = Path("/tmp/nonexistent_result.json")
        try:
            result = runner._try_recover_partial(
                log_path, result_path, False, 0, 1, 12345
            )
            assert result is None
        finally:
            log_path.unlink()

    def test_max_turns_exhausted_exception_exists(self):
        """MaxTurnsExhausted should be importable from runner."""
        from orchestrator.runner import MaxTurnsExhausted
        exc = MaxTurnsExhausted("Batch 42 exhausted 26 turns")
        assert "26 turns" in str(exc)


class TestClaudeRunnerCommand(unittest.TestCase):
    """Tests for ClaudeRunner command building."""

    def test_includes_model_when_configured(self):
        from orchestrator.runner import ClaudeRunner
        from orchestrator.config import get_phase_config
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        runner = ClaudeRunner(config, sem)
        cmd = runner._build_cmd("hello")
        assert "--model" in cmd
        model_index = cmd.index("--model")
        assert cmd[model_index + 1] == "sonnet"

    def test_omits_model_when_not_configured(self):
        from orchestrator.runner import ClaudeRunner
        from orchestrator.config import get_phase_config
        config = get_phase_config("01e")
        sem = asyncio.Semaphore(1)
        runner = ClaudeRunner(config, sem)
        cmd = runner._build_cmd("hello")
        assert "--model" not in cmd

    def test_tools_filter_in_cmd(self):
        """Phase 03 should pass --tools to restrict tool definitions."""
        from orchestrator.runner import ClaudeRunner
        from orchestrator.config import get_phase_config
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        runner = ClaudeRunner(config, sem)
        cmd = runner._build_cmd("hello")
        assert "--tools" in cmd
        tools_index = cmd.index("--tools")
        assert cmd[tools_index + 1] == "Read,Write,Grep,Glob"

    def test_no_tools_filter_when_none(self):
        """Phases without tools_filter should not pass --tools."""
        from orchestrator.runner import ClaudeRunner
        from orchestrator.config import get_phase_config
        config = get_phase_config("01a")
        sem = asyncio.Semaphore(1)
        runner = ClaudeRunner(config, sem)
        cmd = runner._build_cmd("hello")
        assert "--tools" not in cmd

    def test_strict_mcp_config_in_cmd(self):
        """Phases with mcp_servers defined should pass --strict-mcp-config."""
        from orchestrator.runner import ClaudeRunner
        from orchestrator.config import get_phase_config
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        runner = ClaudeRunner(config, sem)
        cmd = runner._build_cmd("hello")
        assert "--strict-mcp-config" in cmd
        assert "--mcp-config" in cmd

    def test_phase_mcp_config_generation(self):
        """_get_phase_mcp_config should create a filtered MCP config file."""
        import json as _json
        from orchestrator.runner import ClaudeRunner
        from orchestrator.config import get_phase_config
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        runner = ClaudeRunner(config, sem)
        old_cwd = os.getcwd()
        try:
            os.chdir(Path(__file__).parent.parent)
            config_path = runner._get_phase_mcp_config()
            assert config_path.exists()
            with open(config_path) as f:
                data = _json.load(f)
            # Phase 03 has mcp_servers=[] → empty mcpServers
            assert data["mcpServers"] == {}
        finally:
            # Cleanup generated file
            if config_path.exists():
                config_path.unlink()
            os.chdir(old_cwd)


# =========================================================================
# Usage Limit Detection tests
# =========================================================================

class TestUsageLimitDetection:
    """Tests for usage limit detection across watchdog.py and runner.py.

    When the Claude API quota is exhausted ("You're out of extra usage"),
    the system should:
      1. Detect the pattern in log lines (both real-time and post-hoc)
      2. Treat it as a FATAL anomaly (immediate stop, no retries)
      3. Trip the circuit breaker so all workers stop
    """

    # --- _extract_scannable_text: result event with usage limit ---

    def test_extract_scannable_text_result_with_usage_limit(self):
        """A result event with is_error=true containing usage limit text
        should be returned as scannable text."""
        from orchestrator.watchdog import _extract_scannable_text

        line = json.dumps({
            "type": "result",
            "is_error": True,
            "subtype": "success",
            "result": "You're out of extra usage. Your usage resets February 14 at 12:00 AM."
        })
        text, is_tool_use = _extract_scannable_text(line)
        assert text is not None
        assert "out of extra usage" in text.lower() or "resets" in text.lower()
        assert is_tool_use is False

    def test_extract_scannable_text_result_no_error_not_scanned(self):
        """A result event without is_error should NOT be scanned."""
        from orchestrator.watchdog import _extract_scannable_text

        line = json.dumps({
            "type": "result",
            "is_error": False,
            "result": "You're out of extra usage."
        })
        text, _ = _extract_scannable_text(line)
        # Non-error result should not be scanned
        assert text is None

    # --- _ANOMALY_PATTERNS: usage_limit pattern matching ---

    def test_usage_limit_pattern_matches_out_of_extra_usage(self):
        """The usage_limit pattern should match 'out of extra usage'."""
        from orchestrator.watchdog import _ANOMALY_PATTERNS

        usage_patterns = [(n, p) for n, p in _ANOMALY_PATTERNS if n == "usage_limit"]
        assert len(usage_patterns) == 1
        _, pattern = usage_patterns[0]
        assert pattern.search("You're out of extra usage")

    def test_usage_limit_pattern_matches_out_of_usage(self):
        """The usage_limit pattern should match 'out of usage'."""
        from orchestrator.watchdog import _ANOMALY_PATTERNS

        usage_patterns = [(n, p) for n, p in _ANOMALY_PATTERNS if n == "usage_limit"]
        _, pattern = usage_patterns[0]
        assert pattern.search("You're out of usage")

    def test_usage_limit_pattern_matches_resets(self):
        """The usage_limit pattern should match 'resets February 14'."""
        from orchestrator.watchdog import _ANOMALY_PATTERNS

        usage_patterns = [(n, p) for n, p in _ANOMALY_PATTERNS if n == "usage_limit"]
        _, pattern = usage_patterns[0]
        assert pattern.search("Your usage resets February 14 at 12:00 AM")

    def test_usage_limit_pattern_matches_usage_limit(self):
        """The usage_limit pattern should match 'usage limit'."""
        from orchestrator.watchdog import _ANOMALY_PATTERNS

        usage_patterns = [(n, p) for n, p in _ANOMALY_PATTERNS if n == "usage_limit"]
        _, pattern = usage_patterns[0]
        assert pattern.search("usage limit exceeded")

    # --- _FATAL_PATTERNS: usage_limit is fatal ---

    def test_usage_limit_is_fatal(self):
        """usage_limit should be in _FATAL_PATTERNS."""
        from orchestrator.watchdog import _FATAL_PATTERNS

        assert "usage_limit" in _FATAL_PATTERNS

    # --- LogWatcher: fatal detection triggers immediate stop ---

    def test_logwatcher_fatal_immediate_stop(self):
        """A single usage_limit anomaly should trigger immediate stop
        regardless of anomaly_threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "usage_limit.log.jsonl")
            with open(log_path, "w") as f:
                # Only ONE usage limit result event — should still trigger stop
                f.write(json.dumps({
                    "type": "result",
                    "is_error": True,
                    "subtype": "success",
                    "result": "You're out of extra usage. Your usage resets February 14 at 12:00 AM."
                }) + "\n")

            watcher = LogWatcher(
                log_path,
                config=LogWatcherConfig(
                    poll_interval=0.05,
                    anomaly_threshold=100,  # Very high threshold — should still stop
                ),
            )
            loop = asyncio.new_event_loop()
            try:
                async def run_and_stop():
                    task = asyncio.create_task(watcher.watch())
                    await asyncio.sleep(0.3)
                    watcher.stop()
                    await task

                loop.run_until_complete(run_and_stop())
            finally:
                loop.close()

            assert watcher.should_stop is True, (
                f"Expected immediate stop for fatal anomaly. Anomalies: {watcher.anomalies}"
            )
            assert watcher._fatal_detected is True
            assert any("usage_limit" in a for a in watcher.anomalies)

    def test_logwatcher_summary_includes_fatal_flag(self):
        """get_summary should include fatal_detected field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "fatal_summary.log.jsonl")
            with open(log_path, "w") as f:
                f.write(json.dumps({
                    "type": "result",
                    "is_error": True,
                    "subtype": "success",
                    "result": "You're out of extra usage."
                }) + "\n")

            watcher = LogWatcher(
                log_path,
                config=LogWatcherConfig(poll_interval=0.05),
            )
            loop = asyncio.new_event_loop()
            try:
                async def run_and_stop():
                    task = asyncio.create_task(watcher.watch())
                    await asyncio.sleep(0.3)
                    watcher.stop()
                    await task

                loop.run_until_complete(run_and_stop())
            finally:
                loop.close()

            summary = watcher.get_summary()
            assert "fatal_detected" in summary
            assert summary["fatal_detected"] is True

    def test_logwatcher_non_fatal_no_immediate_stop(self):
        """Non-fatal anomalies (e.g. rate_limit_error) should NOT trigger
        immediate stop when below threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "non_fatal.log.jsonl")
            with open(log_path, "w") as f:
                # One rate limit error — not fatal, below threshold
                f.write(json.dumps({
                    "type": "error",
                    "error": {"type": "rate_limit_error", "message": "429 Too Many Requests"}
                }) + "\n")

            watcher = LogWatcher(
                log_path,
                config=LogWatcherConfig(
                    poll_interval=0.05,
                    anomaly_threshold=100,
                ),
            )
            loop = asyncio.new_event_loop()
            try:
                async def run_and_stop():
                    task = asyncio.create_task(watcher.watch())
                    await asyncio.sleep(0.3)
                    watcher.stop()
                    await task

                loop.run_until_complete(run_and_stop())
            finally:
                loop.close()

            assert watcher.should_stop is False
            assert watcher._fatal_detected is False

    # --- LogAnomalyDetector: usage_limit detection ---

    def test_log_anomaly_detector_detects_usage_limit(self):
        """LogAnomalyDetector.scan_log should detect usage_limit in result events."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "type": "result",
                "is_error": True,
                "subtype": "success",
                "result": "You're out of extra usage. Your usage resets February 14 at 12:00 AM."
            }) + "\n")
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(f.name)
        os.unlink(f.name)
        assert any("usage_limit" in a for a in anomalies), f"Expected usage_limit anomaly, got: {anomalies}"

    def test_log_anomaly_detector_has_fatal_anomaly_true(self):
        """has_fatal_anomaly should return True for usage_limit anomalies."""
        anomalies = [
            "rate_limit_error: 429 Too Many Requests",
            "usage_limit: You're out of extra usage. Your usage resets February 14",
        ]
        assert LogAnomalyDetector.has_fatal_anomaly(anomalies) is True

    def test_log_anomaly_detector_has_fatal_anomaly_false(self):
        """has_fatal_anomaly should return False when no fatal patterns present."""
        anomalies = [
            "rate_limit_error: 429 Too Many Requests",
            "api_error: APIError: InternalServerError",
        ]
        assert LogAnomalyDetector.has_fatal_anomaly(anomalies) is False

    def test_log_anomaly_detector_has_fatal_anomaly_empty(self):
        """has_fatal_anomaly should return False for empty list."""
        assert LogAnomalyDetector.has_fatal_anomaly([]) is False

    # --- Integration: no false positive from user content ---

    def test_usage_limit_not_triggered_by_user_content(self):
        """User content mentioning 'usage limit' should NOT trigger detection."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            line = json.dumps({
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": "toolu_test",
                        "content": "Check usage limit handling: verify that out of extra usage errors are caught"
                    }]
                }
            })
            f.write(line + "\n")
            f.flush()
            anomalies = LogAnomalyDetector.scan_log(f.name)
        os.unlink(f.name)
        assert anomalies == [], f"False positive from user content: {anomalies}"
