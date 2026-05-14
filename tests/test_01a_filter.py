"""Tests for ``_filter_01a_state`` and ``_select_primary_specs``.

Covers the ``--01a-scope`` / ``SPECA_01A_SCOPE`` middleware introduced as
the next-slice follow-up from issue #60. The filter sits between Phase
01a's PARTIAL consolidation and the ``01a_STATE.json`` write that Phase
01b consumes — it lets demo / single-spec runs avoid paying for 01b
extraction on every URL that the spec-discovery skill expanded into.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pytest

_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from run_phase import (
    _build_env_snapshot,
    _filter_01a_state,
    _finalize_01a_state,
    _parse_01a_scope,
    _select_primary_specs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def eip7951_state() -> dict:
    """A trimmed payload matching the EIP-7951 demo run shape."""
    return {
        "start_url": "https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7951.md",
        "found_specs": [
            {
                "url": "https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7951.md",
                "title": "EIP-7951 (source markdown)",
            },
            {
                "url": "https://eips.ethereum.org/EIPS/eip-7951",
                "title": "EIP-7951 (rendered)",
            },
            {
                "url": "https://raw.githubusercontent.com/ethereum/EIPs/master/EIPS/eip-7951.md",
                "title": "EIP-7951 raw markdown",
            },
            {
                "url": "https://github.com/ethereum/EIPs/blob/master/assets/eip-7951/test-vectors.json",
                "title": "Test vectors",
            },
            {
                "url": "https://github.com/ethereum/RIPs/blob/master/RIPS/rip-7212.md",
                "title": "RIP-7212 (predecessor)",
            },
        ],
        "metadata": {"crawler": "spec-discovery"},
    }


# ---------------------------------------------------------------------------
# scope = "all" — no-op identity
# ---------------------------------------------------------------------------

class TestScopeAll:
    def test_default_keeps_everything(self, eip7951_state: dict):
        out = _filter_01a_state(eip7951_state, "all")
        assert len(out["found_specs"]) == 5
        # Original payload is not mutated even when filter is identity.
        assert eip7951_state["found_specs"][0]["title"] == "EIP-7951 (source markdown)"

    def test_empty_scope_string_treated_as_all(self, eip7951_state: dict):
        assert len(_filter_01a_state(eip7951_state, "")["found_specs"]) == 5

    def test_none_scope_treated_as_all(self, eip7951_state: dict):
        # _finalize_01a_state passes os.environ.get default of "all", but
        # callers may pass None defensively — fall through to no-op.
        assert len(_filter_01a_state(eip7951_state, None)["found_specs"]) == 5


# ---------------------------------------------------------------------------
# scope = "primary"
# ---------------------------------------------------------------------------

class TestScopePrimary:
    def test_exact_url_match_wins(self, eip7951_state: dict):
        out = _filter_01a_state(eip7951_state, "primary")
        assert len(out["found_specs"]) == 1
        assert out["found_specs"][0]["url"] == eip7951_state["start_url"]

    def test_stem_match_when_no_exact(self, eip7951_state: dict):
        # Drop the exact-match entry; primary should still resolve via
        # the eip-7951.md filename stem appearing in the raw-markdown URL.
        eip7951_state["found_specs"] = [
            s
            for s in eip7951_state["found_specs"]
            if not s["url"].startswith(
                "https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7951.md"
            )
        ]
        out = _filter_01a_state(eip7951_state, "primary")
        assert len(out["found_specs"]) == 1
        assert "eip-7951" in out["found_specs"][0]["url"].lower()

    def test_first_entry_fallback_when_no_match(self):
        state = {
            "start_url": "https://nowhere.example/spec.md",
            "found_specs": [
                {"url": "https://x.example/a", "title": "A"},
                {"url": "https://x.example/b", "title": "B"},
            ],
        }
        out = _filter_01a_state(state, "primary")
        assert out["found_specs"] == [{"url": "https://x.example/a", "title": "A"}]

    def test_missing_start_url_falls_back_to_first(self):
        state = {"found_specs": [{"url": "https://only.example/x", "title": "X"}]}
        out = _filter_01a_state(state, "primary")
        assert out["found_specs"] == [{"url": "https://only.example/x", "title": "X"}]


# ---------------------------------------------------------------------------
# scope = "primary+1hop"
# ---------------------------------------------------------------------------

class TestScopePrimaryPlus1Hop:
    def test_primary_plus_one_other(self, eip7951_state: dict):
        out = _filter_01a_state(eip7951_state, "primary+1hop")
        assert len(out["found_specs"]) == 2
        # First is the exact-match primary.
        assert out["found_specs"][0]["url"] == eip7951_state["start_url"]
        # Second is the first *other* entry from the original list.
        assert out["found_specs"][1]["url"] != eip7951_state["start_url"]

    def test_single_found_spec_returns_singleton(self):
        state = {
            "start_url": "https://only.example/x",
            "found_specs": [{"url": "https://only.example/x", "title": "X"}],
        }
        out = _filter_01a_state(state, "primary+1hop")
        # Only one spec exists, so 1hop has nothing to add.
        assert len(out["found_specs"]) == 1


# ---------------------------------------------------------------------------
# scope = integer-as-string ("3" etc.)
# ---------------------------------------------------------------------------

class TestScopeInteger:
    def test_top_n_kept_in_order(self, eip7951_state: dict):
        out = _filter_01a_state(eip7951_state, "3")
        assert len(out["found_specs"]) == 3
        assert (
            out["found_specs"][0]["title"]
            == eip7951_state["found_specs"][0]["title"]
        )
        assert (
            out["found_specs"][2]["title"]
            == eip7951_state["found_specs"][2]["title"]
        )

    def test_n_larger_than_available_returns_all(self, eip7951_state: dict):
        out = _filter_01a_state(eip7951_state, "999")
        assert len(out["found_specs"]) == 5

    def test_zero_falls_back_to_at_least_one(self, eip7951_state: dict):
        # max(1, int("0")) == 1 — the implementation refuses to strip the
        # whole state.
        out = _filter_01a_state(eip7951_state, "0")
        assert len(out["found_specs"]) == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_found_specs_is_passthrough(self):
        state = {"start_url": "https://x.example/", "found_specs": []}
        out = _filter_01a_state(state, "primary")
        assert out["found_specs"] == []

    def test_unknown_scope_warns_and_keeps_all(self, eip7951_state: dict, capsys):
        out = _filter_01a_state(eip7951_state, "weird-mode")
        captured = capsys.readouterr()
        assert "unknown --01a-scope" in captured.err.lower()
        assert len(out["found_specs"]) == 5

    def test_filter_keeps_other_payload_fields(self, eip7951_state: dict):
        out = _filter_01a_state(eip7951_state, "primary")
        # metadata and start_url must survive intact.
        assert out["metadata"] == {"crawler": "spec-discovery"}
        assert out["start_url"] == eip7951_state["start_url"]


# ---------------------------------------------------------------------------
# _select_primary_specs direct unit tests (independent of scope handling)
# ---------------------------------------------------------------------------

class TestSelectPrimarySpecs:
    def test_empty_list_returns_empty(self):
        assert _select_primary_specs([], "https://x", include_one_hop=False) == []

    def test_no_start_url_returns_first(self):
        specs = [{"url": "https://a"}, {"url": "https://b"}]
        assert _select_primary_specs(specs, "", include_one_hop=False) == [specs[0]]

    def test_include_one_hop_picks_first_non_primary(self):
        specs = [{"url": "https://a"}, {"url": "https://b"}, {"url": "https://c"}]
        result = _select_primary_specs(specs, "https://a", include_one_hop=True)
        assert result == [specs[0], specs[1]]


# ---------------------------------------------------------------------------
# argparse type validator (_parse_01a_scope)
# ---------------------------------------------------------------------------

class TestParse01aScope:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("all", "all"),
            ("ALL", "all"),
            (" primary ", "primary"),
            ("primary+1hop", "primary+1hop"),
            ("3", "3"),
            ("100", "100"),
            ("", "all"),
        ],
    )
    def test_valid_inputs_normalised(self, raw: str, expected: str):
        assert _parse_01a_scope(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        ["weird", "primary+2hop", "0", "-3", "3.5", " 3 4 ", "primary,all"],
    )
    def test_invalid_inputs_raise(self, raw: str):
        # Negative / non-positive / float / unknown literal all fail at
        # parse time, surfacing typos immediately rather than at finalize.
        with pytest.raises(argparse.ArgumentTypeError):
            _parse_01a_scope(raw)

    def test_none_falls_back_to_all(self):
        # Defensive — argparse will pass through ``default=None`` if the
        # flag is omitted entirely, before the validator runs. But the
        # validator should still be safe to call directly.
        assert _parse_01a_scope(None) == "all"


# ---------------------------------------------------------------------------
# _build_env_snapshot includes SPECA_01A_SCOPE
# ---------------------------------------------------------------------------

class TestEnvSnapshot:
    def test_includes_speca_01a_scope_field(self, monkeypatch):
        monkeypatch.setenv("SPECA_01A_SCOPE", "primary")
        snap = _build_env_snapshot(["01a", "01b"])
        assert snap["SPECA_01A_SCOPE"] == "primary"
        assert snap["phases"] == ["01a", "01b"]

    def test_unset_env_yields_empty_string(self, monkeypatch):
        monkeypatch.delenv("SPECA_01A_SCOPE", raising=False)
        snap = _build_env_snapshot(["01a"])
        assert snap["SPECA_01A_SCOPE"] == ""


# ---------------------------------------------------------------------------
# _finalize_01a_state end-to-end (wires env var → on-disk STATE write)
# ---------------------------------------------------------------------------

class TestFinalize01aStateIntegration:
    """End-to-end: drop a PARTIAL on disk, set env, run finalize, assert STATE.

    The function reads ``get_output_root()`` for both the PARTIAL glob and
    the STATE write target. ``SPECA_OUTPUT_DIR`` is the documented override.
    """

    @pytest.fixture()
    def partial(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path))
        # Match the actual on-disk shape: {"items": [<phase01a_state>]}.
        partial_path = tmp_path / "01a_PARTIAL_W0B0_1700000000.json"
        payload = {
            "items": [
                {
                    "start_url": "https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7951.md",
                    "found_specs": [
                        {
                            "url": "https://github.com/ethereum/EIPs/blob/master/EIPS/eip-7951.md",
                            "title": "primary",
                        },
                        {"url": "https://eips.ethereum.org/EIPS/eip-7951", "title": "rendered"},
                        {"url": "https://example.com/sibling.md", "title": "sibling"},
                    ],
                    "metadata": {},
                }
            ]
        }
        partial_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        return tmp_path

    def test_scope_primary_via_env_writes_single_spec_state(
        self, partial: Path, monkeypatch, capsys
    ):
        monkeypatch.setenv("SPECA_01A_SCOPE", "primary")
        _finalize_01a_state()
        state = json.loads((partial / "01a_STATE.json").read_text(encoding="utf-8"))
        assert len(state["found_specs"]) == 1
        assert state["found_specs"][0]["title"] == "primary"
        out = capsys.readouterr().out
        # The "1/3 specs, scope=primary" annotation is the operator's
        # signal that filtering happened.
        assert "scope=primary" in out
        assert "1/3" in out

    def test_no_scope_keeps_all_specs(self, partial: Path, monkeypatch, capsys):
        monkeypatch.delenv("SPECA_01A_SCOPE", raising=False)
        _finalize_01a_state()
        state = json.loads((partial / "01a_STATE.json").read_text(encoding="utf-8"))
        assert len(state["found_specs"]) == 3
        # No scope annotation when filter was a no-op.
        assert "scope=" not in capsys.readouterr().out

    def test_no_partial_is_silent_no_op(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path))
        # No PARTIAL on disk — should return cleanly without writing STATE.
        _finalize_01a_state()
        assert not (tmp_path / "01a_STATE.json").exists()
