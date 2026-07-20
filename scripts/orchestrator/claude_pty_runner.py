"""Claude interactive-REPL runner driven through a pseudo-terminal (issue #80).

Insurance path against the ``-p`` (print mode) flag becoming paywalled or
removed from subscription tiers. The production audit path stays
``ClaudeRunner`` (``claude -p --output-format stream-json``); this runner
drives the *interactive* ``claude`` REPL through a pty instead:

1. spawn ``claude`` under a pseudo-terminal (interactive TUI mode),
2. wait for the input prompt to render,
3. paste the phase prompt (bracketed paste, so multi-line prompts do not
   submit early) and press Enter,
4. read the streamed TUI output until the batch's result file — which the
   phase prompt instructs Claude to materialise via the Write tool — is
   present and parseable (or, in directory mode, until the REPL is idle
   at the prompt again),
5. parse the result file into the exact shape ``ClaudeRunner`` returns
   (``list[dict]``), with an ANSI-stripped transcript fallback.

Selection / default
-------------------
OFF by default. ``ORCHESTRATOR_RUNNER=claude_pty`` (or
``run_phase.py --runtime claude_pty``) selects it; the default runtime id
remains ``claude``. Adopt this path for real only when the ``-p`` flag is
actually unavailable on the account's tier — until then it exists as
tested-but-dormant insurance (see issue #80 for the paywall scenario and
``scripts/contrib/claude_pty_driver.py`` for the standalone PoC driver).

Platform support
----------------
* Linux / macOS: stdlib ``os.openpty`` + ``select`` — no extra dependency.
* Windows: requires the optional ``pywinpty`` package (winpty/ConPTY
  backend). It is NOT a declared dependency; without it, selecting
  ``claude_pty`` on Windows fails fast with an actionable error instead of
  pretending to work. Install with ``uv pip install pywinpty`` to enable.

Honest limitations (v1)
-----------------------
* **No token usage / cost tracking.** The interactive TUI does not emit
  the machine-readable ``usage`` payload that stream-json mode provides,
  so ``CostTracker`` receives no usage and the budget guard cannot fire
  from this runner. Circuit breaker, retries, and timeouts are fully
  active (inherited from ``ClaudeRunner.run_batch``).
* **One REPL per batch, one batch at a time.** Interactive sessions are
  not designed for parallel automation against one subscription;
  ``base.py`` clamps concurrency to 1 when this runtime is selected.
* **Prompt-detection is heuristic.** TUI markers are matched on
  ANSI-stripped output and are configurable via ``SPECA_PTY_READY_PATTERN``
  because the TUI layout is not a stable API. CI exercises this module
  with the pty boundary mocked (see tests/test_claude_pty_runner.py);
  a live interactive round-trip cannot run in CI without an authenticated
  claude CLI, so real-session verification is manual via the contrib PoC.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .config import PhaseConfig
from .runner import CircuitBreaker, ClaudeRunner
from .watchdog import CostTracker

if TYPE_CHECKING:
    from .archiver import Archiver


# ---------------------------------------------------------------------------
# ANSI stripping
# ---------------------------------------------------------------------------

# CSI sequences (colors, cursor movement), OSC sequences (window title,
# hyperlinks; BEL- or ST-terminated), charset selection, keypad modes, and
# single-char escapes. Bracketed-paste markers are CSI and covered too.
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"          # CSI ... final byte
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC ... BEL | ST
    r"|\x1b[()][0-9A-Za-z]"                # charset selection
    r"|\x1b[@-_]"                          # other C1 escapes
)

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_ansi(text: str) -> str:
    """Return ``text`` with ANSI escape sequences and control chars removed.

    Carriage returns are dropped (TUI redraws rewrite lines constantly);
    newlines are kept so the transcript stays line-oriented.
    """

    text = _ANSI_RE.sub("", text)
    text = text.replace("\r", "")
    return _CTRL_RE.sub("", text)


# ---------------------------------------------------------------------------
# Pty session backends
# ---------------------------------------------------------------------------


class PtyDriverError(RuntimeError):
    """Base error for pty-driver failures."""


class PtyTimeout(PtyDriverError):
    """The REPL did not reach the expected state within the deadline."""


class PtyEof(PtyDriverError):
    """The pty closed (process exited) while we were reading."""


def _has_winpty() -> bool:
    """True when the optional ``pywinpty`` package is importable."""

    return importlib.util.find_spec("winpty") is not None


def pty_supported() -> tuple[bool, str]:
    """Return (supported, reason) for the current platform.

    POSIX always has stdlib pty support. Windows needs ``pywinpty``; we
    refuse to fake a pty with plain pipes there — the claude TUI requires
    a real console, and pretending otherwise would produce silent garbage.
    """

    if sys.platform != "win32":
        return True, "POSIX pty via stdlib os.openpty."
    if _has_winpty():
        return True, "Windows pty via pywinpty (winpty/ConPTY)."
    return (
        False,
        "Windows requires the optional pywinpty package for the claude_pty "
        "runtime (`uv pip install pywinpty`). Plain pipes are not a pty and "
        "are not silently substituted.",
    )


class _PosixPty:
    """Blocking pty session around one subprocess (POSIX stdlib only)."""

    def __init__(self, argv: list[str], cwd: str, env: dict[str, str]):
        import fcntl
        import struct
        import termios

        self._master, slave = os.openpty()
        # A wide window reduces TUI line-wrapping noise in transcripts.
        try:
            fcntl.ioctl(
                slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 200, 0, 0)
            )
        except OSError:
            pass
        self._proc = subprocess.Popen(  # noqa: S603 — argv is CLI + fixed flags
            argv,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=cwd,
            env=env,
            close_fds=True,
            start_new_session=True,
        )
        os.close(slave)

    def read(self, timeout: float) -> bytes:
        """Read available bytes, waiting at most ``timeout`` seconds.

        Returns ``b""`` when nothing arrived; raises :class:`PtyEof` when
        the slave side closed.
        """

        import select

        ready, _, _ = select.select([self._master], [], [], timeout)
        if not ready:
            return b""
        try:
            data = os.read(self._master, 65536)
        except OSError as exc:  # EIO on Linux when the slave side closes
            raise PtyEof(str(exc)) from exc
        if not data:
            raise PtyEof("pty master returned EOF")
        return data

    def write(self, data: bytes) -> None:
        os.write(self._master, data)

    def alive(self) -> bool:
        return self._proc.poll() is None

    def kill(self) -> None:
        try:
            if self._proc.poll() is None:
                self._proc.kill()
                self._proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            os.close(self._master)
        except OSError:
            pass


class _WinPty:
    """Blocking pty session via the optional ``pywinpty`` package.

    pywinpty's ``read`` has no timeout, so a background thread pumps
    output into a queue and :meth:`read` waits on the queue instead.
    """

    def __init__(self, argv: list[str], cwd: str, env: dict[str, str]):
        supported, reason = pty_supported()
        if not supported:
            raise PtyDriverError(reason)
        import queue
        import threading

        import winpty  # noqa: PLC0415 — optional, gated by pty_supported()

        self._pty = winpty.PtyProcess.spawn(
            argv, cwd=cwd, env=env, dimensions=(50, 200)
        )
        self._queue: queue.Queue[bytes | None] = queue.Queue()

        def _pump() -> None:
            try:
                while True:
                    chunk = self._pty.read(65536)
                    if not chunk:
                        break
                    self._queue.put(
                        chunk.encode("utf-8", errors="replace")
                        if isinstance(chunk, str)
                        else chunk
                    )
            except EOFError:
                pass
            finally:
                self._queue.put(None)  # EOF sentinel

        self._reader = threading.Thread(target=_pump, daemon=True)
        self._reader.start()
        self._eof = False

    def read(self, timeout: float) -> bytes:
        import queue

        if self._eof:
            raise PtyEof("pty already at EOF")
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return b""
        if item is None:
            self._eof = True
            raise PtyEof("pty reader thread reached EOF")
        return item

    def write(self, data: bytes) -> None:
        self._pty.write(data.decode("utf-8", errors="replace"))

    def alive(self) -> bool:
        return bool(self._pty.isalive())

    def kill(self) -> None:
        try:
            self._pty.kill()
        except Exception:  # noqa: BLE001 — best-effort teardown
            pass


def open_pty_session(argv: list[str], cwd: str, env: dict[str, str]):
    """Spawn ``argv`` under a platform-appropriate pty session."""

    if sys.platform == "win32":
        return _WinPty(argv, cwd, env)
    return _PosixPty(argv, cwd, env)


# ---------------------------------------------------------------------------
# One-prompt round-trip driver (pure logic; pty boundary injected)
# ---------------------------------------------------------------------------

# Markers that indicate the claude TUI is idle at its input prompt. Matched
# against the ANSI-stripped tail of accumulated output. The TUI layout is
# not a stable API, hence the env override.
DEFAULT_READY_PATTERN = r"\? for shortcuts|^\s*> |\n\s*> "

BRACKETED_PASTE_START = b"\x1b[200~"
BRACKETED_PASTE_END = b"\x1b[201~"


def _ready_regex() -> re.Pattern[str]:
    return re.compile(
        os.environ.get("SPECA_PTY_READY_PATTERN", DEFAULT_READY_PATTERN),
        re.MULTILINE,
    )


def drive_one_prompt(
    io: Any,
    prompt: str,
    done_check: Callable[[], bool],
    *,
    ready_timeout: float = 90.0,
    completion_timeout: float = 3600.0,
    idle_done: float = 30.0,
    poll_interval: float = 0.25,
    quiet_confirm: float = 0.5,
    on_output: Callable[[bytes], None] | None = None,
) -> str:
    """Run one prompt round-trip against an interactive REPL behind ``io``.

    ``io`` is any object with ``read(timeout) -> bytes`` (``b""`` on
    timeout, :class:`PtyEof` on close), ``write(bytes)``, ``alive() ->
    bool`` and ``kill()`` — the real pty backends above, or a fake in
    tests. Pure driver logic lives here so CI can exercise every branch
    without a live claude session.

    Completion = ``done_check()`` returns True (normally: the result file
    exists and parses), or — for phases with no single result file — the
    REPL has produced output and then stayed idle at its prompt for
    ``idle_done`` seconds. Raises :class:`PtyTimeout` on deadline misses.

    Returns the ANSI-stripped transcript of everything the TUI printed.
    """

    ready_re = _ready_regex()
    raw = bytearray()

    def _pump(timeout: float) -> bytes:
        chunk = io.read(timeout)
        if chunk:
            raw.extend(chunk)
            if on_output is not None:
                on_output(chunk)
        return chunk

    def _tail_text() -> str:
        return strip_ansi(raw[-8192:].decode("utf-8", errors="replace"))

    # --- Phase 1: wait for the input prompt to render -------------------
    deadline = time.monotonic() + ready_timeout
    ready = False
    while not ready:
        try:
            chunk = _pump(poll_interval)
        except PtyEof:
            raise PtyDriverError(
                "claude exited before showing its prompt "
                f"(output tail: {_tail_text()[-500:]!r})"
            ) from None
        if ready_re.search(_tail_text()):
            # Confirm with a short quiet window: markers may scroll past
            # mid-redraw. Idle + marker visible = genuinely ready.
            if not chunk:
                quiet_until = time.monotonic() + quiet_confirm
                while time.monotonic() < quiet_until:
                    try:
                        if _pump(poll_interval):
                            break
                    except PtyEof:
                        break
                else:
                    ready = True
        if not ready and time.monotonic() > deadline:
            raise PtyTimeout(
                f"claude REPL not ready within {ready_timeout:.0f}s "
                f"(output tail: {_tail_text()[-500:]!r})"
            )

    # --- Phase 2: paste the prompt and submit ---------------------------
    io.write(
        BRACKETED_PASTE_START
        + prompt.encode("utf-8", errors="replace")
        + BRACKETED_PASTE_END
    )
    io.write(b"\r")

    # --- Phase 3: wait for completion -----------------------------------
    deadline = time.monotonic() + completion_timeout
    last_output = time.monotonic()
    saw_output = False
    eof = False
    while True:
        try:
            chunk = _pump(poll_interval)
        except PtyEof:
            eof = True
            chunk = b""
        if chunk:
            saw_output = True
            last_output = time.monotonic()
        if done_check():
            break
        if eof or not io.alive():
            # REPL died — done_check gets one final say above; otherwise
            # the caller decides based on whatever landed on disk.
            break
        idle_for = time.monotonic() - last_output
        if saw_output and idle_for >= idle_done and ready_re.search(_tail_text()):
            # Back at the prompt, idle, no result file to wait for
            # (directory-mode phases) — treat as complete.
            break
        if time.monotonic() > deadline:
            raise PtyTimeout(
                f"claude REPL did not complete within {completion_timeout:.0f}s"
            )

    # --- Phase 4: polite exit (caller's finally still calls kill()) -----
    if not eof and io.alive():
        try:
            io.write(b"/exit\r")
            exit_deadline = time.monotonic() + 5.0
            while io.alive() and time.monotonic() < exit_deadline:
                try:
                    _pump(poll_interval)
                except PtyEof:
                    break
        except (OSError, PtyDriverError):
            pass

    return strip_ansi(raw.decode("utf-8", errors="replace"))


def result_file_ready(path: Path) -> bool:
    """True when ``path`` exists, is non-empty, and parses as JSON.

    Parse success doubles as a write-completion check: while Claude's
    Write tool is mid-flight the file either doesn't exist or is whole
    (atomic write); a torn partial simply fails to parse and we keep
    waiting.
    """

    try:
        if not path.exists() or path.stat().st_size == 0:
            return False
        json.loads(path.read_text(encoding="utf-8"))
        return True
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class ClaudePtyRunner(ClaudeRunner):
    """Drives the interactive ``claude`` REPL through a pty per batch.

    Subclasses :class:`ClaudeRunner` so the retry loop, circuit-breaker
    accounting, prompt/queue/context construction, and result parsing
    (``run_batch`` / ``_build_prompt`` / ``_parse_results`` /
    ``_normalize_result_data``) are shared verbatim — only the execution
    transport differs. Returned batch results have the identical
    ``list[dict]`` shape.
    """

    RUNTIME_LABEL = "claude_pty"

    #: extra wall-clock grace on top of config.timeout_seconds for the
    #: outer asyncio guard around the driver thread.
    _OUTER_TIMEOUT_GRACE = 60.0

    def __init__(
        self,
        config: PhaseConfig,
        semaphore: asyncio.Semaphore,
        max_retries: int = 2,
        circuit_breaker: CircuitBreaker | None = None,
        cost_tracker: CostTracker | None = None,
        archiver: "Archiver | None" = None,
    ):
        super().__init__(
            config,
            semaphore,
            max_retries=max_retries,
            circuit_breaker=circuit_breaker,
            cost_tracker=cost_tracker,
            archiver=archiver,
        )
        supported, reason = pty_supported()
        if not supported:
            # Fail at construction, not mid-pipeline.
            raise RuntimeError(f"claude_pty runtime unavailable: {reason}")

    # -- transport ------------------------------------------------------

    def _build_interactive_cmd(self) -> list[str]:
        """argv for an interactive session (no ``-p``, no stream-json)."""

        claude_bin = (
            shutil.which("claude.cmd") if sys.platform == "win32" else None
        ) or shutil.which("claude") or "claude"
        cmd = [claude_bin, "--dangerously-skip-permissions"]
        if self.config.model:
            cmd.extend(["--model", self.config.model])
        if self.config.tools_filter is not None:
            cmd.extend(["--tools", ",".join(self.config.tools_filter)])
        if self.config.mcp_servers is not None:
            mcp_config_path = self._get_phase_mcp_config()
            cmd.extend(["--strict-mcp-config", "--mcp-config", str(mcp_config_path)])
        # NOTE: --max-turns is a print-mode option and is intentionally
        # omitted; turn limits are enforced by timeout in this transport.
        return cmd

    def _build_pty_env(self, **kwargs: Any) -> dict[str, str]:
        env = self._build_env(**kwargs)
        env.setdefault("TERM", "xterm-256color")
        env["COLUMNS"] = "200"
        env["LINES"] = "50"
        return env

    def _drive_session(
        self,
        argv: list[str],
        env: dict[str, str],
        prompt: str,
        result_parse_path: Path,
        directory_mode: bool,
        log_file: Path,
        holder: dict[str, Any],
    ) -> str:
        """Blocking pty round-trip; runs on a worker thread.

        This method is the mocked boundary in CI tests — everything above
        it (paths, prompt build, parsing, retries) runs for real; the
        live-TUI interaction below it cannot run without an authenticated
        claude CLI.
        """

        io = open_pty_session(argv, env.get("PWD") or str(Path.cwd()), env)
        holder["io"] = io

        raw_log = open(log_file, "ab")

        def _on_output(chunk: bytes) -> None:
            # JSONL event per chunk keeps the log greppable alongside the
            # stream-json logs other runners produce.
            line = json.dumps(
                {"type": "pty_output", "text": chunk.decode("utf-8", errors="replace")}
            ) + "\n"
            raw_log.write(line.encode("utf-8"))

        if directory_mode:
            def done_check() -> bool:
                return False  # completion via idle-at-prompt heuristic
        else:
            def done_check() -> bool:
                return result_file_ready(result_parse_path)

        try:
            transcript = drive_one_prompt(
                io,
                prompt,
                done_check,
                ready_timeout=float(os.environ.get("SPECA_PTY_READY_TIMEOUT", "90")),
                completion_timeout=float(self.config.timeout_seconds),
                idle_done=float(os.environ.get("SPECA_PTY_IDLE_DONE", "30")),
            )
            raw_log.write(
                (json.dumps({"type": "pty_transcript", "text": transcript}) + "\n").encode(
                    "utf-8"
                )
            )
            return transcript
        finally:
            raw_log.close()
            io.kill()

    # -- batch execution ------------------------------------------------

    async def _execute_batch(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> list[dict[str, Any]] | None:
        timestamp = int(time.time())
        phase_id = self.config.phase_id
        directory_mode = self.config.output_mode == "directory"

        queue_path = self.output_dir / (
            f"{phase_id}_ASYNC_QUEUE_W{worker_id}B{batch_index}_{timestamp}.json"
        )
        context_path = self.output_dir / (
            f"{phase_id}_CONTEXT_W{worker_id}B{batch_index}_{timestamp}.json"
        )
        log_file = self.log_dir / (
            f"{phase_id}_w{worker_id}b{batch_index}_{timestamp}.pty.log.jsonl"
        )

        if directory_mode:
            batch_output_dir = (
                self.output_dir / "graphs" / f"batch_w{worker_id}b{batch_index}_{timestamp}"
            )
            batch_output_dir.mkdir(parents=True, exist_ok=True)
            result_parse_path = batch_output_dir / ".no_result_file"
            output_kwargs: dict[str, str] = {"output_dir": str(batch_output_dir)}
        else:
            result_parse_path = self.output_dir / (
                f"{phase_id}_PARTIAL_W{worker_id}B{batch_index}_{timestamp}.json"
            )
            output_kwargs = {"output_file": str(result_parse_path)}

        self._save_json(
            queue_path, self._build_queue_payload(batch, worker_id, str(context_path))
        )
        self._save_json(context_path, self._build_context_payload(batch))

        common_kwargs: dict[str, Any] = dict(
            worker_id=worker_id,
            queue_file=str(queue_path),
            context_file=str(context_path),
            batch_size=len(batch),
            iteration=batch_index,
            timestamp=timestamp,
            **output_kwargs,
        )
        prompt_content = self._build_prompt(**common_kwargs)
        env = self._build_pty_env(**common_kwargs)
        env["PWD"] = self.config.workdir or str(Path.cwd())
        argv = self._build_interactive_cmd()

        holder: dict[str, Any] = {}
        try:
            transcript = await asyncio.wait_for(
                asyncio.to_thread(
                    self._drive_session,
                    argv,
                    env,
                    prompt_content,
                    result_parse_path,
                    directory_mode,
                    log_file,
                    holder,
                ),
                timeout=self.config.timeout_seconds + self._OUTER_TIMEOUT_GRACE,
            )
        except asyncio.TimeoutError:
            io = holder.get("io")
            if io is not None:
                io.kill()
            print(
                f"[W{worker_id}] Batch {batch_index} pty session timed out",
                file=sys.stderr,
            )
            return None
        except PtyTimeout as e:
            print(f"[W{worker_id}] Batch {batch_index}: {e}", file=sys.stderr)
            return None

        # Cost tracking: interactive mode exposes no machine-readable usage
        # payload — nothing is recorded (documented limitation; the budget
        # guard cannot fire from this runner).

        # Archive the pty log alongside stream-json logs.
        if self.archiver is not None:
            try:
                await asyncio.to_thread(self.archiver.record_log, phase_id, log_file)
            except Exception as _arc_err:  # noqa: BLE001 — archive is best-effort
                print(
                    f"[Archiver] warning: failed to record log for {phase_id}: {_arc_err}",
                    file=sys.stderr,
                )

        results = self._parse_results(result_parse_path)
        if not results:
            results = self._parse_results_from_transcript(transcript)
            if results:
                print(
                    f"[W{worker_id}] Batch {batch_index}: recovered "
                    f"{len(results)} result(s) from TUI transcript",
                    file=sys.stderr,
                )

        if not directory_mode:
            result_parse_path.unlink(missing_ok=True)

        return results

    # -- parsing --------------------------------------------------------

    def _parse_results_from_transcript(self, transcript: str) -> list[dict[str, Any]]:
        """Fallback: pull ```json fenced blocks out of the (already
        ANSI-stripped) TUI transcript. Mirrors
        ``ClaudeRunner._parse_results_from_log`` for the pty transport."""

        if not transcript:
            return []
        results: list[dict[str, Any]] = []
        for block in re.findall(r"```json\s*(.*?)```", transcript, re.DOTALL):
            try:
                data = json.loads(block.strip())
            except json.JSONDecodeError:
                continue
            normalized = self._normalize_result_data(data)
            results.extend(self._validate_result_item(item) for item in normalized)
        return results
