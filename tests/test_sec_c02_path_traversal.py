"""Tests for SEC-C02: Path traversal guard on LLM-supplied file paths.

Verifies that _is_safe_output_path() correctly allows paths inside the
outputs/ directory and rejects traversal or absolute paths that escape it.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

# Add workspace root to sys.path
sys.path.append(os.getcwd())

# Mock heavy dependencies before importing scripts
sys.modules["tqdm"] = MagicMock()
sys.modules["aiofiles"] = MagicMock()
sys.modules["anthropic"] = MagicMock()
sys.modules["tenacity"] = MagicMock()

from scripts.orchestrator.base import _is_safe_output_path


class TestIsSafeOutputPath(unittest.TestCase):
    """Verify the path traversal guard for LLM-supplied file paths."""

    def test_normal_output_path_accepted(self):
        """A normal outputs/ relative path should pass validation."""
        self.assertTrue(_is_safe_output_path("outputs/01b_PARTIAL_W1B1.json"))

    def test_nested_output_path_accepted(self):
        """A nested path inside outputs/ should pass validation."""
        self.assertTrue(_is_safe_output_path("outputs/logs/01b_W0B1_123.jsonl"))

    def test_traversal_path_rejected(self):
        """A path traversal like ../../../../etc/passwd must be rejected."""
        self.assertFalse(_is_safe_output_path("../../../../etc/passwd"))

    def test_absolute_path_rejected(self):
        """An absolute path outside outputs/ must be rejected."""
        self.assertFalse(_is_safe_output_path("/etc/passwd"))

    def test_traversal_from_outputs_rejected(self):
        """A path that starts in outputs/ but escapes via .. must be rejected."""
        self.assertFalse(_is_safe_output_path("outputs/../../etc/passwd"))

    def test_empty_path_rejected(self):
        """An empty string should be rejected (resolves to cwd, not outputs/)."""
        self.assertFalse(_is_safe_output_path(""))


if __name__ == "__main__":
    unittest.main()
