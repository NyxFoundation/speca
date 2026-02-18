import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add workspace root to sys.path
sys.path.append(os.getcwd())

# Mock dependencies before importing scripts
sys.modules["tqdm"] = MagicMock()
sys.modules["aiofiles"] = MagicMock()
sys.modules["anthropic"] = MagicMock()
sys.modules["tenacity"] = MagicMock()

from scripts.orchestrator.base import Phase03Orchestrator
from scripts.orchestrator.config import get_phase_config


class TestPhase03EarlyExit(unittest.TestCase):
    def setUp(self):
        # Patch BaseOrchestrator.__init__ to avoid side effects during instantiation
        with patch("scripts.orchestrator.base.BaseOrchestrator.__init__", return_value=None):
            self.orchestrator = Phase03Orchestrator()
            # Manually inject config since __init__ was skipped
            self.orchestrator.config = get_phase_config("03")

    def test_out_of_scope_only_early_exit(self):
        items = [
            # Missing property_id, but should not early exit
            {
                "check_id": "C1",
                "checklist_item": {
                    "property_id": None,
                    "code_scope": {"resolution_status": "resolved"},
                },
            },
            # Explicitly out of scope -> should early exit
            {
                "check_id": "C2",
                "checklist_item": {
                    "property_id": "P2",
                    "code_scope": {"resolution_status": "out_of_scope"},
                },
            },
            # No code_scope at all -> should be processed
            {
                "check_id": "C3",
                "checklist_item": {"property_id": "P3"},
            },
        ]

        skipped, kept = self.orchestrator.apply_early_exit(items)

        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["check_id"], "C2")
        self.assertIn("out-of-scope", skipped[0]["summary"])

        kept_ids = sorted([i["check_id"] for i in kept])
        self.assertEqual(kept_ids, ["C1", "C3"])


if __name__ == "__main__":
    unittest.main()
