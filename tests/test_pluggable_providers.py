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
from scripts.orchestrator.schemas import Phase01ePartial, VerificationRecord, PropertyProviderName as SchemasProviderName  # same object — tested below
from scripts.orchestrator.config import PhaseConfig, PHASE_CONFIGS
from scripts.orchestrator.factory import create_orchestrator
from pathlib import Path
import hashlib, json, os, tempfile


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


def test_lean_provider_bad_plugin_dir_raises(monkeypatch, tmp_path):
    # An explicitly-configured plugin dir that is not a checkout must fail
    # loudly, before any subprocess or network activity.
    provider = LeanPropertyProvider()
    assert provider.plugin_ref == "NyxFoundation/speca-lean4-plugin"
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(tmp_path / "not-a-checkout"))
    with pytest.raises(FileNotFoundError):
        provider.generate([], {})


def test_lean_provider_auto_clone_forbidden_raises(monkeypatch, tmp_path):
    # With no checkout configured and auto-clone forbidden, resolution must
    # fail with guidance — never touch the network.
    monkeypatch.delenv("SPECA_LEAN4_PLUGIN_DIR", raising=False)
    monkeypatch.setenv("SPECA_LEAN4_AUTO_CLONE", "0")
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="SPECA_LEAN4_PLUGIN_DIR"):
        LeanPropertyProvider().generate([], {})


def _fake_plugin_checkout(root: Path) -> Path:
    plugin_dir = root / "speca-lean4-plugin"
    (plugin_dir / "src" / "speca_lean4").mkdir(parents=True)
    return plugin_dir


def _mk_fake_run(subprocess_mod, emitted, captured=None, git_tags="v0.1.0\n",
                 git_toplevel=None):
    """Fake subprocess.run: answers the `git rev-parse --show-toplevel`
    containment probe (with *git_toplevel*, defaulting to the probed dir
    itself, i.e. containment OK), the `git tag --points-at HEAD` version
    probe (with *git_tags*), and the CLI invocation by writing *emitted* to
    the --out file."""
    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            if captured is not None:
                captured.setdefault("git_cmds", []).append(cmd)
            if "rev-parse" in cmd:
                top = git_toplevel if git_toplevel is not None else cmd[2]
                return subprocess_mod.CompletedProcess(cmd, 0, stdout=top + "\n", stderr="")
            return subprocess_mod.CompletedProcess(cmd, 0, stdout=git_tags, stderr="")
        if captured is not None:
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            captured["env"] = kwargs.get("env")
        Path(cmd[cmd.index("--out") + 1]).write_text(
            json.dumps({"phase": "01e", "provider": "lean", "properties": emitted}),
            encoding="utf-8",
        )
        return subprocess_mod.CompletedProcess(cmd, 0, stdout="", stderr="")
    return fake_run


def test_lean_provider_invokes_plugin_cli(monkeypatch, tmp_path):
    """generate() must shell out to `speca-lean4 emit-kurtosis` (the default
    since speca#88 Task 5 — same 01e pipeline plus fixture scaffolds) per the
    CLI contract and return the emitted `properties` list."""
    import subprocess as subprocess_mod
    import sys as sys_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_KURTOSIS_FIXTURES", raising=False)

    emitted = [
        {"property_id": "PROP-lean-001", "text": "t", "severity": "HIGH",
         "lean_status": "proved"},
        {"property_id": "PROP-lean-002", "text": "u", "severity": "MEDIUM",
         "lean_status": "unknown"},
    ]
    captured = {}
    monkeypatch.setattr(
        subprocess_mod, "run", _mk_fake_run(subprocess_mod, emitted, captured)
    )

    subgraphs = [{"source_url": "https://spec.example/x", "subgraphs": []}]
    scope = {"program_name": "Test Bounty"}
    result = LeanPropertyProvider().generate(subgraphs, scope, source=None)

    assert result == emitted
    cmd = captured["cmd"]
    assert cmd[0] == sys_mod.executable
    assert cmd[1:4] == ["-m", "speca_lean4.cli", "emit-kurtosis"]
    assert "--scope" in cmd and "--out" in cmd
    # fixtures go under the speca output root, passed as an absolute path
    # (the plugin subprocess runs with cwd = the plugin checkout)
    fixtures_dir = Path(cmd[cmd.index("--fixtures-dir") + 1])
    assert fixtures_dir.is_absolute()
    assert fixtures_dir == (tmp_path / "outputs" / "kurtosis").resolve()
    # subgraphs were materialized to a temp file and passed through
    assert "--subgraphs" in cmd
    # no health source configured -> honest dry-mapping mode (no --health-json,
    # no --run-lean)
    assert "--health-json" not in cmd
    assert "--run-lean" not in cmd
    # runs from the checkout with its src/ importable
    assert captured["cwd"] == str(plugin_dir)
    assert str(plugin_dir / "src") in captured["env"]["PYTHONPATH"]
    # the scope dict was round-tripped to the file handed to the CLI
    scope_file = Path(cmd[cmd.index("--scope") + 1])
    # (the tempdir is gone after generate() returns; path shape is enough)
    assert scope_file.name == "BUG_BOUNTY_SCOPE.json"


def test_lean_provider_fixture_optout_falls_back_to_emit_01e(monkeypatch, tmp_path):
    """SPECA_LEAN4_KURTOSIS_FIXTURES=0 must restore the plain emit-01e call:
    no --fixtures-dir, no kurtosis_test rewriting, nothing written."""
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("SPECA_LEAN4_KURTOSIS_FIXTURES", "0")
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)

    captured = {}
    monkeypatch.setattr(
        subprocess_mod, "run",
        _mk_fake_run(subprocess_mod, [{"property_id": "P-1"}], captured),
    )
    result = LeanPropertyProvider().generate([], {})
    assert result == [{"property_id": "P-1"}]
    cmd = captured["cmd"]
    assert cmd[1:4] == ["-m", "speca_lean4.cli", "emit-01e"]
    assert "--fixtures-dir" not in cmd
    assert not (tmp_path / "outputs" / "kurtosis").exists()


def _mk_fake_kurtosis_run(subprocess_mod, captured=None, *, fixture_props,
                          write_fixture_files=True, record_path=None):
    """Fake subprocess.run emulating `emit-kurtosis`: for each entry in
    *fixture_props* (property dict, linked flag) it writes the fixture
    scaffold under the --fixtures-dir the provider passed (unless
    *write_fixture_files* is False) and records the kurtosis_test path in the
    --out JSON, exactly like the plugin's `_record_path` (absolute POSIX when
    outside the plugin cwd). *record_path* overrides the recorded path for
    the error-path tests."""
    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            return subprocess_mod.CompletedProcess(cmd, 0, stdout="v0.1.0\n" if "tag" in cmd else cmd[2] + "\n", stderr="")
        if captured is not None:
            captured["cmd"] = cmd
        fixtures_dir = Path(cmd[cmd.index("--fixtures-dir") + 1])
        emitted = []
        for prop, linked in fixture_props:
            prop = dict(prop)
            if linked:
                fdir = fixtures_dir / (prop.get("label") or "unlabeled").replace(":", "--") / prop["property_id"]
                fp = fdir / "assertion.scaffold.json"
                if write_fixture_files:
                    fdir.mkdir(parents=True, exist_ok=True)
                    (fdir / "devnet.scaffold.json").write_text(
                        json.dumps({"scaffold": True}), encoding="utf-8"
                    )
                    fp.write_text(
                        json.dumps({"scaffold": True, "handoff": {"verdict": None}}),
                        encoding="utf-8",
                    )
                prop["kurtosis_test"] = (
                    record_path if record_path is not None else fp.resolve().as_posix()
                )
            emitted.append(prop)
        Path(cmd[cmd.index("--out") + 1]).write_text(
            json.dumps({"phase": "01e", "provider": "lean", "properties": emitted}),
            encoding="utf-8",
        )
        return subprocess_mod.CompletedProcess(cmd, 0, stdout="", stderr="")
    return fake_run


def test_lean_provider_rebases_kurtosis_paths(monkeypatch, tmp_path):
    """Task 5 contract: kurtosis_test is rebased onto the configured output
    root (POSIX form), the fixture file really exists there, and properties
    without a checker keep kurtosis_test null/absent — never fabricated."""
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    out_root = tmp_path / "outputs"
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(out_root))
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_KURTOSIS_FIXTURES", raising=False)

    fixture_props = [
        ({"property_id": "PROP-l-001", "label": "beacon-chain:slashing",
          "lean_status": "proved"}, True),
        ({"property_id": "PROP-l-002", "label": "beacon-chain:slashing",
          "lean_status": "proved"}, False),  # no Executable checker
    ]
    monkeypatch.setattr(
        subprocess_mod, "run",
        _mk_fake_kurtosis_run(subprocess_mod, fixture_props=fixture_props),
    )
    result = LeanPropertyProvider().generate([], {})

    linked = result[0]
    expected = (
        out_root / "kurtosis" / "beacon-chain--slashing" / "PROP-l-001"
        / "assertion.scaffold.json"
    )
    assert linked["kurtosis_test"] == expected.as_posix()
    assert "\\" not in linked["kurtosis_test"]  # POSIX form on every platform
    assert expected.is_file()
    # honesty: the checkerless property was not given a fixture reference
    assert result[1].get("kurtosis_test") is None


def test_lean_provider_missing_fixture_file_raises(monkeypatch, tmp_path):
    """A kurtosis_test path whose fixture was never written must fail loud —
    the provider refuses to emit references to fixtures that don't exist."""
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.delenv("SPECA_LEAN4_KURTOSIS_FIXTURES", raising=False)

    fixture_props = [({"property_id": "PROP-l-001", "label": "x"}, True)]
    monkeypatch.setattr(
        subprocess_mod, "run",
        _mk_fake_kurtosis_run(
            subprocess_mod, fixture_props=fixture_props, write_fixture_files=False
        ),
    )
    with pytest.raises(RuntimeError, match="missing on disk"):
        LeanPropertyProvider().generate([], {})


def test_lean_provider_fixture_path_outside_dir_raises(monkeypatch, tmp_path):
    """A recorded kurtosis_test outside the requested fixtures dir must be
    rejected, not silently rebased or passed through."""
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.delenv("SPECA_LEAN4_KURTOSIS_FIXTURES", raising=False)

    rogue = (tmp_path / "elsewhere" / "assertion.scaffold.json").resolve()
    fixture_props = [({"property_id": "PROP-l-001", "label": "x"}, True)]
    monkeypatch.setattr(
        subprocess_mod, "run",
        _mk_fake_kurtosis_run(
            subprocess_mod, fixture_props=fixture_props,
            record_path=rogue.as_posix(),
        ),
    )
    with pytest.raises(RuntimeError, match="outside the requested"):
        LeanPropertyProvider().generate([], {})


def test_lean_provider_passes_health_json_source(monkeypatch, tmp_path):
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)
    health = tmp_path / "health.json"
    health.write_text("{}", encoding="utf-8")

    captured = {}
    monkeypatch.setattr(
        subprocess_mod, "run", _mk_fake_run(subprocess_mod, [], captured)
    )

    LeanPropertyProvider().generate([], {}, source=str(health))
    cmd = captured["cmd"]
    assert cmd[cmd.index("--health-json") + 1] == str(health)


def test_lean_provider_missing_health_json_raises(monkeypatch, tmp_path):
    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    with pytest.raises(FileNotFoundError, match="proof-health"):
        LeanPropertyProvider().generate([], {}, source=str(tmp_path / "no.json"))


def test_lean_provider_nonzero_exit_raises(monkeypatch, tmp_path):
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))

    def fake_run(cmd, **kwargs):
        return subprocess_mod.CompletedProcess(cmd, 2, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess_mod, "run", fake_run)
    with pytest.raises(RuntimeError, match="boom"):
        LeanPropertyProvider().generate([], {})


def test_lean_provider_version_mismatch_raises(monkeypatch, tmp_path):
    """A checkout verifiably at a different tag than plugin_version must be
    rejected before the CLI is invoked (issue #87: pins are enforced, not
    just declared)."""
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.delenv("SPECA_LEAN4_ALLOW_VERSION_MISMATCH", raising=False)
    monkeypatch.setattr(
        subprocess_mod, "run",
        _mk_fake_run(subprocess_mod, [], git_tags="v0.0.9\n"),
    )
    with pytest.raises(RuntimeError, match=r"v0\.0\.9.*pins.*v0\.1\.0"):
        LeanPropertyProvider().generate([], {})


def test_lean_provider_version_mismatch_override(monkeypatch, tmp_path, capsys):
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.setenv("SPECA_LEAN4_ALLOW_VERSION_MISMATCH", "1")
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)
    monkeypatch.setattr(
        subprocess_mod, "run",
        _mk_fake_run(subprocess_mod, [{"property_id": "P-1"}], git_tags="v0.0.9\n"),
    )
    result = LeanPropertyProvider().generate([], {})
    assert result == [{"property_id": "P-1"}]
    assert "SPECA_LEAN4_ALLOW_VERSION_MISMATCH" in capsys.readouterr().err


def test_lean_provider_unverifiable_version_warns_not_fails(monkeypatch, tmp_path, capsys):
    """A checkout with no readable tag (e.g. a plain directory, or a branch
    clone) proceeds with a warning — unverified, never falsely verified."""
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)
    monkeypatch.setattr(
        subprocess_mod, "run",
        _mk_fake_run(subprocess_mod, [{"property_id": "P-1"}], git_tags=""),
    )
    result = LeanPropertyProvider().generate([], {})
    assert result == [{"property_id": "P-1"}]
    assert "cannot verify" in capsys.readouterr().err


def test_lean_provider_zero_properties_warns(monkeypatch, tmp_path, capsys):
    """An empty emission must be loudly flagged at runtime, not only by the
    CI verify step."""
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)
    monkeypatch.setattr(subprocess_mod, "run", _mk_fake_run(subprocess_mod, []))
    result = LeanPropertyProvider().generate([], {})
    assert result == []
    assert "zero properties" in capsys.readouterr().err


def test_lean_provider_nested_plain_dir_is_unverified(monkeypatch, tmp_path, capsys):
    """A plain (non-git) plugin dir nested inside another repository must NOT
    inherit the outer repo's tags: `git -C` resolves to the enclosing
    toplevel, so the probe is only trusted when the toplevel IS the plugin
    dir. Here the outer repo even carries a wrong tag — without the
    containment check this would hard-fail (or worse, falsely verify)."""
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)
    monkeypatch.setattr(
        subprocess_mod, "run",
        _mk_fake_run(subprocess_mod, [{"property_id": "P-1"}],
                     git_tags="v0.0.9\n", git_toplevel=str(tmp_path)),
    )
    result = LeanPropertyProvider().generate([], {})
    assert result == [{"property_id": "P-1"}]
    err = capsys.readouterr().err
    assert "cannot verify" in err and "not a git toplevel" in err


def test_lean_provider_git_unavailable_warns_not_fails(monkeypatch, tmp_path, capsys):
    """git missing from PATH (or hanging) must take the warn-unverified
    branch, not crash the provider."""
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)

    inner = _mk_fake_run(subprocess_mod, [{"property_id": "P-1"}])

    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            raise FileNotFoundError("No such file or directory: 'git'")
        return inner(cmd, **kwargs)

    monkeypatch.setattr(subprocess_mod, "run", fake_run)
    result = LeanPropertyProvider().generate([], {})
    assert result == [{"property_id": "P-1"}]
    assert "git unavailable" in capsys.readouterr().err


def test_lean_provider_probe_timeout_warns_not_fails(monkeypatch, tmp_path, capsys):
    import subprocess as subprocess_mod

    plugin_dir = _fake_plugin_checkout(tmp_path)
    monkeypatch.setenv("SPECA_LEAN4_PLUGIN_DIR", str(plugin_dir))
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)

    inner = _mk_fake_run(subprocess_mod, [{"property_id": "P-1"}])

    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            raise subprocess_mod.TimeoutExpired(cmd, 60)
        return inner(cmd, **kwargs)

    monkeypatch.setattr(subprocess_mod, "run", fake_run)
    result = LeanPropertyProvider().generate([], {})
    assert result == [{"property_id": "P-1"}]
    assert "git unavailable" in capsys.readouterr().err


def test_lean_provider_concurrent_clone_rename_race(monkeypatch, tmp_path):
    """If a concurrent resolver renames its clone into place first, the
    loser's rename raises OSError; the winner's valid checkout must be used
    instead of crashing."""
    import subprocess as subprocess_mod

    monkeypatch.delenv("SPECA_LEAN4_PLUGIN_DIR", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_AUTO_CLONE", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path))

    cache = tmp_path / ".plugins" / "speca-lean4-plugin-v0.1.0"

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            dest = Path(cmd[-1])
            (dest / "src" / "speca_lean4").mkdir(parents=True)
            # Concurrent winner appears between clone and rename.
            (cache / "src" / "speca_lean4").mkdir(parents=True)
            (cache / "src" / "speca_lean4" / "marker.txt").write_text(
                "winner", encoding="utf-8"
            )
            return subprocess_mod.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0] == "git" and "rev-parse" in cmd:
            return subprocess_mod.CompletedProcess(cmd, 0, stdout=cmd[2] + "\n", stderr="")
        if cmd[0] == "git":
            return subprocess_mod.CompletedProcess(cmd, 0, stdout="v0.1.0\n", stderr="")
        Path(cmd[cmd.index("--out") + 1]).write_text(
            json.dumps({"properties": [{"property_id": "P-1"}]}), encoding="utf-8"
        )
        return subprocess_mod.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess_mod, "run", fake_run)
    result = LeanPropertyProvider().generate([], {})
    assert result == [{"property_id": "P-1"}]
    # The winner's checkout survived; no tmp leftovers.
    assert (cache / "src" / "speca_lean4" / "marker.txt").exists()
    leftovers = [p for p in cache.parent.iterdir() if ".tmp-" in p.name]
    assert leftovers == []


def test_lean_provider_cleans_partial_clone_cache(monkeypatch, tmp_path):
    """A half-populated cache dir (interrupted clone) must be removed and
    re-cloned, not reused or allowed to break the re-clone."""
    import subprocess as subprocess_mod

    monkeypatch.delenv("SPECA_LEAN4_PLUGIN_DIR", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_AUTO_CLONE", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_HEALTH_JSON", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path))

    # Simulate the leftover of an interrupted clone: dir exists, shape check fails.
    partial = tmp_path / ".plugins" / "speca-lean4-plugin-v0.1.0"
    (partial / ".git").mkdir(parents=True)
    (partial / ".git" / "config").write_text("stub", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            dest = Path(cmd[-1])
            assert not dest.exists(), "clone destination should not pre-exist"
            (dest / "src" / "speca_lean4").mkdir(parents=True)
            return subprocess_mod.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0] == "git":  # version probe
            return subprocess_mod.CompletedProcess(cmd, 0, stdout="v0.1.0\n", stderr="")
        Path(cmd[cmd.index("--out") + 1]).write_text(
            json.dumps({"properties": [{"property_id": "P-1"}]}), encoding="utf-8"
        )
        return subprocess_mod.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess_mod, "run", fake_run)
    result = LeanPropertyProvider().generate([], {})
    assert result == [{"property_id": "P-1"}]
    cache = tmp_path / ".plugins" / "speca-lean4-plugin-v0.1.0"
    assert (cache / "src" / "speca_lean4").is_dir()  # fresh clone in place
    assert not (cache / ".git" / "config").exists()  # partial leftover gone


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


def test_prompt_provider_routes_to_base_run(monkeypatch):
    """#87 residual: the default (prompt) path must be identical to the
    pre-seam behavior — run() goes straight to the Claude CLI batch loop and
    never enters the provider branch."""
    import asyncio
    from scripts.orchestrator import base as base_mod

    called = {}

    async def _base_run(self):
        called["base_run"] = True

    monkeypatch.setattr(base_mod.BaseOrchestrator, "run", _base_run)

    def _forbidden(self):
        raise AssertionError(
            "provider branch must not run for the default prompt provider"
        )

    monkeypatch.setattr(
        base_mod.Phase01Orchestrator, "_run_01e_with_provider", _forbidden
    )

    orch = create_orchestrator("01e")  # default: prompt
    asyncio.run(orch.run())
    assert called.get("base_run")


def test_prompt_provider_keeps_output_fields_compaction():
    """The prompt path's PARTIAL compaction (output_fields) must stay exactly
    as configured — only the non-prompt provider save path bypasses it."""
    orch = create_orchestrator("01e")
    assert orch.config.output_fields == PHASE_CONFIGS["01e"].output_fields
    assert orch.config.output_fields, "prompt-path compaction must stay active"


def test_provider_output_fields_bypass_stays_local():
    """The lean-provider save path clears output_fields on its own config
    copy; the global 01e config must never be affected (regression guard for
    the lean_*-provenance compaction seam)."""
    orch = create_orchestrator("01e", property_provider="lean")
    orch.config.output_fields = []  # what _run_01e_with_provider does at save
    assert PHASE_CONFIGS["01e"].output_fields, "global 01e config was mutated"


# Fixed input for the #87(b) golden test: full Property field set plus extra
# provenance keys that the default prompt path must strip via output_fields.
_GOLDEN_INPUT_PROPERTIES = [
    {
        "property_id": "PROP-golden-001",
        "text": "Quorum intersection weight is bounded",
        "type": "safety",
        "assertion": "forall q1 q2: quorum_2 q1 -> quorum_2 q2 -> overlap(q1, q2) >= threshold",
        "severity": "CRITICAL",
        "covers": "FN-001",
        "reachability": {
            "classification": "external",
            "entry_points": ["P2P"],
            "attacker_controlled": True,
            "bug_bounty_scope": "in_scope",
        },
        "exploitability": "high",
        "bug_bounty_eligible": True,
        "lean_status": "proved",
        "lean_proof_source": "theorem quorum_intersection ... := by omega",
        "internal_note": "must never appear in the prompt-path PARTIAL",
    },
    {
        "property_id": "PROP-golden-002",
        "text": "No two justified blocks at one height",
        "type": "safety",
        "assertion": "justified b1 h -> justified b2 h -> b1 = b2",
        "severity": "HIGH",
        "covers": "FN-002",
        "reachability": {
            "classification": "internal",
            "entry_points": [],
            "attacker_controlled": False,
            "bug_bounty_scope": "conditional",
        },
        "exploitability": "medium",
        "bug_bounty_eligible": False,
        "kurtosis_test": {"scaffold": True},
    },
]


def test_prompt_path_partial_matches_golden_fixture(monkeypatch, tmp_path):
    """#87(b): true fixture-identity guard for the DEFAULT provider path.

    The prompt path's 01e PARTIAL for a fixed input must stay identical to
    the committed golden file — same output_fields compaction (extra keys
    stripped), same key order, same envelope, same serialization. Any change
    to the collector/config seam that alters the default path's bytes fails
    here, not in production diffs. Newlines are normalized because the
    collector writes platform-native line endings; content is what the #87
    contract freezes.
    """
    from scripts.orchestrator.collector import ResultCollector
    from scripts.orchestrator.config import get_phase_config

    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path))
    collector = ResultCollector(get_phase_config("01e").model_copy(deep=True))
    out_path = collector.save_partial(
        [json.loads(json.dumps(p)) for p in _GOLDEN_INPUT_PROPERTIES],
        worker_id=0,
        batch_index=0,
        timestamp=1700000000,
    )
    assert out_path.name == "01e_PARTIAL_W0B0_1700000000.json"

    golden = Path(__file__).parent / "fixtures" / "01e_prompt_partial_golden.json"
    produced = out_path.read_bytes().replace(b"\r\n", b"\n")
    expected = golden.read_bytes().replace(b"\r\n", b"\n")
    assert produced == expected, (
        "default prompt-path 01e PARTIAL differs from the golden fixture "
        f"({golden}); if the change is intentional, regenerate the golden "
        "and say so explicitly in the PR."
    )
    # Belt and braces: the stripped extras must really be gone.
    doc = json.loads(produced.decode("utf-8"))
    saved_keys = set().union(*(p.keys() for p in doc["properties"]))
    assert "lean_status" not in saved_keys
    assert "internal_note" not in saved_keys


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


def test_external_plugins_are_version_pinned():
    # issue #87: plugin boundaries must be version-pinned. The pin mechanism
    # (a plugin_version field at the resolution point) must exist on both
    # external plugins. Both pins are now concrete: the lean plugin pins the
    # speca-lean4-plugin release tag (plugin #8 F1), kurtosis-harness pins a
    # commit SHA until #92 publishes a tag.
    assert LeanPropertyProvider.plugin_version == "v0.1.0"
    assert KurtosisVerificationBackend.plugin_version, "kurtosis pin must be concrete, not None"


def test_phase04_run_dispatches_confirmed_findings_to_backend(monkeypatch, tmp_path):
    """Phase04Orchestrator.run() must filter self.results by the real Phase-04
    verdict strings and dispatch exactly those to the verification backend.

    Regression guard for the follow-up-review bug where the filter used the
    bare strings {"CONFIRMED", "POTENTIAL"} instead of the actual Phase-04
    verdicts {"CONFIRMED_VULNERABILITY", "CONFIRMED_POTENTIAL"}, making
    confirmed_findings always empty. Exercises run()'s filter+dispatch path,
    not just create_orchestrator() construction.
    """
    import asyncio
    from scripts.orchestrator import base as base_mod
    from scripts.orchestrator import providers as providers_mod

    # Route get_output_root() at tmp and provide the required TARGET_INFO.json.
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path))
    (tmp_path / "TARGET_INFO.json").write_text(
        json.dumps({"repository": "x/y", "commit": "deadbeef"}), encoding="utf-8"
    )

    dispatched = {}

    class SpyBackend:
        def verify(self, confirmed_findings, target_info):
            dispatched["findings"] = confirmed_findings
            dispatched["target_info"] = target_info
            return [
                {"property_id": f["property_id"], "verdict": "reproduced", "harness": "spy"}
                for f in confirmed_findings
            ]

    # run() does `from .providers import resolve_verification_backend` at call
    # time, so patching the providers-module attribute is picked up.
    monkeypatch.setattr(providers_mod, "resolve_verification_backend", lambda name: SpyBackend())

    # Stub out the heavy base pipeline; only the post-04 dispatch path is under test.
    async def _noop(self):
        return None
    monkeypatch.setattr(base_mod.BaseOrchestrator, "run", _noop)

    orch = create_orchestrator("04", verification_backend="kurtosis")
    orch.results = [
        {"property_id": "P-1", "review_verdict": "CONFIRMED_VULNERABILITY"},
        {"property_id": "P-2", "review_verdict": "CONFIRMED_POTENTIAL"},
        {"property_id": "P-3", "review_verdict": "DISPUTED_FP"},
        {"property_id": "P-4", "review_verdict": "PASS_THROUGH"},
        {"property_id": "P-5", "review_verdict": "CONFIRMED"},  # bare string must NOT match
    ]

    asyncio.run(orch.run())

    assert "findings" in dispatched, "backend.verify() was never called"
    assert {f["property_id"] for f in dispatched["findings"]} == {"P-1", "P-2"}
    assert dispatched["target_info"]["commit"] == "deadbeef"

    ver_path = tmp_path / "04_VERIFICATION.json"
    assert ver_path.exists(), "04_VERIFICATION.json was not written"
    records = json.loads(ver_path.read_text(encoding="utf-8"))["verification_records"]
    assert {r["property_id"] for r in records} == {"P-1", "P-2"}


# ---------------------------------------------------------------------------
# speca#88 Task 8 — pilot tests against the REAL plugin checkout.
#
# These run only when SPECA_LEAN4_PLUGIN_DIR points at an actual
# speca-lean4-plugin checkout (the `properties-lean` CI job resolves the
# pinned version and exports it; `tests-on-push` skips them). Proof health
# comes from the plugin's committed sample fixture — it certifies NOTHING
# about the real theorems; these tests validate the plumbing contract
# (proved-status property with an on-disk fixture scaffold, 01e schema
# validity, determinism), not mathematical truth.
# ---------------------------------------------------------------------------

_REAL_PLUGIN_DIR = os.environ.get("SPECA_LEAN4_PLUGIN_DIR", "")


def _real_plugin_ready() -> bool:
    if not _REAL_PLUGIN_DIR:
        return False
    root = Path(_REAL_PLUGIN_DIR)
    return (
        (root / "src" / "speca_lean4").is_dir()
        and (root / "tests" / "fixtures" / "theorem_health.sample.json").is_file()
        and (root / "tests" / "fixtures" / "bug_bounty_scope.sample.json").is_file()
    )


requires_real_plugin = pytest.mark.skipif(
    not _real_plugin_ready(),
    reason="pilot tests need SPECA_LEAN4_PLUGIN_DIR pointing at a real "
           "speca-lean4-plugin checkout (with its sample fixtures)",
)


def _pilot_generate(monkeypatch, out_root: Path) -> list[dict]:
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(out_root))
    monkeypatch.delenv("SPECA_LEAN4_KURTOSIS_FIXTURES", raising=False)
    monkeypatch.delenv("SPECA_LEAN4_RUN_LEAN", raising=False)
    root = Path(_REAL_PLUGIN_DIR)
    scope = json.loads(
        (root / "tests" / "fixtures" / "bug_bounty_scope.sample.json")
        .read_text(encoding="utf-8")
    )
    health = root / "tests" / "fixtures" / "theorem_health.sample.json"
    return LeanPropertyProvider().generate([], scope, source=str(health))


@requires_real_plugin
def test_lean_pilot_proved_property_with_fixture(monkeypatch, tmp_path):
    """Task 8 pilot: at least one lean_status=proved property carries a
    kurtosis_test whose fixture scaffold exists on disk, and the whole
    emission validates against the core 01e schema (additive fields only)."""
    props = _pilot_generate(monkeypatch, tmp_path)
    assert props, "pilot emitted no properties"

    # Core 01e schema validity (extras like lean_* / kurtosis_test are
    # additive and must not break validation).
    Phase01ePartial.model_validate({"properties": props})

    proved_with_fixture = [
        p for p in props
        if p.get("lean_status") == "proved" and p.get("kurtosis_test")
    ]
    assert proved_with_fixture, (
        "no proved property with a kurtosis_test fixture — the pilot "
        "contract (issue #88 Task 8) is not met"
    )

    fixtures_root = tmp_path / "kurtosis"
    for p in props:
        kt = p.get("kurtosis_test")
        if not kt:
            continue  # honest null for checkerless properties
        fp = Path(kt)
        assert fp.is_file(), f"kurtosis_test does not exist on disk: {kt}"
        assert fp.name == "assertion.scaffold.json"
        assert fixtures_root.resolve() in fp.resolve().parents, (
            f"fixture escaped the output root: {kt}"
        )
        # devnet config sits next to the assertion stub
        assert (fp.parent / "devnet.scaffold.json").is_file()
        doc = json.loads(fp.read_text(encoding="utf-8"))
        # Honesty invariants: these are scaffolds — nothing has run, no
        # verdict may be claimed, and the checker names a real Executable
        # function.
        assert doc["scaffold"] is True
        assert doc["handoff"]["verdict"] is None
        assert doc["checker"]["primary"]
        assert doc["property_id"] == p["property_id"]


def _snapshot_tree(root: Path) -> dict[str, str]:
    """{relative POSIX path: sha256} for every file under *root*."""
    return {
        fp.relative_to(root).as_posix():
            hashlib.sha256(fp.read_bytes()).hexdigest()
        for fp in sorted(root.rglob("*")) if fp.is_file()
    }


@requires_real_plugin
def test_lean_pilot_determinism(monkeypatch, tmp_path):
    """Task 8 determinism: the same inputs must produce byte-identical
    properties, kurtosis_test paths, and fixture contents on a re-run."""
    props1 = _pilot_generate(monkeypatch, tmp_path)
    snap1 = _snapshot_tree(tmp_path / "kurtosis")
    assert snap1, "first run wrote no fixtures"

    props2 = _pilot_generate(monkeypatch, tmp_path)
    snap2 = _snapshot_tree(tmp_path / "kurtosis")

    assert props1 == props2, "properties differ between identical runs"
    assert snap1 == snap2, "fixture tree differs between identical runs"
