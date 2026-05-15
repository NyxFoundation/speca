"""Tests for ``CopilotRunner`` — the agentic @github/copilot driver.

Focus is on the pure-function pieces (cmd construction, JSONL event
parsing, result extraction) because the subprocess loop is exercised
end-to-end by the CLI smoke tests (``--list-runtimes`` etc.) and we do
not want to depend on the real CLI being installed under unit-test CI.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from orchestrator.config import get_phase_config
from orchestrator.copilot_runner import CopilotRunner, _resolve_copilot_bin
from orchestrator.runner import CircuitBreaker


# ---------------------------------------------------------------------------
# Constructor / interface contract
# ---------------------------------------------------------------------------


class TestRunnerInterface:
    """``CopilotRunner`` is a drop-in peer of ``ClaudeRunner`` / ``APIRunner``."""

    def test_constructor_signature(self) -> None:
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        cb = CircuitBreaker(config)
        runner = CopilotRunner(config, sem, circuit_breaker=cb)
        assert runner.config is config
        assert runner.semaphore is sem
        assert runner.circuit_breaker is cb

    def test_has_run_batch(self) -> None:
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        runner = CopilotRunner(config, sem)
        assert hasattr(runner, "run_batch")
        assert asyncio.iscoroutinefunction(runner.run_batch)

    def test_default_model_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No COPILOT_MODEL => model is None (CLI picks its own default)."""

        monkeypatch.delenv("COPILOT_MODEL", raising=False)
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        runner = CopilotRunner(config, sem)
        assert runner.model is None

    def test_model_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COPILOT_MODEL", "claude-sonnet-4-6")
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        runner = CopilotRunner(config, sem)
        assert runner.model == "claude-sonnet-4-6"

    def test_model_kwarg_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COPILOT_MODEL", "from-env")
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        runner = CopilotRunner(config, sem, model="from-kwarg")
        assert runner.model == "from-kwarg"


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


class TestBuildCmd:
    def _runner(self, model: str | None = None) -> CopilotRunner:
        config = get_phase_config("03")
        sem = asyncio.Semaphore(1)
        return CopilotRunner(config, sem, model=model)

    def test_base_args(self) -> None:
        runner = self._runner()
        cmd = runner._build_cmd("/usr/local/bin/copilot", "PROMPT")
        assert cmd[0] == "/usr/local/bin/copilot"
        assert "-p" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--allow-all-tools" in cmd
        assert "--no-banner" in cmd

    def test_no_model_flag_when_unset(self) -> None:
        runner = self._runner()
        cmd = runner._build_cmd("copilot", "PROMPT")
        assert "--model" not in cmd

    def test_model_flag_when_set(self) -> None:
        runner = self._runner(model="gpt-5-turbo")
        cmd = runner._build_cmd("copilot", "PROMPT")
        assert "--model" in cmd
        assert "gpt-5-turbo" in cmd


# ---------------------------------------------------------------------------
# JSONL event parsing (_consume_event)
# ---------------------------------------------------------------------------


class TestConsumeEvent:
    def _runner(self) -> CopilotRunner:
        config = get_phase_config("03")
        return CopilotRunner(config, asyncio.Semaphore(1))

    def _fresh_state(self) -> dict:
        return {
            "assistant_text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "error_message": None,
            "session_id": None,
            "tool_count": 0,
            "saw_complete": False,
        }

    def test_ignores_blank_line(self) -> None:
        runner = self._runner()
        state = self._fresh_state()
        runner._consume_event("", state)
        runner._consume_event("   \n", state)
        assert state == self._fresh_state()

    def test_ignores_invalid_json(self) -> None:
        runner = self._runner()
        state = self._fresh_state()
        runner._consume_event("not json at all\n", state)
        assert state["assistant_text"] == ""

    def test_session_boot_captures_id(self) -> None:
        runner = self._runner()
        state = self._fresh_state()
        raw = json.dumps(
            {"type": "session.start", "data": {"sessionId": "sess-abc"}}
        )
        runner._consume_event(raw, state)
        assert state["session_id"] == "sess-abc"

    def test_assistant_delta_accumulates_text(self) -> None:
        runner = self._runner()
        state = self._fresh_state()
        runner._consume_event(
            json.dumps({"type": "assistant.delta", "data": {"text": "Hello "}}),
            state,
        )
        runner._consume_event(
            json.dumps({"type": "message.delta", "data": {"text": "world."}}),
            state,
        )
        assert state["assistant_text"] == "Hello world."

    def test_message_full_only_when_no_deltas(self) -> None:
        runner = self._runner()
        state = self._fresh_state()
        runner._consume_event(
            json.dumps({"type": "assistant.delta", "data": {"text": "delta"}}),
            state,
        )
        runner._consume_event(
            json.dumps(
                {"type": "message", "data": {"message": {"text": "full"}}}
            ),
            state,
        )
        # Full message ignored because deltas already accumulated.
        assert state["assistant_text"] == "delta"

    def test_message_full_when_no_deltas(self) -> None:
        runner = self._runner()
        state = self._fresh_state()
        runner._consume_event(
            json.dumps({"type": "message", "data": {"content": "complete reply"}}),
            state,
        )
        assert state["assistant_text"] == "complete reply"

    def test_tool_events_increment_count(self) -> None:
        runner = self._runner()
        state = self._fresh_state()
        runner._consume_event(json.dumps({"type": "tool.start"}), state)
        runner._consume_event(json.dumps({"type": "tool.start"}), state)
        runner._consume_event(json.dumps({"type": "tool.result"}), state)
        assert state["tool_count"] == 2

    def test_error_captures_message(self) -> None:
        runner = self._runner()
        state = self._fresh_state()
        runner._consume_event(
            json.dumps({"type": "error", "data": {"message": "policy denied"}}),
            state,
        )
        assert state["error_message"] == "policy denied"

    def test_complete_extracts_usage(self) -> None:
        runner = self._runner()
        state = self._fresh_state()
        runner._consume_event(
            json.dumps(
                {
                    "type": "complete",
                    "data": {"usage": {"input_tokens": 1234, "output_tokens": 567}},
                }
            ),
            state,
        )
        assert state["input_tokens"] == 1234
        assert state["output_tokens"] == 567
        assert state["saw_complete"] is True

    def test_complete_accepts_openai_token_names(self) -> None:
        runner = self._runner()
        state = self._fresh_state()
        runner._consume_event(
            json.dumps(
                {
                    "type": "session.end",
                    "data": {
                        "usage": {"prompt_tokens": 100, "completion_tokens": 50}
                    },
                }
            ),
            state,
        )
        assert state["input_tokens"] == 100
        assert state["output_tokens"] == 50


# ---------------------------------------------------------------------------
# Result extraction
# ---------------------------------------------------------------------------


class TestExtractResultsFromText:
    def _runner(self) -> CopilotRunner:
        config = get_phase_config("03")
        return CopilotRunner(config, asyncio.Semaphore(1))

    def test_fenced_json_array(self) -> None:
        runner = self._runner()
        text = (
            "Here is the audit:\n\n"
            "```json\n"
            '[{"property_id": "PROP-1"}, {"property_id": "PROP-2"}]\n'
            "```\n"
        )
        result = runner._extract_results_from_text(text)
        assert result is not None
        assert len(result) == 2
        assert result[0]["property_id"] == "PROP-1"

    def test_raw_array(self) -> None:
        runner = self._runner()
        text = '[{"check_id": "C-1"}]'
        result = runner._extract_results_from_text(text)
        assert result == [{"check_id": "C-1"}]

    def test_returns_none_on_empty(self) -> None:
        runner = self._runner()
        assert runner._extract_results_from_text("") is None
        assert runner._extract_results_from_text("no json here") is None


class TestNormalizeResultData:
    def _runner(self) -> CopilotRunner:
        config = get_phase_config("03")
        return CopilotRunner(config, asyncio.Semaphore(1))

    def test_list_passthrough(self) -> None:
        runner = self._runner()
        data = [{"a": 1}, {"b": 2}, "not a dict"]
        assert runner._normalize_result_data(data) == [{"a": 1}, {"b": 2}]

    def test_dict_with_result_key(self) -> None:
        runner = self._runner()
        # Phase 03's result_key is "audit_items" — see config.py
        data = {"audit_items": [{"id": "x"}]}
        assert runner._normalize_result_data(data) == [{"id": "x"}]

    def test_dict_wrap_when_no_known_key(self) -> None:
        runner = self._runner()
        assert runner._normalize_result_data({"foo": "bar"}) == [{"foo": "bar"}]


# ---------------------------------------------------------------------------
# Binary resolution (mocked)
# ---------------------------------------------------------------------------


class TestResolveBin:
    def test_returns_none_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "orchestrator.copilot_runner.shutil.which", lambda _name: None
        )
        assert _resolve_copilot_bin() is None

    def test_returns_path_when_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "orchestrator.copilot_runner.shutil.which",
            lambda _name: "/usr/local/bin/copilot",
        )
        assert _resolve_copilot_bin() == "/usr/local/bin/copilot"
