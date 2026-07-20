"""Client/target dimension for the findings browser (issue #54).

Multi-client audits lay outputs out per target directory
(``outputs/<client>/03_PARTIAL_*.json``). These tests pin the contract
added for the "filter by client" half of #54:

1. Each finding is stamped with the ``target`` derived from its parent dir.
2. ``meta.targets`` lists every distinct client (from the *unfiltered* set).
3. ``?target=<client>`` narrows the list to that client only.
4. Top-level ``outputs/03_PARTIAL_*.json`` (single-target layout) yields
   ``target: null`` and an empty ``meta.targets`` — the frontend then hides
   the client filter, so existing single-target runs are unaffected.

We redirect ``SPECA_OUTPUTS_DIR`` at the loader module so the tests never
touch the real ``outputs/`` tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.server.services import finding_loader


def _write_partial(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _audit_item(property_id: str, severity: str = "High") -> dict:
    return {
        "metadata": {"phase": "03", "timestamp": 1700000000},
        "audit_items": [
            {
                "property_id": property_id,
                "severity": severity,
                "code_path": f"src/{property_id}.rs::L1-L2",
            }
        ],
    }


def _seed_multi_client(outputs: Path) -> None:
    """Two clients, one finding each, laid out as outputs/<client>/..."""

    _write_partial(
        outputs / "lighthouse_fusaka" / "03_PARTIAL_W0B0_1700000001.json",
        _audit_item("P-LH-001", "Critical"),
    )
    _write_partial(
        outputs / "reth_fusaka" / "03_PARTIAL_W0B0_1700000002.json",
        _audit_item("P-RETH-001", "Medium"),
    )


def test_finding_is_stamped_with_client_target(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    _seed_multi_client(outputs)
    monkeypatch.setattr(finding_loader, "SPECA_OUTPUTS_DIR", outputs)

    body = client.get("/api/runs/any/findings").json()
    by_id = {f["property_id"]: f for f in body["data"]}
    assert by_id["P-LH-001"]["target"] == "lighthouse_fusaka"
    assert by_id["P-RETH-001"]["target"] == "reth_fusaka"


def test_meta_targets_lists_every_client_sorted(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    _seed_multi_client(outputs)
    monkeypatch.setattr(finding_loader, "SPECA_OUTPUTS_DIR", outputs)

    body = client.get("/api/runs/any/findings").json()
    assert body["meta"]["targets"] == ["lighthouse_fusaka", "reth_fusaka"]


def test_target_filter_narrows_to_one_client(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    _seed_multi_client(outputs)
    monkeypatch.setattr(finding_loader, "SPECA_OUTPUTS_DIR", outputs)

    body = client.get("/api/runs/any/findings?target=reth_fusaka").json()
    ids = [f["property_id"] for f in body["data"]]
    assert ids == ["P-RETH-001"]
    assert body["meta"]["count"] == 1
    # meta.targets stays the *full* set even when the list is filtered.
    assert body["meta"]["targets"] == ["lighthouse_fusaka", "reth_fusaka"]


def test_top_level_outputs_have_null_target(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    # Single-target layout: PARTIAL sits directly under outputs/.
    _write_partial(
        outputs / "03_PARTIAL_W0B0_1700000003.json",
        _audit_item("P-SINGLE-001"),
    )
    monkeypatch.setattr(finding_loader, "SPECA_OUTPUTS_DIR", outputs)

    body = client.get("/api/runs/any/findings").json()
    assert body["data"][0]["target"] is None
    assert body["meta"]["targets"] == []
