import sys
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add workspace root to sys.path using absolute path calculation (BUG-SCH13)
_WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

# Mock dependencies before importing scripts, using patch.dict for proper cleanup (BUG-SCH12)
_MOCK_MODULES = {"tqdm": MagicMock(), "aiofiles": MagicMock(), "anthropic": MagicMock(), "tenacity": MagicMock()}
_patcher = patch.dict(sys.modules, _MOCK_MODULES)
_patcher.start()

from scripts.orchestrator.base import Phase03Orchestrator
from scripts.orchestrator.config import get_phase_config

_patcher.stop()


class TestPhase03EarlyExit(unittest.TestCase):
    def setUp(self):
        # Patch BaseOrchestrator.__init__ to avoid side effects during instantiation
        with patch("scripts.orchestrator.base.BaseOrchestrator.__init__", return_value=None):
            self.orchestrator = Phase03Orchestrator()
            # Manually inject config since __init__ was skipped
            self.orchestrator.config = get_phase_config("03")

    def test_out_of_scope_only_early_exit(self):
        items = [
            # Resolved property -> should be kept
            {
                "property_id": "P1",
                "text": "Some property",
                "code_scope": {"resolution_status": "resolved"},
            },
            # Explicitly out of scope -> should early exit
            {
                "property_id": "P2",
                "text": "Out of scope property",
                "code_scope": {"resolution_status": "out_of_scope"},
            },
            # No code_scope at all -> should be processed
            {
                "property_id": "P3",
                "text": "Property without code scope",
            },
        ]

        skipped, kept = self.orchestrator.apply_early_exit(items)

        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["property_id"], "P2")
        self.assertIn("out-of-scope", skipped[0]["summary"])

        kept_ids = sorted([i["property_id"] for i in kept])
        self.assertEqual(kept_ids, ["P1", "P3"])

    def test_skipped_early_exit(self):
        items = [
            {
                "property_id": "P1",
                "text": "Resolved property",
                "code_scope": {"resolution_status": "resolved"},
            },
            {
                "property_id": "P2",
                "text": "Skipped property",
                "code_scope": {"resolution_status": "skipped"},
            },
            {
                "property_id": "P3",
                "text": "Out of scope property",
                "code_scope": {"resolution_status": "out_of_scope"},
            },
        ]

        early_exit, to_process = self.orchestrator.apply_early_exit(items)

        self.assertEqual(len(early_exit), 2)
        exit_ids = {r["property_id"]: r for r in early_exit}
        self.assertIn("P2", exit_ids)
        self.assertIn("P3", exit_ids)
        self.assertEqual(exit_ids["P2"]["classification"], "skipped")
        self.assertEqual(exit_ids["P3"]["classification"], "out-of-scope")

        self.assertEqual(len(to_process), 1)
        self.assertEqual(to_process[0]["property_id"], "P1")


if __name__ == "__main__":
    unittest.main()
