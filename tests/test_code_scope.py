"""
Tests for CodeScope schema and code pre-resolution functionality.
"""

import pytest
from scripts.orchestrator.schemas import CodeScope, ChecklistItem


class TestCodeScope:
    """Test CodeScope model."""

    def test_code_scope_empty(self):
        """Test empty CodeScope initialization."""
        scope = CodeScope()
        assert scope.file == ""
        assert scope.function == ""
        assert scope.line_range == ""
        assert scope.resolution_status == ""
        assert scope.resolution_error == ""

    def test_code_scope_resolved(self):
        """Test resolved CodeScope."""
        scope = CodeScope(
            file="src/beacon_chain.go",
            function="ProcessBlock",
            line_range="100-150",
            resolution_status="resolved",
        )
        assert scope.file == "src/beacon_chain.go"
        assert scope.function == "ProcessBlock"
        assert scope.line_range == "100-150"
        assert scope.resolution_status == "resolved"
        assert scope.resolution_error == ""

    def test_code_scope_not_found(self):
        """Test CodeScope with resolution error."""
        scope = CodeScope(
            resolution_status="not_found",
            resolution_error="Symbol not found in codebase",
        )
        assert scope.file == ""
        assert scope.resolution_status == "not_found"
        assert scope.resolution_error == "Symbol not found in codebase"


class TestChecklistItemWithCodeScope:
    """Test ChecklistItem with typed CodeScope."""

    def test_checklist_item_with_code_scope(self):
        """Test ChecklistItem with resolved code_scope."""
        item = ChecklistItem(
            check_id="CHK-001",
            property_id="PROP-001",
            graph_element_under_test="beacon_chain.go:ProcessBlock",
            code_scope=CodeScope(
                file="src/beacon_chain.go",
                function="ProcessBlock",
                line_range="100-150",
                resolution_status="resolved",
            ),
            code_excerpt="func ProcessBlock(block *Block) error {\n    // ...\n}",
        )
        assert item.check_id == "CHK-001"
        assert item.code_scope.file == "src/beacon_chain.go"
        assert item.code_scope.resolution_status == "resolved"
        assert item.code_excerpt != ""

    def test_checklist_item_pending_resolution(self):
        """Test ChecklistItem with pending code resolution."""
        item = ChecklistItem(
            check_id="CHK-002",
            graph_element_under_test="unknown_file.go:UnknownFunc",
            code_scope=CodeScope(resolution_status="pending"),
        )
        assert item.code_scope.resolution_status == "pending"
        assert item.code_scope.file == ""
        assert item.code_excerpt == ""

    def test_checklist_item_serialization(self):
        """Test ChecklistItem serialization with CodeScope."""
        item = ChecklistItem(
            check_id="CHK-003",
            code_scope=CodeScope(
                file="test.go",
                function="TestFunc",
                line_range="1-10",
                resolution_status="resolved",
            ),
        )
        data = item.model_dump()
        assert data["code_scope"]["file"] == "test.go"
        assert data["code_scope"]["resolution_status"] == "resolved"

    def test_checklist_item_from_dict(self):
        """Test ChecklistItem deserialization with CodeScope."""
        data = {
            "check_id": "CHK-004",
            "code_scope": {
                "file": "src/main.go",
                "function": "main",
                "line_range": "10-20",
                "resolution_status": "resolved",
            },
        }
        item = ChecklistItem(**data)
        assert item.code_scope.file == "src/main.go"
        assert isinstance(item.code_scope, CodeScope)
