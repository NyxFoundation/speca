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
    """Lean 4 formal-verification provider (external plugin)."""

    plugin_ref = "NyxFoundation/speca-lean4-plugin"
    # Version pin for the external plugin boundary (issue #87 requires plugin
    # boundaries to be version-pinned). The plugin repo has no commits/tags yet,
    # so the pin is deferred to #88 when it publishes a taggable release.
    plugin_version: str | None = None

    def generate(
        self,
        subgraphs: list[dict],
        bug_bounty_scope: dict,
        source: str | None = None,
    ) -> list[dict]:
        pin = f"@{self.plugin_version}" if self.plugin_version else " (version pin TBD by #88)"
        raise NotImplementedError(
            f"lean provider requires {self.plugin_ref}{pin}; "
            "install and configure it first."
        )


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
