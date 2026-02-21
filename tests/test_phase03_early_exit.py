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


if __name__ == "__main__":
    unittest.main()
