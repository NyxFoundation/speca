"""Tests for the claude_pty runtime (issue #80).

The pty boundary is mocked throughout — CI cannot (and must not) spawn a
live authenticated claude TUI. What IS exercised for real: registry
wiring, driver state machine (ready detection, bracketed-paste submit,
completion, timeouts), runner path/prompt/parse plumbing, and the
circuit-breaker integration inherited from ClaudeRunner. The live
interactive round-trip is manual via scripts/contrib/claude_pty_driver.py.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from orchestrator import claude_pty_runner as cpr
from orchestrator import runtime_registry as rr
from orchestrator.config import PhaseConfig
from orchestrator.runner import CircuitBreaker


# ---------------------------------------------------------------------------
# strip_ansi
# ---------------------------------------------------------------------------


def test_strip_ansi_removes_csi_and_osc() -> None:
    raw = (
        "\x1b[1m\x1b[38;5;208mhello\x1b[0m "
        "\x1b]0;window title\x07world\x1b[2K\x1b[1G"
    )
    assert cpr.strip_ansi(raw) == "hello world"


def test_strip_ansi_keeps_newlines_drops_cr_and_ctrl() -> None:
    assert cpr.strip_ansi("a\r\nb\x08c\x00") == "a\nbc"


def test_strip_ansi_removes_bracketed_paste_markers() -> None:
    assert cpr.strip_ansi("\x1b[200~pasted\x1b[201~") == "pasted"


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------


def test_registry_includes_claude_pty() -> None:
    assert "claude_pty" in rr.all_runtime_ids()
    descr = rr.get("claude_pty")
    assert descr.implemented is True
    assert "pty" in descr.summary.lower()


def test_default_runtime_is_still_plain_claude(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The insurance path must never become the default."""

    monkeypatch.delenv("ORCHESTRATOR_RUNNER", raising=False)
    assert rr.resolve_active() == "claude"


def test_resolve_active_accepts_claude_pty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORCHESTRATOR_RUNNER", "claude_pty")
    assert rr.resolve_active() == "claude_pty"


def test_probe_claude_pty_returns_availability_struct() -> None:
    result = rr.probe("claude_pty")
    assert isinstance(result, rr.RuntimeAvailability)
    assert result.runtime_id == "claude_pty"
    assert result.implemented is True
    joined = " ".join(result.notes).lower()
    assert "issue #80" in joined
    assert "off by default" in joined


# ---------------------------------------------------------------------------
# Platform gate
# ---------------------------------------------------------------------------


def test_pty_supported_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cpr.sys, "platform", "linux")
    supported, reason = cpr.pty_supported()
    assert supported is True
    assert "POSIX" in reason


def test_pty_supported_windows_without_pywinpty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cpr.sys, "platform", "win32")
    monkeypatch.setattr(cpr, "_has_winpty", lambda: False)
    supported, reason = cpr.pty_supported()
    assert supported is False
    assert "pywinpty" in reason


def test_pty_supported_windows_with_pywinpty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cpr.sys, "platform", "win32")
    monkeypatch.setattr(cpr, "_has_winpty", lambda: True)
    supported, _ = cpr.pty_supported()
    assert supported is True


def test_runner_ctor_fails_fast_when_platform_unsupported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(cpr, "pty_supported", lambda: (False, "no pty here"))
    with pytest.raises(RuntimeError, match="no pty here"):
        cpr.ClaudePtyRunner(
            _phase_config(tmp_path),
            asyncio.Semaphore(1),
        )


# ---------------------------------------------------------------------------
# drive_one_prompt — fake pty
# ---------------------------------------------------------------------------


class FakePty:
    """Scripted pty double.

    ``script`` is a list of byte chunks emitted one per read() before the
    prompt is submitted; after the driver writes a line ending in b"\\r",
    ``response`` chunks are emitted, and ``on_submit`` (if given) runs —
    e.g. to write the result file like Claude's Write tool would.
    """

    def __init__(self, script, response=(), on_submit=None):
        self._pre = list(script)
        self._post = list(response)
        self._on_submit = on_submit
        self.writes: list[bytes] = []
        self.submitted = False
        self.killed = False

    def read(self, timeout: float) -> bytes:
        queue = self._post if self.submitted else self._pre
        if queue:
            return queue.pop(0)
        time.sleep(min(timeout, 0.01))
        return b""

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        if data.startswith(b"/exit"):
            self.killed = True  # a real REPL exits promptly on /exit
            return
        if data.endswith(b"\r") and not self.submitted:
            self.submitted = True
            if self._on_submit is not None:
                self._on_submit()

    def alive(self) -> bool:
        return not self.killed

    def kill(self) -> None:
        self.killed = True


READY_BANNER = b"\x1b[1mWelcome to Claude\x1b[0m\r\n> \r\n? for shortcuts"


def test_drive_one_prompt_happy_path(tmp_path: Path) -> None:
    result_path = tmp_path / "PARTIAL_TEST.json"

    def write_result() -> None:
        result_path.write_text(json.dumps([{"property_id": "P-1"}]), encoding="utf-8")

    io = FakePty(
        script=[READY_BANNER],
        response=[b"\x1b[2Kworking...\r\n", b"done. wrote the file.\r\n"],
        on_submit=write_result,
    )
    transcript = cpr.drive_one_prompt(
        io,
        "do the thing",
        lambda: cpr.result_file_ready(result_path),
        ready_timeout=5.0,
        completion_timeout=10.0,
        poll_interval=0.01,
        quiet_confirm=0.05,
    )
    # Prompt was pasted with bracketed-paste markers, then submitted.
    joined = b"".join(io.writes)
    assert cpr.BRACKETED_PASTE_START + b"do the thing" + cpr.BRACKETED_PASTE_END in joined
    assert b"\r" in joined
    # Transcript is ANSI-stripped and contains the streamed output.
    assert "working..." in transcript
    assert "\x1b" not in transcript
    # Result file was accepted as completion.
    assert cpr.result_file_ready(result_path)
    # Polite /exit was attempted after completion.
    assert any(w.startswith(b"/exit") for w in io.writes)


def test_drive_one_prompt_ready_timeout() -> None:
    io = FakePty(script=[])  # never shows a prompt
    with pytest.raises(cpr.PtyTimeout, match="not ready"):
        cpr.drive_one_prompt(
            io,
            "x",
            lambda: False,
            ready_timeout=0.2,
            completion_timeout=1.0,
            poll_interval=0.01,
        )


def test_drive_one_prompt_completion_timeout(tmp_path: Path) -> None:
    io = FakePty(script=[READY_BANNER], response=[b"thinking forever"])
    with pytest.raises(cpr.PtyTimeout, match="did not complete"):
        cpr.drive_one_prompt(
            io,
            "x",
            lambda: False,
            ready_timeout=5.0,
            completion_timeout=0.3,
            idle_done=99.0,  # keep the idle heuristic out of this test
            poll_interval=0.01,
            quiet_confirm=0.05,
        )


def test_drive_one_prompt_exit_before_ready_raises() -> None:
    class DeadPty(FakePty):
        def read(self, timeout: float) -> bytes:
            raise cpr.PtyEof("gone")

    with pytest.raises(cpr.PtyDriverError, match="before showing its prompt"):
        cpr.drive_one_prompt(
            DeadPty(script=[]),
            "x",
            lambda: False,
            ready_timeout=1.0,
            completion_timeout=1.0,
            poll_interval=0.01,
        )


def test_drive_one_prompt_idle_at_prompt_completes(tmp_path: Path) -> None:
    """Directory-mode phases have no result file: output then idle at the
    prompt must count as completion."""

    io = FakePty(
        script=[READY_BANNER],
        response=[b"did some work\r\n> \r\n? for shortcuts"],
    )
    transcript = cpr.drive_one_prompt(
        io,
        "x",
        lambda: False,
        ready_timeout=5.0,
        completion_timeout=10.0,
        idle_done=0.1,
        poll_interval=0.01,
        quiet_confirm=0.05,
    )
    assert "did some work" in transcript


# ---------------------------------------------------------------------------
# result_file_ready
# ---------------------------------------------------------------------------


def test_result_file_ready_states(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    assert cpr.result_file_ready(p) is False  # missing
    p.write_text("", encoding="utf-8")
    assert cpr.result_file_ready(p) is False  # empty
    p.write_text('{"items": [', encoding="utf-8")
    assert cpr.result_file_ready(p) is False  # torn write
    p.write_text('{"items": []}', encoding="utf-8")
    assert cpr.result_file_ready(p) is True


# ---------------------------------------------------------------------------
# ClaudePtyRunner — _execute_batch with the pty boundary mocked
# ---------------------------------------------------------------------------


def _phase_config(tmp_path: Path) -> PhaseConfig:
    prompt_file = tmp_path / "prompt.md"
    if not prompt_file.exists():
        prompt_file.write_text(
            "Process QUEUE_FILE and write results to OUTPUT_FILE.",
            encoding="utf-8",
        )
    return PhaseConfig(
        phase_id="pty-test",
        name="pty test phase",
        description="synthetic phase for claude_pty tests",
        skill_path=Path(""),
        prompt_path=prompt_file,  # absolute — resolve_core_asset passes through
        queue_pattern="",
        output_pattern="",
        mcp_servers=[],
        item_id_field="property_id",
        result_key="properties",
        timeout_seconds=30,
    )


def _make_runner(tmp_path: Path) -> cpr.ClaudePtyRunner:
    cfg = _phase_config(tmp_path)
    return cpr.ClaudePtyRunner(
        cfg,
        asyncio.Semaphore(1),
        circuit_breaker=CircuitBreaker(cfg),
    )


def test_execute_batch_returns_claude_runner_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end through run_batch with only _drive_session stubbed:
    result shape must match ClaudeRunner (list[dict]) and the circuit
    breaker must record the success."""

    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(cpr, "pty_supported", lambda: (True, "test"))
    runner = _make_runner(tmp_path)

    def fake_drive(argv, env, prompt, result_parse_path, directory_mode, log_file, holder):
        # The prompt must carry the phase template + kwarg args block.
        assert "Process QUEUE_FILE" in prompt
        assert "OUTPUT_FILE=" in prompt
        # argv is interactive: no -p, no stream-json.
        assert "-p" not in argv
        assert "--output-format" not in argv
        assert "--dangerously-skip-permissions" in argv
        # Nested-session guard must be inherited from ClaudeRunner._build_env.
        assert "CLAUDECODE" not in env
        result_parse_path.write_text(
            json.dumps({"properties": [{"property_id": "P-1"}, {"property_id": "P-2"}]}),
            encoding="utf-8",
        )
        return "transcript"

    monkeypatch.setattr(cpr.ClaudePtyRunner, "_drive_session", staticmethod(fake_drive))

    batch = [{"property_id": "P-1"}, {"property_id": "P-2"}]
    results = asyncio.run(runner.run_batch(batch, worker_id=0, batch_index=0))

    assert isinstance(results, list)
    assert [r["property_id"] for r in results] == ["P-1", "P-2"]
    assert runner.circuit_breaker.total_successes == 1
    assert runner.circuit_breaker.total_failures == 0


def test_execute_batch_transcript_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No result file -> results recovered from a ```json block in the
    ANSI-stripped transcript, mirroring ClaudeRunner's log fallback."""

    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(cpr, "pty_supported", lambda: (True, "test"))
    runner = _make_runner(tmp_path)

    transcript = (
        "I wrote the results:\n```json\n"
        + json.dumps({"properties": [{"property_id": "P-9"}]})
        + "\n```\n"
    )
    monkeypatch.setattr(
        cpr.ClaudePtyRunner,
        "_drive_session",
        staticmethod(lambda *a, **k: transcript),
    )

    results = asyncio.run(
        runner.run_batch([{"property_id": "P-9"}], worker_id=0, batch_index=0)
    )
    assert results == [{"property_id": "P-9"}]


def test_execute_batch_pty_timeout_counts_as_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PtyTimeout -> None result -> retries exhausted -> circuit breaker
    records the failure (retry/breaker integration is live, not bypassed)."""

    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(cpr, "pty_supported", lambda: (True, "test"))
    runner = _make_runner(tmp_path)
    runner.max_retries = 0  # no backoff sleeps in the test

    def fake_drive(*a, **k):
        raise cpr.PtyTimeout("claude REPL did not complete within 1s")

    monkeypatch.setattr(cpr.ClaudePtyRunner, "_drive_session", staticmethod(fake_drive))

    results = asyncio.run(
        runner.run_batch([{"property_id": "P-1"}], worker_id=0, batch_index=0)
    )
    assert results is None
    assert runner.circuit_breaker.total_failures == 1


def test_interactive_cmd_has_no_print_mode_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(cpr, "pty_supported", lambda: (True, "test"))
    runner = _make_runner(tmp_path)
    cmd = runner._build_interactive_cmd()
    assert "-p" not in cmd
    assert "--output-format" not in cmd
    assert "--verbose" not in cmd
    assert "--max-turns" not in cmd
    assert "--dangerously-skip-permissions" in cmd
