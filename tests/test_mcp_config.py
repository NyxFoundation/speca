"""Tests for MCP config resolution in ClaudeRunner (issue #98).

Covers:
  - resolution order: $SPECA_MCP_CONFIG > ./.mcp.json > <core root>/.mcp.json
  - hard failure when SPECA_MCP_CONFIG points at a missing file
  - the loud stderr warning when a phase declares servers that are absent
    (including the cached-config reuse path)
  - per-phase filtering keeps only the declared servers
"""

import asyncio
import json
from pathlib import Path

import pytest

from scripts.orchestrator.config import PhaseConfig
from scripts.orchestrator.runner import ClaudeRunner


def make_runner(mcp_servers):
    config = PhaseConfig(
        phase_id="testphase",
        name="Test Phase",
        description="MCP config resolution test",
        skill_path=Path(""),
        prompt_path=Path(""),
        queue_pattern="",
        output_pattern="",
        mcp_servers=mcp_servers,
    )
    return ClaudeRunner(config, asyncio.Semaphore(1))


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Run each test from an empty cwd with isolated output and core roots.

    SPECA_ROOT points at an (empty) tmp dir so a developer's locally
    generated repo-root .mcp.json can never leak into the assertions.
    """
    workspace = tmp_path / "workspace"
    core_root = tmp_path / "core"
    workspace.mkdir()
    core_root.mkdir()
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("SPECA_ROOT", str(core_root))
    monkeypatch.delenv("SPECA_MCP_CONFIG", raising=False)
    return workspace, core_root


def write_mcp_json(path: Path, servers: dict) -> None:
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def load_servers(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)["mcpServers"]


def test_workspace_mcp_json_is_used_and_filtered(isolated_env, capsys):
    workspace, _ = isolated_env
    write_mcp_json(
        workspace / ".mcp.json",
        {
            "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
            "github": {"command": "npx", "args": ["-y", "server-github"]},
        },
    )
    runner = make_runner(["fetch"])
    servers = load_servers(runner._get_phase_mcp_config())
    assert set(servers) == {"fetch"}
    assert "WARNING" not in capsys.readouterr().err


def test_core_root_fallback_when_workspace_has_none(isolated_env, capsys):
    _, core_root = isolated_env
    write_mcp_json(
        core_root / ".mcp.json",
        {"fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}},
    )
    runner = make_runner(["fetch"])
    servers = load_servers(runner._get_phase_mcp_config())
    assert set(servers) == {"fetch"}
    assert "WARNING" not in capsys.readouterr().err


def test_workspace_wins_over_core_root(isolated_env):
    workspace, core_root = isolated_env
    write_mcp_json(workspace / ".mcp.json", {"fetch": {"command": "workspace-cmd"}})
    write_mcp_json(core_root / ".mcp.json", {"fetch": {"command": "core-cmd"}})
    runner = make_runner(["fetch"])
    servers = load_servers(runner._get_phase_mcp_config())
    assert servers["fetch"]["command"] == "workspace-cmd"


def test_env_var_wins_over_workspace(isolated_env, tmp_path, monkeypatch):
    workspace, _ = isolated_env
    write_mcp_json(workspace / ".mcp.json", {"fetch": {"command": "workspace-cmd"}})
    explicit = tmp_path / "explicit-mcp.json"
    write_mcp_json(explicit, {"fetch": {"command": "explicit-cmd"}})
    monkeypatch.setenv("SPECA_MCP_CONFIG", str(explicit))
    runner = make_runner(["fetch"])
    servers = load_servers(runner._get_phase_mcp_config())
    assert servers["fetch"]["command"] == "explicit-cmd"


def test_env_var_pointing_at_missing_file_raises(isolated_env, tmp_path, monkeypatch):
    monkeypatch.setenv("SPECA_MCP_CONFIG", str(tmp_path / "does-not-exist.json"))
    runner = make_runner(["fetch"])
    with pytest.raises(FileNotFoundError, match="SPECA_MCP_CONFIG"):
        runner._get_phase_mcp_config()


def test_missing_config_warns_loudly(isolated_env, capsys):
    runner = make_runner(["fetch", "filesystem"])
    servers = load_servers(runner._get_phase_mcp_config())
    assert servers == {}
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "fetch" in err
    assert "filesystem" in err
    assert "SPECA_MCP_CONFIG" in err


def test_partial_config_warns_about_missing_servers_only(isolated_env, capsys):
    workspace, _ = isolated_env
    write_mcp_json(workspace / ".mcp.json", {"fetch": {"command": "uvx"}})
    runner = make_runner(["fetch", "tree_sitter"])
    servers = load_servers(runner._get_phase_mcp_config())
    assert set(servers) == {"fetch"}
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "tree_sitter" in err


def test_fixing_config_after_empty_run_clears_warning(isolated_env, capsys):
    # First run with no config anywhere: empty per-phase file plus warning.
    runner = make_runner(["fetch"])
    first = runner._get_phase_mcp_config()
    assert load_servers(first) == {}
    assert "WARNING" in capsys.readouterr().err
    # The user follows the warning's advice and creates .mcp.json. The next
    # run must pick it up even though the per-phase file already exists on
    # disk — a stale generated config must never be a dead end that keeps
    # the warning (and the empty server list) alive (PR #117 review).
    workspace, _ = isolated_env
    write_mcp_json(workspace / ".mcp.json", {"fetch": {"command": "uvx"}})
    second_runner = make_runner(["fetch"])
    second = second_runner._get_phase_mcp_config()
    assert second == first
    assert set(load_servers(second)) == {"fetch"}
    assert "WARNING" not in capsys.readouterr().err


def test_env_var_honored_even_when_phase_config_already_written(
    isolated_env, tmp_path, monkeypatch, capsys
):
    # A leftover per-phase file must not short-circuit SPECA_MCP_CONFIG
    # handling: pointing the env var at a missing file fails loudly even
    # when a previous run already wrote outputs/.mcp_configs/mcp_<phase>.json.
    runner = make_runner(["fetch"])
    assert runner._get_phase_mcp_config().exists()
    capsys.readouterr()
    monkeypatch.setenv("SPECA_MCP_CONFIG", str(tmp_path / "missing.json"))
    with pytest.raises(FileNotFoundError, match="SPECA_MCP_CONFIG"):
        make_runner(["fetch"])._get_phase_mcp_config()


def test_warning_emitted_once_per_runner(isolated_env, capsys):
    runner = make_runner(["fetch"])
    runner._get_phase_mcp_config()
    runner._get_phase_mcp_config()
    assert capsys.readouterr().err.count("WARNING") == 1


def test_no_warning_when_phase_declares_no_servers(isolated_env, capsys):
    runner = make_runner([])
    servers = load_servers(runner._get_phase_mcp_config())
    assert servers == {}
    assert "WARNING" not in capsys.readouterr().err
