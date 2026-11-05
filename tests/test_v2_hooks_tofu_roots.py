# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The terraform roots' run hooks come from the tofu-roots hook plugin, not
the core: the state-location validator, the state-location recorder and the
state-isolation evidence. With the plugin absent the core validates without
the state-location check and the summary's evidence names every lifecycle
bound to nothing; with it present the three hooks are installed and the
evidence is the plugin's.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from v2_support import V2Run, copy_config, load_context, stub_environment


def _rebind_storage(root: Path, backend: str) -> None:
    p = root / "cfg" / "storage-builders.yml"
    p.write_text(p.read_text().replace("state_configuration: s3-east1", f"state_configuration: {backend}"))


@pytest.fixture
def no_hook_plugins(monkeypatch):
    """The entry-point group empty: no hook plugin at all is installed."""
    from cs_image_system.base.commands import run_lifecycles as rl
    import importlib.metadata as md
    real = md.entry_points
    monkeypatch.setattr(md, "entry_points",
                        lambda **kw: [] if kw.get("group") == rl.HOOK_ENTRY_POINT_GROUP else real(**kw))
    saved = {name: list(getattr(rl, name)) for name in
             ("_VALIDATORS", "_AFTER_GENERATE", "_BEFORE_APPLY", "_AFTER_APPLY", "_ON_SUMMARY", "_STATE_BINDINGS")}
    from cs_image_system.tofu_roots import hooks as tofu_hooks
    for name, hooks in saved.items():
        getattr(rl, name)[:] = [h for h in hooks if getattr(h, "__module__", None) != tofu_hooks.__name__]
    monkeypatch.setattr(rl, "_HOOK_PLUGINS_LOADED", False)
    yield
    for name, hooks in saved.items():
        getattr(rl, name)[:] = hooks


def test_the_plugin_installs_the_three_hooks():
    from cs_image_system.base.commands import run_lifecycles as rl
    from cs_image_system.tofu_roots import hooks as tofu_hooks
    assert rl.load_hook_plugins(force=True) >= 2          # the dummy plugin and this one
    assert tofu_hooks.validate_state_locations in rl._VALIDATORS
    assert tofu_hooks.record_state_locations in rl._AFTER_GENERATE
    assert tofu_hooks.lifecycle_state_bindings in rl._STATE_BINDINGS
    before = {name: len(getattr(rl, name)) for name in ("_VALIDATORS", "_AFTER_GENERATE", "_STATE_BINDINGS")}
    rl.load_hook_plugins(force=True)                      # the per-run reload installs nothing twice
    assert {name: len(getattr(rl, name)) for name in before} == before


def test_without_the_plugin_validate_skips_the_state_location_check(tmp_path, monkeypatch, no_hook_plugins):
    root = copy_config(tmp_path)
    _rebind_storage(root, "nowhere")                      # an undeclared backend
    stub_environment(monkeypatch)
    load_context(root)
    from cs_image_system.base.commands.run_lifecycles import validate_only
    from cs_image_system.base.global_context import GlobalTypeContext
    from cs_image_system.tofu_roots.hooks import state_location_problems
    ctx = GlobalTypeContext()
    assert any("not declared" in str(e) for e in state_location_problems(ctx))
    assert not any("not declared" in e for e in validate_only(ctx))


def test_with_the_plugin_validate_refuses_an_undeclared_backend(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    _rebind_storage(root, "nowhere")
    stub_environment(monkeypatch)
    load_context(root)
    from cs_image_system.base.commands.run_lifecycles import validate_only
    errors = validate_only()
    assert any("workspace 'aws-ebs' names state backend 'nowhere', which is not declared" == e for e in errors), errors


def test_without_the_plugin_the_summary_evidence_is_empty(tmp_path, monkeypatch, no_hook_plugins):
    v2 = V2Run(tmp_path, monkeypatch)
    summary = v2.run("all", apply=False)
    assert summary.ok, summary.error
    assert set(summary.state_bindings) >= {"identity", "storage", "base-image", "instance-image"}
    assert all(bindings == {} for bindings in summary.state_bindings.values())
    assert not (v2.meta_state / "state-locations.yaml").exists()


def test_with_the_plugin_the_summary_carries_the_evidence_and_the_records_exist(tmp_path, monkeypatch):
    v2 = V2Run(tmp_path, monkeypatch)
    summary = v2.run("all", apply=False)
    assert summary.ok, summary.error
    assert set(summary.state_bindings["storage"]) == {"aws-ebs", "aws-efs", "aws-s3", "gcp-pd", "gcp-gcs"}
    assert summary.state_bindings["base-image"] == {}
    assert (v2.meta_state / "state-locations.yaml").is_file()
