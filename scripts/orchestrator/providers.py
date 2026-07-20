"""Property provider and verification backend plugin interfaces for the SPECA pipeline.

Phase 01e ("Property Generation") historically used a single method: a Claude CLI
prompt path. This module makes both property generation and a post-04 verification
step pluggable behind small, explicit interfaces so alternative backends (Lean 4
formal verification, dataset ingestion, prior-output reuse, Kurtosis E2E repro)
can be swapped in without touching the async orchestration core.

The default provider (``prompt``) and default backend (``none``) preserve the
existing behavior exactly.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

class PropertyProviderName(str, Enum):
    """Recognised property-generation provider names."""
    PROMPT = "prompt"      # default — existing Claude CLI prompt path
    LEAN = "lean"          # Lean 4 FV via speca-lean4-plugin (external)
    DATASET = "dataset"    # ingest from HuggingFace or GitHub release URL
    EXISTING = "existing"  # load a previously-generated 01e output file


class VerificationBackendName(str, Enum):
    """Recognised post-04 verification backend names."""
    NONE = "none"          # default — no post-04 verification
    KURTOSIS = "kurtosis"  # E2E via NyxFoundation/kurtosis-harness (external)


class SearchBackendName(str, Enum):
    """Recognised external-search backend names for Phase 05 (finding critique)."""
    WEBSEARCH = "websearch"  # default — Claude Code built-in WebSearch/WebFetch tools
    NONE = "none"            # degraded mode — critique runs on internal evidence only


# ---------------------------------------------------------------------------
# Property provider interface + implementations
# ---------------------------------------------------------------------------

@runtime_checkable
class PropertyProvider(Protocol):
    """Generates or loads a list of Property from 01b subgraphs."""

    def generate(
        self,
        subgraphs: list[dict],         # raw 01b SpecSubGraphs dicts
        bug_bounty_scope: dict,        # contents of BUG_BOUNTY_SCOPE.json
        source: str | None = None,     # URL (for DATASET/LEAN) or path (for EXISTING)
    ) -> list[dict]:                   # list of Property-compatible dicts
        ...


class PromptPropertyProvider:
    """The current default provider.

    Property generation for the ``prompt`` path is performed by the Claude CLI
    runner inside the orchestrator, not by this object. This class exists so the
    :class:`PropertyProvider` interface is satisfied and callers/tests can assert
    it is selected when ``provider="prompt"``.
    """

    def generate(
        self,
        subgraphs: list[dict],
        bug_bounty_scope: dict,
        source: str | None = None,
    ) -> list[dict]:
        raise NotImplementedError(
            "PromptPropertyProvider delegates to the Claude CLI runner; "
            "call generate() is not used in the prompt path."
        )


class LeanPropertyProvider:
    """Lean 4 formal-verification provider (external plugin).

    ``generate()`` subprocess-invokes the plugin's CLI contract
    (speca-lean4-plugin README, "CLI contract"):

        speca-lean4 emit-01e --scope BUG_BOUNTY_SCOPE.json
                             [--subgraphs 01b_subgraphs.json]
                             (--health-json health.json | --run-lean)
                             --out 01e_PARTIAL_lean.json

    and returns the emitted ``properties`` list (01e schema; Lean provenance
    fields like ``lean_status`` are additive extras, per speca#88's contract).

    Plugin resolution (version-pinned per issue #87):

    1. ``SPECA_LEAN4_PLUGIN_DIR`` — path to an existing plugin checkout.
    2. Otherwise the pinned tag is auto-cloned into
       ``<output_root>/.plugins/speca-lean4-plugin-<version>`` (requires git
       and network; set ``SPECA_LEAN4_AUTO_CLONE=0`` to forbid).

    The CLI is invoked as ``python -m speca_lean4.cli`` from the checkout
    (with ``<checkout>/src`` on PYTHONPATH) rather than via a pip console
    script: the plugin resolves its repo-root data files (theorem_map.json,
    data/*.json) relative to its source tree, which a wheel install would not
    carry.

    Proof-health source (Stage B of the plugin pipeline), in priority order:

    - ``source`` argument (wired from ``--dataset-source``) or the
      ``SPECA_LEAN4_HEALTH_JSON`` env var — path to a precomputed
      ``lake exe speca-export`` proof-health JSON (the plugin's CI artifact).
    - ``SPECA_LEAN4_RUN_LEAN=1`` — run the Lean exporter now (requires the
      Lean toolchain; heavy — gated off by default).
    - Neither — the plugin emits every property ``lean_status=unknown`` with
      a warning (honest dry-mapping mode; nothing is claimed proved).
    """

    plugin_ref = "NyxFoundation/speca-lean4-plugin"
    # Version pin for the external plugin boundary (issue #87 requires plugin
    # boundaries to be version-pinned). Pinned to the plugin's F1 release
    # (speca-lean4-plugin#8).
    plugin_version: str | None = "v0.1.0"

    subprocess_timeout_s = 1800

    @staticmethod
    def _is_plugin_checkout(path: Path) -> bool:
        return (path / "src" / "speca_lean4").is_dir()

    def _verify_plugin_version(self, plugin_dir: Path) -> None:
        """Enforce that *plugin_dir* is actually at the pinned version.

        The shape check (src/speca_lean4 exists) says nothing about *which*
        version the checkout is, so a stale SPECA_LEAN4_PLUGIN_DIR or cache
        would silently test the wrong code (issue #87: pins must be enforced,
        not just declared). Policy:

        - a tag at HEAD matching ``plugin_version`` -> verified;
        - tags at HEAD but none matching -> hard error (set
          ``SPECA_LEAN4_ALLOW_VERSION_MISMATCH=1`` to downgrade to a warning,
          e.g. for local plugin development);
        - no tag readable (not a git checkout, a branch clone without tags,
          git missing/timing out, or *plugin_dir* is a plain directory nested
          inside some OTHER repo — ``git -C`` would silently report the outer
          repo's tags, so containment is checked first) -> loud warning, not
          an error — we cannot verify, and honest "unverified" beats a false
          "verified".

        Scope note: verification is commit-level (which commit the tag points
        at), not content-level — a dirty working tree on the pinned tag still
        passes. That is the intended threat model: the pin guards against
        *stale/wrong-version* checkouts (the failure mode a cache or env var
        actually produces), not against deliberate local modification, which
        an attacker with filesystem access could defeat anyway.
        """
        import os
        import subprocess
        import sys

        def _unverified(reason: str) -> None:
            print(
                f"warning: cannot verify {self.plugin_ref} checkout at "
                f"{plugin_dir} is {self.plugin_version} ({reason}); "
                "proceeding unverified.",
                file=sys.stderr,
            )

        if not self.plugin_version:
            return
        try:
            top = subprocess.run(
                ["git", "-C", str(plugin_dir), "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=60,
            )
            if top.returncode != 0:
                _unverified("not a git checkout")
                return
            toplevel = Path(top.stdout.strip())
            if toplevel.resolve() != plugin_dir.resolve():
                # git -C resolved to an enclosing repository, not the plugin
                # dir itself; its tags would describe the wrong repo.
                _unverified(
                    f"directory is not a git toplevel; git resolves to {toplevel}"
                )
                return
            proc = subprocess.run(
                ["git", "-C", str(plugin_dir), "tag", "--points-at", "HEAD"],
                capture_output=True, text=True, timeout=60,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            _unverified(f"git unavailable: {exc}")
            return
        tags = [t.strip() for t in proc.stdout.splitlines() if t.strip()]
        if proc.returncode != 0 or not tags:
            _unverified("no tag readable at HEAD")
            return
        if self.plugin_version not in tags:
            msg = (
                f"{self.plugin_ref} checkout at {plugin_dir} is at "
                f"{'/'.join(tags)}, but the provider pins "
                f"{self.plugin_version}."
            )
            if os.environ.get("SPECA_LEAN4_ALLOW_VERSION_MISMATCH") == "1":
                print(
                    f"warning: {msg} Proceeding because "
                    "SPECA_LEAN4_ALLOW_VERSION_MISMATCH=1.",
                    file=sys.stderr,
                )
                return
            raise RuntimeError(
                f"{msg} Use a {self.plugin_version} checkout, or set "
                "SPECA_LEAN4_ALLOW_VERSION_MISMATCH=1 to override "
                "(local plugin development only)."
            )

    def _resolve_plugin_dir(self) -> Path:
        """Locate (or clone) the pinned plugin checkout; return its root."""
        import os
        import shutil
        import subprocess

        env_dir = os.environ.get("SPECA_LEAN4_PLUGIN_DIR")
        if env_dir:
            plugin_dir = Path(env_dir)
            if not self._is_plugin_checkout(plugin_dir):
                raise FileNotFoundError(
                    f"SPECA_LEAN4_PLUGIN_DIR={env_dir} is not a "
                    f"{self.plugin_ref} checkout (missing src/speca_lean4)."
                )
            self._verify_plugin_version(plugin_dir)
            return plugin_dir

        from .paths import get_output_root

        cache_dir = (
            get_output_root() / ".plugins"
            / f"speca-lean4-plugin-{self.plugin_version or 'main'}"
        )
        if self._is_plugin_checkout(cache_dir):
            self._verify_plugin_version(cache_dir)
            return cache_dir
        if cache_dir.exists():
            # Leftover from an interrupted clone: a half-populated dir would
            # make the re-clone fail with a misleading "destination path
            # already exists" error. Remove it and clone fresh.
            shutil.rmtree(cache_dir)

        if os.environ.get("SPECA_LEAN4_AUTO_CLONE", "1") == "0":
            raise RuntimeError(
                f"lean provider requires {self.plugin_ref}@{self.plugin_version} "
                "and SPECA_LEAN4_AUTO_CLONE=0 forbids cloning it. Set "
                "SPECA_LEAN4_PLUGIN_DIR to an existing checkout."
            )

        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        clone_url = f"https://github.com/{self.plugin_ref}.git"
        # Clone into a temp sibling, then rename into place, so an
        # interrupted clone never leaves a half-populated cache_dir behind.
        tmp_dir = cache_dir.parent / f"{cache_dir.name}.tmp-{os.getpid()}"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        cmd = ["git", "clone", "--depth", "1"]
        if self.plugin_version:
            cmd += ["--branch", self.plugin_version]
        cmd += [clone_url, str(tmp_dir)]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.subprocess_timeout_s
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"failed to clone {self.plugin_ref}@{self.plugin_version} "
                    f"(rc={proc.returncode}): {proc.stderr.strip()}\n"
                    "Set SPECA_LEAN4_PLUGIN_DIR to an existing checkout instead."
                )
            try:
                tmp_dir.rename(cache_dir)
            except OSError:
                # A concurrent resolver may have renamed its own clone into
                # place first ("Directory not empty" / "file exists"). If the
                # winner left a valid checkout, use it; otherwise re-raise.
                if not self._is_plugin_checkout(cache_dir):
                    raise
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
        self._verify_plugin_version(cache_dir)
        return cache_dir

    def generate(
        self,
        subgraphs: list[dict],
        bug_bounty_scope: dict,
        source: str | None = None,
    ) -> list[dict]:
        import os
        import subprocess
        import sys
        import tempfile

        plugin_dir = self._resolve_plugin_dir()

        with tempfile.TemporaryDirectory(prefix="speca-lean4-") as td:
            tmp = Path(td)
            scope_path = tmp / "BUG_BOUNTY_SCOPE.json"
            scope_path.write_text(
                json.dumps(bug_bounty_scope, ensure_ascii=False), encoding="utf-8"
            )
            out_path = tmp / "01e_PARTIAL_lean.json"

            cmd = [
                sys.executable, "-m", "speca_lean4.cli", "emit-01e",
                "--scope", str(scope_path),
                "--out", str(out_path),
            ]

            if subgraphs:
                # The CLI globs 01b files; a JSON *list* file is consumed as a
                # list of subgraph dicts (covers resolution input).
                subgraphs_path = tmp / "01b_subgraphs.json"
                subgraphs_path.write_text(
                    json.dumps(subgraphs, ensure_ascii=False), encoding="utf-8"
                )
                cmd += ["--subgraphs", str(subgraphs_path)]

            health_json = source or os.environ.get("SPECA_LEAN4_HEALTH_JSON")
            if health_json:
                health_path = Path(health_json)
                if not health_path.exists():
                    raise FileNotFoundError(
                        f"lean provider proof-health JSON not found: {health_json}"
                    )
                cmd += ["--health-json", str(health_path)]
            elif os.environ.get("SPECA_LEAN4_RUN_LEAN") == "1":
                cmd += ["--run-lean"]

            env = dict(os.environ)
            src_dir = str(plugin_dir / "src")
            existing = env.get("PYTHONPATH")
            env["PYTHONPATH"] = (
                src_dir + os.pathsep + existing if existing else src_dir
            )

            proc = subprocess.run(
                cmd,
                cwd=str(plugin_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.subprocess_timeout_s,
            )
            # Surface the plugin's warnings (unknown lean_status, B5
            # type-consistency flags) instead of swallowing them.
            if proc.stderr:
                print(proc.stderr, file=sys.stderr, end="")
            if proc.returncode != 0:
                raise RuntimeError(
                    f"speca-lean4 emit-01e failed (rc={proc.returncode}): "
                    f"{proc.stderr.strip() or proc.stdout.strip()}"
                )
            doc = json.loads(out_path.read_text(encoding="utf-8"))

        properties = doc.get("properties", [])
        if not properties:
            # An empty emission means downstream phases have nothing to audit;
            # the phase would otherwise still log "completed" and exit 0.
            print(
                "warning: lean provider returned zero properties — check the "
                "theorem map / scope inputs and the plugin output above.",
                file=sys.stderr,
            )
        print(
            f"lean provider: {len(properties)} properties from "
            f"{self.plugin_ref}@{self.plugin_version}"
        )
        return properties


class DatasetPropertyProvider:
    """Ingest properties from a HuggingFace or GitHub release URL."""

    accepted_url_prefixes = ("https://huggingface.co/", "https://github.com/")

    def generate(
        self,
        subgraphs: list[dict],
        bug_bounty_scope: dict,
        source: str | None = None,
    ) -> list[dict]:
        raise NotImplementedError(
            "dataset ingestion not yet implemented; pass a HuggingFace or "
            "GitHub release URL via --dataset-source."
        )


class ExistingPropertyProvider:
    """Load properties from a previously-generated ``01e_PARTIAL_*.json`` file."""

    def generate(
        self,
        subgraphs: list[dict],
        bug_bounty_scope: dict,
        source: str | None = None,
    ) -> list[dict]:
        if source is None:
            raise FileNotFoundError(
                "ExistingPropertyProvider requires a source path to an "
                "01e_PARTIAL_*.json file, but source was None."
            )
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(
                f"ExistingPropertyProvider source file not found: {source}"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("properties", [])


# ---------------------------------------------------------------------------
# Refinement hook
# ---------------------------------------------------------------------------

def run_refinement_pass(properties: list[dict]) -> list[dict]:
    """No-op refinement hook. Opt-in via --enable-refinement / config.refinement_pass_enabled.

    Future implementations will dedup, tighten assertions, and raise coverage.
    """
    return properties


# ---------------------------------------------------------------------------
# Verification backend interface + implementations
# ---------------------------------------------------------------------------

@runtime_checkable
class VerificationBackend(Protocol):
    """Runs post-04 verification on confirmed findings."""

    def verify(
        self,
        confirmed_findings: list[dict],   # surviving 04_PARTIAL items
        target_info: dict,                # contents of TARGET_INFO.json
    ) -> list[dict]:                      # list of VerificationRecord-compatible dicts
        ...


class NullVerificationBackend:
    """Default backend — performs no verification."""

    def verify(
        self,
        confirmed_findings: list[dict],
        target_info: dict,
    ) -> list[dict]:
        return []


class KurtosisVerificationBackend:
    """E2E reproduction backend via the Kurtosis harness (external plugin)."""

    plugin_ref = "NyxFoundation/kurtosis-harness"
    # Version pin for the external plugin boundary (issue #87 requires plugin
    # boundaries to be version-pinned). No tagged release exists yet, so this
    # pins the current default-branch HEAD; #92 bumps it to a tag when published.
    plugin_version: str | None = "f92be45cfecb35700ab8e67800151260ac3c5f07"

    def verify(
        self,
        confirmed_findings: list[dict],
        target_info: dict,
    ) -> list[dict]:
        pin = f"@{self.plugin_version}" if self.plugin_version else ""
        raise NotImplementedError(
            f"kurtosis backend requires {self.plugin_ref}{pin}; "
            "install and configure it first."
        )


# ---------------------------------------------------------------------------
# Search backend interface + implementations (Phase 05 — finding critique)
# ---------------------------------------------------------------------------

@runtime_checkable
class SearchBackend(Protocol):
    """Supplies external-search capability to the Phase 05 critique worker.

    The critique worker is a Claude CLI session; external search is delivered
    to it as *tools* (via the phase's ``tools_filter``), not as pre-fetched
    data. A backend therefore declares:

    - ``worker_tools()`` — the tool names to append to the phase tool filter.
    - ``provenance()`` — the ``evidence_provenance`` value the worker must
      record when this backend is active, so the output schema always carries
      an honest statement of where the evidence came from.
    """

    name: str

    def worker_tools(self) -> list[str]:
        ...

    def provenance(self) -> str:
        ...


class WebSearchBackend:
    """Default backend — Claude Code built-in WebSearch/WebFetch tools."""

    name = SearchBackendName.WEBSEARCH.value

    def worker_tools(self) -> list[str]:
        return ["WebSearch", "WebFetch"]

    def provenance(self) -> str:
        return "external+internal"


class NullSearchBackend:
    """Degraded mode — no search backend configured.

    The critique still runs (term extraction, re-read, code re-verification)
    but on internal evidence only. No search tools are exposed to the worker,
    and the output must record ``evidence_provenance = internal-only`` with
    no external citations (enforced by ``schemas.CritiquedItem``).
    """

    name = SearchBackendName.NONE.value

    def worker_tools(self) -> list[str]:
        return []

    def provenance(self) -> str:
        return "internal-only"


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

_PROVIDERS = {
    PropertyProviderName.PROMPT: PromptPropertyProvider,
    PropertyProviderName.LEAN: LeanPropertyProvider,
    PropertyProviderName.DATASET: DatasetPropertyProvider,
    PropertyProviderName.EXISTING: ExistingPropertyProvider,
}

_BACKENDS = {
    VerificationBackendName.NONE: NullVerificationBackend,
    VerificationBackendName.KURTOSIS: KurtosisVerificationBackend,
}


def resolve_provider(name: str | PropertyProviderName) -> PropertyProvider:
    """Return the PropertyProvider instance for *name*."""
    try:
        key = PropertyProviderName(name)
    except ValueError as exc:
        valid = ", ".join(n.value for n in PropertyProviderName)
        raise ValueError(
            f"Unknown property provider: {name!r}. Valid providers: {valid}."
        ) from exc
    return _PROVIDERS[key]()


def resolve_verification_backend(name: str | VerificationBackendName) -> VerificationBackend:
    """Return the VerificationBackend instance for *name*."""
    try:
        key = VerificationBackendName(name)
    except ValueError as exc:
        valid = ", ".join(n.value for n in VerificationBackendName)
        raise ValueError(
            f"Unknown verification backend: {name!r}. Valid backends: {valid}."
        ) from exc
    return _BACKENDS[key]()


_SEARCH_BACKENDS = {
    SearchBackendName.WEBSEARCH: WebSearchBackend,
    SearchBackendName.NONE: NullSearchBackend,
}


def resolve_search_backend(name: str | SearchBackendName) -> SearchBackend:
    """Return the SearchBackend instance for *name*."""
    try:
        key = SearchBackendName(name)
    except ValueError as exc:
        valid = ", ".join(n.value for n in SearchBackendName)
        raise ValueError(
            f"Unknown search backend: {name!r}. Valid backends: {valid}."
        ) from exc
    return _SEARCH_BACKENDS[key]()
