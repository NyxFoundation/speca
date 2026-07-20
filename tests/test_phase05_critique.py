"""Tests for Phase 05 (Finding Critique) — schema, config, and wiring (issue #53).

Covers:
- The CritiquedItem / Phase05Partial data contract, including the
  no-fabricated-citations honesty guard.
- The "05" PhaseConfig entry and its dependency chain.
- Default-pipeline isolation: phases 01a..04 are unchanged when 05 is
  not selected.
- Factory wiring: Phase05Orchestrator selection and pluggable search
  backend (websearch default, graceful degradation with "none").
- Phase05Orchestrator load/early-exit/enrich behavior.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add workspace root to sys.path using absolute path calculation (BUG-SCH13)
_WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

# Mock heavy dependencies before importing scripts, using patch.dict for proper cleanup (BUG-SCH12)
_MOCK_MODULES = {"tqdm": MagicMock(), "aiofiles": MagicMock(), "anthropic": MagicMock(), "tenacity": MagicMock()}
_patcher = patch.dict(sys.modules, _MOCK_MODULES)
_patcher.start()

from scripts.orchestrator import base as base_mod
from scripts.orchestrator.base import Phase05Orchestrator, PhaseAbortError
from scripts.orchestrator.collector import _PHASE_OUTPUT_MODELS
from scripts.orchestrator.config import PHASE_CONFIGS, get_phase_chain, get_phase_config
from scripts.orchestrator.factory import create_orchestrator
from scripts.orchestrator.providers import (
    NullSearchBackend,
    SearchBackendName,
    WebSearchBackend,
    resolve_search_backend,
)
from scripts.orchestrator.schemas import (
    CritiquedItem,
    CritiqueVerdict,
    EvidenceProvenance,
    GlossaryEntry,
    Phase05Partial,
    SearchTraceStep,
    validate_critiqued_item,
)

_patcher.stop()


# ---------------------------------------------------------------------------
# Schema: CritiquedItem / Phase05Partial
# ---------------------------------------------------------------------------

class TestCritiqueSchemas(unittest.TestCase):
    def _full_item(self) -> dict:
        return {
            "property_id": "PROP-ABC-001",
            "prior_verdict": "CONFIRMED_VULNERABILITY",
            "critique_verdict": "LIKELY_FP",
            "glossary": [
                {
                    "term": "HogEx",
                    "definition": "The hogswap extension transaction placed at the end of each block.",
                    "source_url": "https://example.org/spec/hogex",
                }
            ],
            "search_trace": [
                {
                    "step": 1,
                    "query": "litecoin mweb hogex integration transaction",
                    "urls": ["https://example.org/spec/hogex"],
                    "found": "HogEx is consensus-mandated to be the final tx.",
                    "inference": "The reported ordering issue is intended behavior.",
                }
            ],
            "code_rechecks": [
                {
                    "file": "src/consensus/tx_verify.cpp",
                    "lines": "120-160",
                    "observation": "The cited guard exists and rejects the suspect input.",
                }
            ],
            "related_cves": [],
            "rationale": "Spec documents the behavior as intended; cited code re-read confirms the guard.",
            "evidence_provenance": "external+internal",
            "search_backend": "websearch",
        }

    def test_full_item_validates(self):
        item = CritiquedItem.model_validate(self._full_item())
        self.assertEqual(item.critique_verdict, CritiqueVerdict.LIKELY_FP)
        self.assertEqual(item.evidence_provenance, EvidenceProvenance.EXTERNAL_AND_INTERNAL)
        self.assertEqual(item.glossary[0].term, "HogEx")
        self.assertEqual(item.search_trace[0].step, 1)

    def test_verdict_enum_values(self):
        self.assertEqual(CritiqueVerdict.CONFIRMED.value, "CONFIRMED")
        self.assertEqual(CritiqueVerdict.LIKELY_FP.value, "LIKELY_FP")
        self.assertEqual(CritiqueVerdict.INSUFFICIENT_CONTEXT.value, "INSUFFICIENT_CONTEXT")
        self.assertEqual(len(CritiqueVerdict), 3)

    def test_minimal_item_defaults(self):
        item = CritiquedItem(property_id="P1", critique_verdict="CONFIRMED", rationale="ok")
        self.assertEqual(item.search_backend, "none")
        self.assertEqual(item.evidence_provenance, EvidenceProvenance.INTERNAL_ONLY)
        self.assertEqual(item.glossary, [])
        self.assertEqual(item.search_trace, [])
        self.assertEqual(item.related_cves, [])

    def test_degraded_mode_item_validates(self):
        """search_backend none with internal-only evidence and no URLs is valid."""
        item = CritiquedItem.model_validate({
            "property_id": "P1",
            "prior_verdict": "CONFIRMED_POTENTIAL",
            "critique_verdict": "INSUFFICIENT_CONTEXT",
            "glossary": [{"term": "MWEB", "definition": "internal knowledge", "source_url": ""}],
            "search_trace": [{"step": 1, "query": "", "urls": [], "found": "no search backend", "inference": ""}],
            "rationale": "No external search was performed; internal evidence inconclusive.",
            "evidence_provenance": "internal-only",
            "search_backend": "none",
        })
        self.assertEqual(item.search_backend, "none")

    def test_fabricated_search_urls_rejected(self):
        """URLs in the search trace without a search backend are fabricated."""
        data = self._full_item()
        data["search_backend"] = "none"
        data["evidence_provenance"] = "internal-only"
        data["glossary"] = []
        with pytest.raises(Exception) as exc_info:
            CritiquedItem.model_validate(data)
        self.assertIn("fabricated", str(exc_info.value))

    def test_fabricated_glossary_source_rejected(self):
        data = self._full_item()
        data["search_backend"] = "none"
        data["evidence_provenance"] = "internal-only"
        data["search_trace"] = []
        with pytest.raises(Exception) as exc_info:
            CritiquedItem.model_validate(data)
        self.assertIn("fabricated", str(exc_info.value))

    def test_external_provenance_without_backend_rejected(self):
        data = self._full_item()
        data["search_backend"] = "none"
        data["search_trace"] = []
        data["glossary"] = []
        # evidence_provenance still claims external evidence
        with pytest.raises(Exception):
            CritiquedItem.model_validate(data)

    def test_phase05_partial_roundtrip(self):
        partial = Phase05Partial.model_validate({
            "critiqued_items": [self._full_item()],
            "metadata": {"phase": "05", "worker_id": 0},
        })
        self.assertEqual(len(partial.critiqued_items), 1)
        dumped = partial.model_dump()
        self.assertIn("critiqued_items", dumped)

    def test_phase05_partial_empty(self):
        partial = Phase05Partial()
        self.assertEqual(partial.critiqued_items, [])
        self.assertEqual(partial.source_files, [])

    def test_validate_critiqued_item_helper(self):
        item, errors = validate_critiqued_item(self._full_item())
        self.assertIsNotNone(item)
        self.assertEqual(errors, [])

    def test_validate_critiqued_item_missing_fields(self):
        item, errors = validate_critiqued_item({"property_id": ""})
        self.assertIsNotNone(item)
        self.assertIn("property_id is empty", errors)
        self.assertIn("critique_verdict is empty", errors)
        self.assertIn("rationale is empty", errors)

    def test_validate_critiqued_item_invalid(self):
        item, errors = validate_critiqued_item({"glossary": "not-a-list"})
        self.assertIsNone(item)
        self.assertTrue(errors)

    def test_glossary_and_trace_defaults(self):
        entry = GlossaryEntry(term="MWEB")
        self.assertEqual(entry.source_url, "")
        step = SearchTraceStep()
        self.assertEqual(step.urls, [])


# ---------------------------------------------------------------------------
# Config: "05" PhaseConfig + default-pipeline isolation
# ---------------------------------------------------------------------------

class TestPhase05Config(unittest.TestCase):
    def test_phase05_in_configs(self):
        self.assertIn("05", PHASE_CONFIGS)
        cfg = get_phase_config("05")
        self.assertEqual(cfg.phase_id, "05")
        self.assertEqual(cfg.name, "Finding Critique")

    def test_phase05_config_values(self):
        cfg = PHASE_CONFIGS["05"]
        self.assertEqual(cfg.depends_on, ["04"])
        self.assertEqual(cfg.input_patterns, ["outputs/04_PARTIAL_*.json"])
        self.assertEqual(cfg.output_pattern, "outputs/05_PARTIAL_*.json")
        self.assertEqual(cfg.batch_strategy, "count")
        self.assertEqual(cfg.max_batch_size, 1)
        self.assertEqual(cfg.item_id_field, "property_id")
        self.assertEqual(cfg.result_key, "critiqued_items")
        self.assertEqual(cfg.model, "sonnet")
        self.assertEqual(cfg.mcp_servers, [])
        self.assertEqual(cfg.search_backend, "websearch")

    def test_phase05_default_tools_include_search(self):
        cfg = PHASE_CONFIGS["05"]
        self.assertIn("WebSearch", cfg.tools_filter)
        self.assertIn("WebFetch", cfg.tools_filter)
        for tool in ("Read", "Write", "Grep", "Glob"):
            self.assertIn(tool, cfg.tools_filter)

    def test_phase05_context_fields(self):
        cfg = PHASE_CONFIGS["05"]
        for field in ("property_id", "review", "audit_result", "text", "assertion"):
            self.assertIn(field, cfg.context_fields)

    def test_phase_chain_to_05_includes_04(self):
        chain = get_phase_chain("05")
        self.assertEqual(chain[-1], "05")
        self.assertIn("04", chain)
        self.assertIn("03", chain)
        self.assertIn("01a", chain)

    def test_default_pipeline_unchanged_without_05(self):
        """Nothing depends on 05: --target 04 must not pull it in."""
        self.assertNotIn("05", get_phase_chain("04"))
        for pid, cfg in PHASE_CONFIGS.items():
            if pid == "05":
                continue
            self.assertNotIn("05", cfg.depends_on)

    def test_non_05_phases_have_no_search_backend(self):
        for pid, cfg in PHASE_CONFIGS.items():
            if pid == "05":
                continue
            self.assertEqual(
                cfg.search_backend, "none",
                f"Phase {pid} should not enable a search backend",
            )

    def test_collector_knows_phase05(self):
        self.assertIn("05", _PHASE_OUTPUT_MODELS)
        self.assertIs(_PHASE_OUTPUT_MODELS["05"], Phase05Partial)


# ---------------------------------------------------------------------------
# Providers: pluggable search backend
# ---------------------------------------------------------------------------

class TestSearchBackends(unittest.TestCase):
    def test_backend_names(self):
        self.assertEqual(SearchBackendName.WEBSEARCH.value, "websearch")
        self.assertEqual(SearchBackendName.NONE.value, "none")

    def test_websearch_backend(self):
        backend = resolve_search_backend("websearch")
        self.assertIsInstance(backend, WebSearchBackend)
        self.assertEqual(backend.worker_tools(), ["WebSearch", "WebFetch"])
        self.assertEqual(backend.provenance(), "external+internal")

    def test_null_backend(self):
        backend = resolve_search_backend("none")
        self.assertIsInstance(backend, NullSearchBackend)
        self.assertEqual(backend.worker_tools(), [])
        self.assertEqual(backend.provenance(), "internal-only")

    def test_unknown_backend_rejected(self):
        with pytest.raises(ValueError, match="Unknown search backend"):
            resolve_search_backend("google")


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------

class TestFactoryWiring(unittest.TestCase):
    def test_creates_phase05_orchestrator(self):
        orch = create_orchestrator("05", num_workers=1, max_concurrent=1)
        self.assertIsInstance(orch, Phase05Orchestrator)
        self.assertEqual(orch.config.phase_id, "05")

    def test_default_backend_keeps_search_tools(self):
        orch = create_orchestrator("05", num_workers=1, max_concurrent=1)
        self.assertEqual(orch.config.search_backend, "websearch")
        self.assertIn("WebSearch", orch.config.tools_filter)
        self.assertIn("WebFetch", orch.config.tools_filter)

    def test_none_backend_strips_search_tools(self):
        orch = create_orchestrator(
            "05", num_workers=1, max_concurrent=1, search_backend="none"
        )
        self.assertEqual(orch.config.search_backend, "none")
        self.assertNotIn("WebSearch", orch.config.tools_filter)
        self.assertNotIn("WebFetch", orch.config.tools_filter)
        # Code re-verification and output writing still work
        for tool in ("Read", "Write", "Grep", "Glob"):
            self.assertIn(tool, orch.config.tools_filter)

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown search backend"):
            create_orchestrator(
                "05", num_workers=1, max_concurrent=1, search_backend="bing"
            )

    def test_global_config_not_mutated(self):
        """Backend overrides must only touch the orchestrator's config copy."""
        create_orchestrator("05", num_workers=1, max_concurrent=1, search_backend="none")
        cfg = PHASE_CONFIGS["05"]
        self.assertEqual(cfg.search_backend, "websearch")
        self.assertIn("WebSearch", cfg.tools_filter)


# ---------------------------------------------------------------------------
# Phase05Orchestrator behavior
# ---------------------------------------------------------------------------

class TestPhase05EarlyExit(unittest.TestCase):
    def setUp(self):
        with patch.object(base_mod.BaseOrchestrator, "__init__", return_value=None):
            self.orchestrator = Phase05Orchestrator("05")
            self.orchestrator.config = get_phase_config("05").model_copy()

    def test_only_confirmed_findings_are_critiqued(self):
        items = [
            {"property_id": "P1", "review": {"review_verdict": "CONFIRMED_VULNERABILITY"}},
            {"property_id": "P2", "review": {"review_verdict": "CONFIRMED_POTENTIAL"}},
            {"property_id": "P3", "review": {"review_verdict": "DISPUTED_FP"}},
            {"property_id": "P4", "review": {"review_verdict": "PASS_THROUGH"}},
            {"property_id": "P5", "review": {"review_verdict": "NEEDS_MANUAL_REVIEW"}},
        ]
        early_exit, to_process = self.orchestrator.apply_early_exit(items)

        self.assertEqual(sorted(i["property_id"] for i in to_process), ["P1", "P2"])
        self.assertEqual(sorted(r["property_id"] for r in early_exit), ["P3", "P4", "P5"])

    def test_early_exit_records_are_schema_valid(self):
        items = [{"property_id": "P3", "review": {"review_verdict": "DISPUTED_FP"}}]
        early_exit, _ = self.orchestrator.apply_early_exit(items)
        record = early_exit[0]
        item = CritiquedItem.model_validate(record)
        self.assertEqual(item.critique_verdict, "PASS_THROUGH")
        self.assertEqual(item.prior_verdict, "DISPUTED_FP")
        self.assertEqual(item.search_backend, "none")
        self.assertEqual(item.evidence_provenance, EvidenceProvenance.INTERNAL_ONLY)
        self.assertIn("Auto-passed", item.rationale)

    def test_missing_review_early_exits(self):
        items = [{"property_id": "P9"}]
        early_exit, to_process = self.orchestrator.apply_early_exit(items)
        self.assertEqual(to_process, [])
        self.assertEqual(len(early_exit), 1)


class TestPhase05LoadAndEnrich(unittest.TestCase):
    def setUp(self):
        with patch.object(base_mod.BaseOrchestrator, "__init__", return_value=None):
            self.orchestrator = Phase05Orchestrator("05")
            self.orchestrator.config = get_phase_config("05").model_copy()

    def _write(self, root: Path, name: str, payload: dict) -> None:
        (root / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_load_items_from_04_partials(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "TARGET_INFO.json", {"target_repo": "org/repo"})
            self._write(root, "04_PARTIAL_W0B0_1.json", {
                "reviewed_items": [
                    {"property_id": "P1", "review_verdict": "CONFIRMED_VULNERABILITY"},
                    {"property_id": "P2", "review_verdict": "DISPUTED_FP"},
                ],
                "metadata": {"phase": "04"},
            })
            # Duplicate P1 in a later file — dedup keeps one entry
            self._write(root, "04_PARTIAL_W1B0_2.json", {
                "reviewed_items": [
                    {"property_id": "P1", "review_verdict": "CONFIRMED_VULNERABILITY"},
                ],
                "metadata": {"phase": "04"},
            })
            with patch.object(base_mod, "get_output_root", return_value=root):
                items = self.orchestrator.load_items()

        ids = sorted(i["property_id"] for i in items)
        self.assertEqual(ids, ["P1", "P2"])
        by_id = {i["property_id"]: i for i in items}
        self.assertEqual(by_id["P1"]["review"]["review_verdict"], "CONFIRMED_VULNERABILITY")

    def test_load_items_requires_target_info(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(base_mod, "get_output_root", return_value=root):
                with pytest.raises(PhaseAbortError, match="TARGET_INFO.json"):
                    self.orchestrator.load_items()

    def test_enrich_attaches_audit_result_and_property_fields(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "03_PARTIAL_W0B0_1.json", {
                "audit_items": [
                    {
                        "property_id": "P1",
                        "classification": "vulnerability",
                        "summary": "Missing bounds check",
                        "attack_scenario": "Oversized payload",
                    }
                ],
                "metadata": {"phase": "03"},
            })
            self._write(root, "02c_PARTIAL_W0B0_1.json", {
                "properties_with_code": [
                    {
                        "property_id": "P1",
                        "text": "Payload length MUST be validated",
                        "assertion": "len(payload) <= MAX",
                        "severity": "High",
                    }
                ],
                "metadata": {"phase": "02c"},
            })
            items = [{"property_id": "P1", "review": {"review_verdict": "CONFIRMED_VULNERABILITY"}}]
            with patch.object(base_mod, "get_output_root", return_value=root):
                enriched = self.orchestrator.enrich_items(items)

        item = enriched[0]
        self.assertEqual(item["audit_result"]["summary"], "Missing bounds check")
        self.assertEqual(item["text"], "Payload length MUST be validated")
        self.assertEqual(item["severity"], "High")

    def test_enrich_degrades_without_upstream_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = [{"property_id": "P1", "review": {"review_verdict": "CONFIRMED_POTENTIAL"}}]
            with patch.object(base_mod, "get_output_root", return_value=root):
                enriched = self.orchestrator.enrich_items(items)

        self.assertNotIn("audit_result", enriched[0])
        self.assertEqual(enriched[0]["property_id"], "P1")


# ---------------------------------------------------------------------------
# Prompt / workflow assets exist
# ---------------------------------------------------------------------------

class TestPhase05Assets(unittest.TestCase):
    def test_worker_prompt_exists(self):
        prompt = Path(_WORKSPACE_ROOT) / "prompts" / "05_critique_worker.md"
        self.assertTrue(prompt.exists())
        content = prompt.read_text(encoding="utf-8")
        self.assertIn("critiqued_items", content)
        self.assertIn("LIKELY_FP", content)
        self.assertIn("INSUFFICIENT_CONTEXT", content)
        # Honesty contract must be spelled out in the prompt
        self.assertIn("internal-only", content)

    def test_workflow_exists(self):
        wf = Path(_WORKSPACE_ROOT) / ".github" / "workflows" / "05-critique.yml"
        self.assertTrue(wf.exists())
        content = wf.read_text(encoding="utf-8")
        self.assertIn("--phase 05", content)
        self.assertIn("search_backend", content)


if __name__ == "__main__":
    unittest.main()
