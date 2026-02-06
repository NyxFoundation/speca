import sys
import os
import json
import unittest
from unittest.mock import MagicMock, patch

# Add workspace root to sys.path
sys.path.append(os.getcwd())

# Mock dependencies before importing scripts
sys.modules['tqdm'] = MagicMock()
sys.modules['aiofiles'] = MagicMock()
sys.modules['anthropic'] = MagicMock()
sys.modules['tenacity'] = MagicMock()

from scripts.orchestrator.base import Phase02Orchestrator
from scripts.orchestrator.config import get_phase_config

class TestPhase02Fixes(unittest.TestCase):
    def setUp(self):
        # Patch BaseOrchestrator.__init__ to avoid side effects during instantiation
        with patch('scripts.orchestrator.base.BaseOrchestrator.__init__', return_value=None):
            self.orchestrator = Phase02Orchestrator("02")
            # Manually inject config since __init__ was skipped
            self.orchestrator.config = get_phase_config("02")

    def test_batch_size(self):
        print("\nTesting Batch Size...")
        config = get_phase_config("02")
        print(f"Phase 02 Max Batch Size: {config.max_batch_size}")
        self.assertEqual(config.max_batch_size, 25, "Batch size should be 25")

    @patch('glob.glob')
    @patch('builtins.open')
    @patch('json.load')
    def test_deduplication(self, mock_json_load, mock_open, mock_glob):
        print("\nTesting Deduplication...")
        # Setup mock data
        mock_glob.return_value = ["outputs/01e_PARTIAL_1.json", "outputs/01e_PARTIAL_2.json"]
        
        # File 1 has prop A and B
        data1 = {
            "properties": [
                {"id": "PROP-A", "val": 1},
                {"id": "PROP-B", "val": 1}
            ]
        }
        # File 2 has prop B (duplicate) and C
        data2 = {
            "properties": [
                {"id": "PROP-B", "val": 2}, # Duplicate
                {"id": "PROP-C", "val": 1}
            ]
        }
        
        mock_json_load.side_effect = [data1, data2]
        
        # Run load_items
        items = self.orchestrator.load_items()
        
        # Verify results
        item_ids = [item['property_id'] for item in items]
        print(f"Loaded Item IDs: {sorted(item_ids)}")
        
        self.assertEqual(len(items), 3, "Should have 3 unique items")
        self.assertIn("PROP-A", item_ids)
        self.assertIn("PROP-B", item_ids)
        self.assertIn("PROP-C", item_ids)
        
        # Verify we kept the first occurrence of B (val 1 from data1)
        prop_b = next(item for item in items if item['property_id'] == "PROP-B")
        self.assertEqual(prop_b['property']['val'], 1, "Should keep first occurrence")

    def test_early_exit(self):
        print("\nTesting Early Exit...")
        items = [
            # Valid item
            {"property_id": "P1", "property": {"id": "P1", "reachability": {"bug_bounty_scope": "in-scope"}}},
            # Missing ID
            {"property_id": None, "property": {"val": "no-id"}},
            # Out of scope
            {"property_id": "P2", "property": {"id": "P2", "reachability": {"bug_bounty_scope": "out-of-scope"}}},
        ]
        
        skip, keep = self.orchestrator.apply_early_exit(items)
        
        print(f"Skipped: {len(skip)}, Kept: {len(keep)}")
        
        self.assertEqual(len(keep), 1, "Should keep 1 item")
        self.assertEqual(keep[0]['property_id'], "P1")
        
        self.assertEqual(len(skip), 2, "Should skip 2 items")
        reasons = sorted([s['skip_reason'] for s in skip])
        self.assertIn("missing property id", reasons)
        self.assertIn("out-of-scope", reasons)

if __name__ == '__main__':
    unittest.main()
