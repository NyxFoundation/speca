"""Tests for the orchestrator runtime registry.

The registry's job is to enumerate runtime backends and probe each for
availability. We test the contract — not the actual subprocess calls —
because the probe shells out to real CLIs that may or may not be
installed on a given dev box.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from orchestrator import runtime_registry as rr


def test_all_runtime_ids_includes_known_set() -> None:
    """Every backend we ship a stub or impl for must be in the registry."""

    ids = rr.all_runtime_ids()
    assert "claude" in ids
    assert "api" in ids
    assert "codex" in ids
    assert "gemini" in ids
    assert "ollama" in ids
    assert "copilot" in ids


def test_get_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown runtime id"):
        rr.get("not-a-real-runtime")


def test_get_returns_descriptor_with_summary_and_probe() -> None:
    descr = rr.get("claude")
    assert descr.runtime_id == "claude"
    assert "claude" in descr.summary.lower()
    assert callable(descr.probe)


def test_implemented_split() -> None:
    """Today only claude + api are wired in the orchestrator."""

    assert rr.get("claude").implemented is True
    assert rr.get("api").implemented is True
    for stubbed in ("codex", "gemini", "ollama", "copilot"):
        assert rr.get(stubbed).implemented is False, (
            f"{stubbed} should still be stubbed at the orchestrator boundary; "
            "the Web chat side has it but the CLI runner is not yet wired."
        )


def test_resolve_active_defaults_to_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORCHESTRATOR_RUNNER", raising=False)
    assert rr.resolve_active() == "claude"


def test_resolve_active_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_RUNNER", "api")
    assert rr.resolve_active() == "api"


def test_resolve_active_falls_back_and_warns_on_typo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORCHESTRATOR_RUNNER", "bogus-runtime")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        active = rr.resolve_active()
    assert active == "claude"
    assert any("not a known runtime" in str(w.message) for w in caught)


def test_list_runtimes_returns_json_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub every probe to a synthetic result so the test does not depend
    # on which CLIs happen to be installed on the runner.
    fake_avail = rr.RuntimeAvailability(
        runtime_id="x",
        available=True,
        implemented=True,
        notes=("synthetic",),
    )
    with mock.patch.object(rr, "REGISTRY", {
        "claude": rr.RuntimeDescriptor(
            runtime_id="claude",
            summary="synthetic claude",
            probe=lambda: fake_avail,
            implemented=True,
        ),
    }):
        rows = rr.list_runtimes()
    assert len(rows) == 1
    row = rows[0]
    assert row["runtime_id"] == "claude"
    assert row["summary"] == "synthetic claude"
    assert row["implemented"] is True
    assert row["available"] is True
    assert row["notes"] == ["synthetic"]


def test_probe_claude_returns_availability_struct() -> None:
    # We don't care whether the CLI is installed on this dev box; we
    # only assert the probe returns the right shape and never raises.
    result = rr.probe("claude")
    assert isinstance(result, rr.RuntimeAvailability)
    assert result.runtime_id == "claude"
    assert isinstance(result.notes, tuple)
    assert isinstance(result.available, bool)
    assert isinstance(result.implemented, bool)


def test_probe_stubbed_runtimes_flag_implemented_false() -> None:
    """Every stubbed runtime must self-report implemented=False."""

    for stubbed in ("codex", "gemini", "ollama", "copilot"):
        result = rr.probe(stubbed)
        assert result.implemented is False, stubbed
        # Notes should call out the "not yet implemented" caveat so a
        # user reading --list-runtimes doesn't expect it to work.
        joined = " ".join(result.notes).lower()
        assert "not yet implemented" in joined, stubbed
