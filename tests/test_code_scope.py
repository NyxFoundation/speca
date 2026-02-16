"""
Tests for CodeScope schema and code pre-resolution functionality.
"""

import pytest
from scripts.orchestrator.schemas import CodeScope, CodeLocation, LineRange, ChecklistItem


class TestCodeScope:
    """Test CodeScope model."""

    def test_code_scope_empty(self):
        """Test empty CodeScope initialization."""
        scope = CodeScope()
        assert scope.locations == []
        assert scope.resolution_status == ""
        assert scope.resolution_error == ""

    def test_code_scope_resolved(self):
        """Test resolved CodeScope with multiple locations."""
        scope = CodeScope(
            locations=[
                CodeLocation(
                    file="src/beacon_chain.go",
                    symbol="ProcessBlock",
                    line_range=LineRange(start=100, end=150),
                    role="primary"
                ),
                CodeLocation(
                    file="src/caller.go",
                    symbol="ValidateChain",
                    line_range=LineRange(start=50, end=70),
                    role="caller"
                )
            ],
            resolution_status="resolved",
        )
        assert len(scope.locations) == 2
        assert scope.locations[0].file == "src/beacon_chain.go"
        assert scope.locations[0].symbol == "ProcessBlock"
        assert scope.locations[0].line_range.start == 100
        assert scope.locations[0].role == "primary"
        assert scope.resolution_status == "resolved"
        assert scope.resolution_error == ""

    def test_code_scope_not_found(self):
        """Test CodeScope with resolution error."""
        scope = CodeScope(
            resolution_status="not_found",
            resolution_error="Symbol not found in codebase",
        )
        assert scope.locations == []
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
                locations=[
                    CodeLocation(
                        file="src/beacon_chain.go",
                        symbol="ProcessBlock",
                        line_range=LineRange(start=100, end=150),
                        role="primary"
                    )
                ],
                resolution_status="resolved",
            ),
            code_excerpt="func ProcessBlock(block *Block) error {\n    // ...\n}",
        )
        assert item.check_id == "CHK-001"
        assert len(item.code_scope.locations) == 1
        assert item.code_scope.locations[0].file == "src/beacon_chain.go"
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
        assert item.code_scope.locations == []
        assert item.code_excerpt == ""

    def test_checklist_item_serialization(self):
        """Test ChecklistItem serialization with CodeScope."""
        item = ChecklistItem(
            check_id="CHK-003",
            code_scope=CodeScope(
                locations=[
                    CodeLocation(
                        file="test.go",
                        symbol="TestFunc",
                        line_range=LineRange(start=1, end=10),
                        role="primary"
                    )
                ],
                resolution_status="resolved",
            ),
        )
        data = item.model_dump()
        assert data["code_scope"]["locations"][0]["file"] == "test.go"
        assert data["code_scope"]["resolution_status"] == "resolved"

    def test_checklist_item_from_dict(self):
        """Test ChecklistItem deserialization with CodeScope."""
        data = {
            "check_id": "CHK-004",
            "code_scope": {
                "locations": [
                    {
                        "file": "src/main.go",
                        "symbol": "main",
                        "line_range": {"start": 10, "end": 20},
                        "role": "primary"
                    }
                ],
                "resolution_status": "resolved",
            },
        }
        item = ChecklistItem(**data)
        assert item.code_scope.locations[0].file == "src/main.go"
        assert isinstance(item.code_scope, CodeScope)
