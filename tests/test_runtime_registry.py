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
    """claude / api / codex / gemini / ollama are wired; copilot orchestrator runner is a follow-up."""

    for impl in ("claude", "api", "codex", "gemini", "ollama"):
        assert rr.get(impl).implemented is True, (
            f"{impl} should be implemented — OpenAI-compat function-calling "
            "routes through APIRunner / its subclasses."
        )
    # Copilot stays stubbed for now: the @github/copilot agentic CLI does
    # support tool-calling, so a CopilotRunner subclass is feasible, but
    # it hasn't been written yet. Web chat side already works.
    assert rr.get("copilot").implemented is False


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


def test_probe_implemented_runtimes_flag_true() -> None:
    """codex / gemini / ollama probes must self-report implemented=True."""

    for impl in ("codex", "gemini", "ollama"):
        result = rr.probe(impl)
        assert result.implemented is True, impl


def test_probe_copilot_stays_stubbed() -> None:
    """Copilot orchestrator runner is a follow-up; stays implemented=False."""

    result = rr.probe("copilot")
    assert result.implemented is False
    joined = " ".join(result.notes).lower()
    assert "orchestrator runner not yet implemented" in joined


# ---------------------------------------------------------------------------
# APIRunner subclass defaults
# ---------------------------------------------------------------------------


def test_codex_runner_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """CodexAPIRunner targets OpenAI's chat-completions endpoint."""

    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    import asyncio

    from orchestrator.api_runner import CodexAPIRunner
    from orchestrator.runner import CircuitBreaker

    from orchestrator.config import get_phase_config

    cfg = get_phase_config("01a")
    sem = asyncio.Semaphore(1)
    cb = CircuitBreaker(cfg)
    r = CodexAPIRunner(cfg, sem, circuit_breaker=cb)
    assert r.base_url == "https://api.openai.com/v1"
    assert r.model == "gpt-4o"
    assert r.RUNTIME_LABEL == "codex"


def test_gemini_runner_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """GeminiAPIRunner targets Google's OpenAI compatibility endpoint."""

    monkeypatch.delenv("GEMINI_BASE_URL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    import asyncio

    from orchestrator.api_runner import GeminiAPIRunner
    from orchestrator.runner import CircuitBreaker

    from orchestrator.config import get_phase_config

    cfg = get_phase_config("01a")
    sem = asyncio.Semaphore(1)
    r = GeminiAPIRunner(cfg, sem, circuit_breaker=CircuitBreaker(cfg))
    assert "googleapis.com" in r.base_url
    assert "gemini" in r.model
    assert r.RUNTIME_LABEL == "gemini"


def test_ollama_runner_self_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    """OllamaAPIRunner derives base_url from OLLAMA_HOST when no explicit URL is set."""

    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    import asyncio

    from orchestrator.api_runner import OllamaAPIRunner
    from orchestrator.runner import CircuitBreaker

    from orchestrator.config import get_phase_config

    cfg = get_phase_config("01a")
    sem = asyncio.Semaphore(1)
    r = OllamaAPIRunner(cfg, sem, circuit_breaker=CircuitBreaker(cfg))
    assert r.base_url == "http://localhost:11434/v1"
    assert r.model == "llama3.2"


def test_ollama_runner_explicit_kwarg_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constructor kwargs win over env vars (operator can pin via Python)."""

    monkeypatch.setenv("OLLAMA_BASE_URL", "https://env-wins.example/v1")

    import asyncio

    from orchestrator.api_runner import OllamaAPIRunner
    from orchestrator.runner import CircuitBreaker

    from orchestrator.config import get_phase_config

    cfg = get_phase_config("01a")
    sem = asyncio.Semaphore(1)
    r = OllamaAPIRunner(
        cfg,
        sem,
        circuit_breaker=CircuitBreaker(cfg),
        base_url="https://kwarg-wins.example/v1",
        model="custom-model",
    )
    assert r.base_url == "https://kwarg-wins.example/v1"
    assert r.model == "custom-model"
