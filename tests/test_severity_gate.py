"""Tests for the Severity enum ordering and the Phase02c severity gate."""

import sys
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add workspace root to sys.path using absolute path calculation (BUG-SCH13)
_WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

# Mock heavy dependencies before importing scripts, using patch.dict for proper cleanup (BUG-SCH12)
_MOCK_MODULES = {"tqdm": MagicMock(), "aiofiles": MagicMock(), "anthropic": MagicMock(), "tenacity": MagicMock()}
_patcher = patch.dict(sys.modules, _MOCK_MODULES)
_patcher.start()

from scripts.orchestrator.schemas import Severity
from scripts.orchestrator.base import Phase02cOrchestrator
from scripts.orchestrator.config import get_phase_config

_patcher.stop()


# ---------------------------------------------------------------------------
# Severity enum: ordering and parsing
# ---------------------------------------------------------------------------

class TestSeverityOrdering(unittest.TestCase):
    """Verify that Severity comparisons follow the expected security ordering."""

    def test_rank_values(self):
        self.assertEqual(Severity.CRITICAL.rank, 0)
        self.assertEqual(Severity.HIGH.rank, 1)
        self.assertEqual(Severity.MEDIUM.rank, 2)
        self.assertEqual(Severity.LOW.rank, 3)
        self.assertEqual(Severity.INFORMATIONAL.rank, 4)

    def test_critical_is_highest(self):
        self.assertGreater(Severity.CRITICAL, Severity.HIGH)
        self.assertGreater(Severity.CRITICAL, Severity.INFORMATIONAL)

    def test_informational_is_lowest(self):
        self.assertLess(Severity.INFORMATIONAL, Severity.LOW)
        self.assertLess(Severity.INFORMATIONAL, Severity.CRITICAL)

    def test_ordering_chain(self):
        self.assertGreater(Severity.CRITICAL, Severity.HIGH)
        self.assertGreater(Severity.HIGH, Severity.MEDIUM)
        self.assertGreater(Severity.MEDIUM, Severity.LOW)
        self.assertGreater(Severity.LOW, Severity.INFORMATIONAL)

    def test_equal(self):
        self.assertGreaterEqual(Severity.HIGH, Severity.HIGH)
        self.assertLessEqual(Severity.HIGH, Severity.HIGH)

    def test_ge_and_le(self):
        self.assertTrue(Severity.CRITICAL >= Severity.LOW)
        self.assertTrue(Severity.LOW <= Severity.CRITICAL)
        self.assertFalse(Severity.LOW >= Severity.CRITICAL)


class TestSeverityFromStr(unittest.TestCase):
    """Verify Severity.from_str() parsing."""

    def test_exact_values(self):
        self.assertEqual(Severity.from_str("Critical"), Severity.CRITICAL)
        self.assertEqual(Severity.from_str("High"), Severity.HIGH)
        self.assertEqual(Severity.from_str("Medium"), Severity.MEDIUM)
        self.assertEqual(Severity.from_str("Low"), Severity.LOW)
        self.assertEqual(Severity.from_str("Informational"), Severity.INFORMATIONAL)

    def test_case_insensitive(self):
        self.assertEqual(Severity.from_str("critical"), Severity.CRITICAL)
        self.assertEqual(Severity.from_str("HIGH"), Severity.HIGH)
        self.assertEqual(Severity.from_str("low"), Severity.LOW)

    def test_whitespace_trimmed(self):
        self.assertEqual(Severity.from_str("  Medium  "), Severity.MEDIUM)

    def test_empty_returns_none(self):
        self.assertIsNone(Severity.from_str(""))

    def test_invalid_returns_none(self):
        self.assertIsNone(Severity.from_str("unknown"))
        self.assertIsNone(Severity.from_str("SEVERE"))


# ---------------------------------------------------------------------------
# Phase02cOrchestrator severity gate
# ---------------------------------------------------------------------------

def _make_property_item(prop_id: str, severity: str, scope: str = "in-scope") -> dict:
    """Helper: build a Phase02c input item (flat property)."""
    return {
        "property_id": prop_id,
        "severity": severity,
        "text": f"Test property {prop_id}",
        "reachability": {"bug_bounty_scope": scope},
    }


class TestPhase02cSeverityGate(unittest.TestCase):
    """Verify that Phase02cOrchestrator.apply_early_exit filters by severity."""

    def setUp(self):
        with patch("scripts.orchestrator.base.BaseOrchestrator.__init__", return_value=None):
            self.orchestrator = Phase02cOrchestrator.__new__(Phase02cOrchestrator)
            self.orchestrator.config = get_phase_config("02c").model_copy()

    def test_default_config_has_min_severity_low(self):
        """Phase 02c config should default to min_severity=Low."""
        self.assertEqual(self.orchestrator.config.min_severity, "Low")

    def test_informational_dropped(self):
        """Informational properties should be skipped with min_severity=Low."""
        items = [
            _make_property_item("PROP-001", "Critical"),
            _make_property_item("PROP-002", "High"),
            _make_property_item("PROP-003", "Medium"),
            _make_property_item("PROP-004", "Low"),
            _make_property_item("PROP-005", "Informational"),
        ]

        skipped, kept = self.orchestrator.apply_early_exit(items)

        kept_ids = [i["property_id"] for i in kept]
        self.assertEqual(kept_ids, ["PROP-001", "PROP-002", "PROP-003", "PROP-004"])

        skipped_ids = [s["property_id"] for s in skipped]
        self.assertIn("PROP-005", skipped_ids)

    def test_min_severity_medium(self):
        """With min_severity=Medium, Low and Informational should be skipped."""
        self.orchestrator.config.min_severity = "Medium"

        items = [
            _make_property_item("PROP-001", "Critical"),
            _make_property_item("PROP-002", "High"),
            _make_property_item("PROP-003", "Medium"),
            _make_property_item("PROP-004", "Low"),
            _make_property_item("PROP-005", "Informational"),
        ]

        skipped, kept = self.orchestrator.apply_early_exit(items)

        kept_ids = [i["property_id"] for i in kept]
        self.assertEqual(kept_ids, ["PROP-001", "PROP-002", "PROP-003"])
        self.assertEqual(len(skipped), 2)

    def test_min_severity_none_passes_all(self):
        """With min_severity=None, all severities should pass."""
        self.orchestrator.config.min_severity = None

        items = [
            _make_property_item("PROP-001", "Critical"),
            _make_property_item("PROP-005", "Informational"),
        ]

        skipped, kept = self.orchestrator.apply_early_exit(items)

        self.assertEqual(len(kept), 2)
        self.assertEqual(len(skipped), 0)

    def test_empty_severity_dropped_when_gate_active(self):
        """Properties with empty/missing severity should be dropped when gate is active."""
        items = [
            _make_property_item("PROP-001", ""),
            _make_property_item("PROP-002", "High"),
        ]

        skipped, kept = self.orchestrator.apply_early_exit(items)

        kept_ids = [i["property_id"] for i in kept]
        self.assertEqual(kept_ids, ["PROP-002"])

        # Check the skip reason mentions severity
        self.assertTrue(any("min_severity" in s.get("skip_reason", "") for s in skipped))

    def test_out_of_scope_still_filtered(self):
        """Out-of-scope filtering should still work alongside severity gate."""
        items = [
            _make_property_item("PROP-001", "Critical", scope="out-of-scope"),
            _make_property_item("PROP-002", "High"),
        ]

        skipped, kept = self.orchestrator.apply_early_exit(items)

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["property_id"], "PROP-002")

        oos_skips = [s for s in skipped if s.get("skip_reason") == "out-of-scope"]
        self.assertEqual(len(oos_skips), 1)

    def test_skip_result_format(self):
        """Skipped items should have the standard skip result format."""
        items = [_make_property_item("PROP-001", "Informational")]

        skipped, kept = self.orchestrator.apply_early_exit(items)

        self.assertEqual(len(skipped), 1)
        result = skipped[0]
        self.assertEqual(result["property_id"], "PROP-001")
        self.assertTrue(result["skipped"])
        self.assertIn("min_severity", result["skip_reason"])


if __name__ == "__main__":
    unittest.main()
