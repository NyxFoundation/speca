"""Tests for pluggable property providers and verification backends (issue #87)."""
import pytest
from scripts.orchestrator.providers import (
    PropertyProviderName, VerificationBackendName,
    PromptPropertyProvider, LeanPropertyProvider,
    DatasetPropertyProvider, ExistingPropertyProvider,
    NullVerificationBackend, KurtosisVerificationBackend,
    resolve_provider, resolve_verification_backend,
    run_refinement_pass,
)
from scripts.orchestrator.schemas import VerificationRecord, PropertyProviderName as SchemasProviderName  # same object — tested below
from scripts.orchestrator.config import PhaseConfig, PHASE_CONFIGS
from scripts.orchestrator.factory import create_orchestrator
from pathlib import Path
import json, tempfile


def test_provider_name_enum_values():
    values = {m.value for m in PropertyProviderName}
    assert values == {"prompt", "lean", "dataset", "existing"}


def test_verification_backend_name_enum_values():
    values = {m.value for m in VerificationBackendName}
    assert "none" in values
    assert "kurtosis" in values


def test_resolve_provider_prompt():
    assert isinstance(resolve_provider("prompt"), PromptPropertyProvider)


def test_resolve_provider_lean():
    assert isinstance(resolve_provider("lean"), LeanPropertyProvider)


def test_resolve_provider_dataset():
    assert isinstance(resolve_provider("dataset"), DatasetPropertyProvider)


def test_resolve_provider_existing():
    assert isinstance(resolve_provider("existing"), ExistingPropertyProvider)


def test_resolve_provider_unknown():
    with pytest.raises(ValueError):
        resolve_provider("bogus")


def test_resolve_verification_backend_none():
    assert isinstance(resolve_verification_backend("none"), NullVerificationBackend)


def test_resolve_verification_backend_kurtosis():
    assert isinstance(resolve_verification_backend("kurtosis"), KurtosisVerificationBackend)


def test_resolve_verification_backend_unknown():
    with pytest.raises(ValueError):
        resolve_verification_backend("bogus")


def test_lean_provider_raises_not_implemented():
    provider = LeanPropertyProvider()
    assert provider.plugin_ref == "NyxFoundation/speca-lean4-plugin"
    with pytest.raises(NotImplementedError):
        provider.generate([], {})


def test_kurtosis_backend_raises_not_implemented():
    backend = KurtosisVerificationBackend()
    assert backend.plugin_ref == "NyxFoundation/kurtosis-harness"
    with pytest.raises(NotImplementedError):
        backend.verify([], {})


def test_null_backend_returns_empty():
    assert NullVerificationBackend().verify([], {}) == []


def test_prompt_provider_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        PromptPropertyProvider().generate([], {})


def test_existing_provider_loads_file():
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td) / "01e_PARTIAL_test.json"
        tmp_path.write_text(
            json.dumps({"properties": [{"property_id": "P-001", "text": "test"}]}),
            encoding="utf-8",
        )
        result = ExistingPropertyProvider().generate([], {}, source=str(tmp_path))
    assert len(result) == 1
    assert result[0]["property_id"] == "P-001"


def test_existing_provider_no_source_raises():
    with pytest.raises(FileNotFoundError):
        ExistingPropertyProvider().generate([], {}, source=None)


def test_refinement_pass_is_noop():
    assert run_refinement_pass([{"a": 1}]) == [{"a": 1}]


def test_verification_record_schema():
    rec = VerificationRecord(property_id="P-001", verdict="reproduced", harness="kurtosis")
    assert rec.property_id == "P-001"
    assert rec.verdict == "reproduced"
    assert rec.harness == "kurtosis"


def test_phase_config_has_provider_fields():
    cfg = PhaseConfig(
        phase_id="x", name="x", description="x",
        skill_path=Path(""), prompt_path=Path(""),
        queue_pattern="", output_pattern="", mcp_servers=[],
    )
    assert cfg.property_provider == "prompt"
    assert cfg.verification_backend == "none"
    assert cfg.refinement_pass_enabled is False


def test_01e_config_default_provider():
    assert PHASE_CONFIGS["01e"].property_provider == "prompt"


def test_create_orchestrator_with_provider_override():
    # Override must land on the orchestrator's own config copy, not the global singleton.
    orch = create_orchestrator("01e", property_provider="lean")
    assert orch.config.property_provider == "lean"
    assert PHASE_CONFIGS["01e"].property_provider == "prompt"  # global unchanged


def test_create_orchestrator_default_provider_unchanged():
    orch = create_orchestrator("01e", property_provider="prompt")
    assert orch.config.property_provider == "prompt"


def test_refinement_disabled_by_default():
    assert PHASE_CONFIGS["01e"].refinement_pass_enabled is False


def test_dataset_provider_accepts_hf_url():
    assert "https://huggingface.co/" in DatasetPropertyProvider.accepted_url_prefixes


def test_lean_provider_plugin_ref():
    assert LeanPropertyProvider.plugin_ref == "NyxFoundation/speca-lean4-plugin"


def test_kurtosis_backend_plugin_ref():
    assert KurtosisVerificationBackend.plugin_ref == "NyxFoundation/kurtosis-harness"


def test_schemas_and_providers_share_enum_identity():
    # schemas.PropertyProviderName must be the same object as providers.PropertyProviderName
    # (no duplicate definitions).
    assert SchemasProviderName is PropertyProviderName


def test_create_orchestrator_verification_override_doesnt_mutate_global():
    orch = create_orchestrator("04", verification_backend="kurtosis")
    assert orch.config.verification_backend == "kurtosis"
    assert PHASE_CONFIGS["04"].verification_backend == "none"  # global unchanged
