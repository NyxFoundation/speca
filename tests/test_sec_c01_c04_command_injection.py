"""Tests for SEC-C01 and SEC-C04 command injection fixes in base_runner."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from benchmarks.runners.base_runner import resolve_version, run_command


class TestRunCommandShellEscaping:
    """SEC-C01: run_command must escape parameters when use_shell=True."""

    @patch("benchmarks.runners.base_runner.subprocess.run")
    def test_shell_mode_escapes_case_id_metacharacters(self, mock_run: MagicMock) -> None:
        """A case_id containing shell metacharacters must be quoted, not executed."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        malicious_case_id = "; echo pwned"
        run_command(
            template="tool --id {case_id} --src {code_path} --out {output_path}",
            code_path=Path("/tmp/code.sol"),
            output_path=Path("/tmp/out.json"),
            case_id=malicious_case_id,
            use_shell=True,
            timeout=30,
        )

        actual_cmd = mock_run.call_args[0][0]
        # The shell metacharacters in case_id must be quoted/escaped
        assert shlex.quote(malicious_case_id) in actual_cmd
        # The raw unquoted malicious string must NOT appear as-is
        # (shlex.quote wraps it, so the raw form without quotes should be absent)
        assert "; echo pwned" not in actual_cmd.replace(shlex.quote(malicious_case_id), "")

    @patch("benchmarks.runners.base_runner.subprocess.run")
    def test_shell_mode_escapes_code_path_metacharacters(self, mock_run: MagicMock) -> None:
        """A code_path containing shell metacharacters must be quoted."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        malicious_path = Path("/tmp/$(rm -rf /)")
        run_command(
            template="tool {code_path}",
            code_path=malicious_path,
            output_path=Path("/tmp/out.json"),
            case_id="safe_id",
            use_shell=True,
            timeout=30,
        )

        actual_cmd = mock_run.call_args[0][0]
        assert shlex.quote(str(malicious_path)) in actual_cmd

    @patch("benchmarks.runners.base_runner.subprocess.run")
    def test_shell_mode_passes_shell_true(self, mock_run: MagicMock) -> None:
        """When use_shell=True, subprocess.run is called with shell=True."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        run_command(
            template="tool {case_id}",
            code_path=Path("/tmp/code.sol"),
            output_path=Path("/tmp/out.json"),
            case_id="safe",
            use_shell=True,
            timeout=30,
        )

        assert mock_run.call_args[1]["shell"] is True

    @patch("benchmarks.runners.base_runner.subprocess.run")
    def test_non_shell_mode_does_not_quote(self, mock_run: MagicMock) -> None:
        """When use_shell=False, parameters are not shell-quoted (shlex.split handles it)."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        run_command(
            template="tool --id {case_id} --src {code_path}",
            code_path=Path("/tmp/code.sol"),
            output_path=Path("/tmp/out.json"),
            case_id="normal_id",
            use_shell=False,
            timeout=30,
        )

        actual_cmd = mock_run.call_args[0][0]
        # In non-shell mode the command should be a list (from shlex.split)
        assert isinstance(actual_cmd, list)


class TestResolveVersionNoShell:
    """SEC-C04: resolve_version must not use shell=True."""

    @patch("benchmarks.runners.base_runner.subprocess.run")
    def test_uses_shell_false(self, mock_run: MagicMock) -> None:
        """resolve_version must call subprocess.run without shell=True."""
        mock_run.return_value = MagicMock(stdout="1.0.0", stderr="")

        resolve_version("mytool --version")

        # Verify it was called with a list (shlex.split result), not a string
        actual_cmd = mock_run.call_args[0][0]
        assert isinstance(actual_cmd, list)
        assert actual_cmd == ["mytool", "--version"]
        # Verify shell is not True (either absent or explicitly False)
        shell_value = mock_run.call_args[1].get("shell", False)
        assert shell_value is not True

    @patch("benchmarks.runners.base_runner.subprocess.run")
    def test_metacharacters_not_interpreted(self, mock_run: MagicMock) -> None:
        """Shell metacharacters in the command should be passed as literal arguments."""
        mock_run.return_value = MagicMock(stdout="", stderr="")

        resolve_version("echo hello; rm -rf /")

        actual_cmd = mock_run.call_args[0][0]
        # shlex.split treats ';' as a literal part of arguments when not in a shell
        # The command list should contain the semicolon as a separate token, not
        # cause shell interpretation
        assert isinstance(actual_cmd, list)
        assert actual_cmd == ["echo", "hello;", "rm", "-rf", "/"]

    def test_empty_command_returns_none(self) -> None:
        """An empty command string should return None without calling subprocess."""
        assert resolve_version("") is None

    @patch("benchmarks.runners.base_runner.subprocess.run")
    def test_returns_version_string(self, mock_run: MagicMock) -> None:
        """resolve_version returns the stripped stdout."""
        mock_run.return_value = MagicMock(stdout="  2.3.1\n", stderr="")

        result = resolve_version("tool --version")

        assert result == "2.3.1"
