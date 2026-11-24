# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The identity roots: what the group and user builders emit and record.

* the identity root emits an outputs block (group -> gid) fed by the
  plugin's queryable shim, and a structural read-model file; no literal gid
  anywhere in generated IaC; the runner is gated and never applies unless
  configured; a managed group that disappears is a hard failure; an
  unmanaged group is released from state, never destroyed;
* the read-only group builder answers the read-only truth: a lookup root,
  never a resource, and a lookup-only group never drifts;
* the OPA client follows the Link header to every page, reads a retirement
  404 from the status code, and a missing OPA key is a real refusal;
* the core's read-model rules over a posix group: the read-model is
  structural, a managed group the YAML lost fails the run, an unmanaged
  one is recorded so and never drifts;
* the dummy (template) builders return asset sets, keep org and team,
  refuse credentials and write under their own root; the attributes probe
  step carries the configuration.

History: gate 4 (identity half), stage 63 items 1, 8, 12, 13 and 18.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml
from harness import FixtureRun, copy_config


@pytest.fixture
def fixture_run(tmp_path, monkeypatch):
    run = FixtureRun(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _write_yaml(path: Path, data) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _prepared(tmp_path, monkeypatch, mutate):
    """A config copy mutated BEFORE the context loads."""
    root = copy_config(tmp_path)
    mutate(root)
    return FixtureRun(tmp_path, monkeypatch, config_root=root)


# ------------------------------------- the core's read-model rules, on posix
# The identity read-model (engine/read_models.py) and the rule that a managed
# group never silently leaves the YAML (engine/validation_rules.py) are the
# core's; here through the posix identity plugin's group, pxgroup.

def test_the_identity_read_model_of_a_posix_group_is_structural(fixture_run):
    assert fixture_run.run(["identity"], apply=False).ok
    model = yaml.safe_load((fixture_run.meta_state / "identity.yaml").read_text())
    px = model["groups"]["pxgroup"]
    assert px["identity_type"] == "posix" and px["gid_policy"] == "config-time"
    assert px["builder"] == "posix-local"
    assert px["members"] == ["taylor_tango", "unity_uniform"] and px["admins"] == ["taylor_tango"]
    assert px["managed"] is True and px["is_root"] is False
    assert {"taylor_tango", "unity_uniform"} <= set(model["users"])
    assert "gid" not in px, "structural facts only: a gid is the configuration's, never the read-model's"
    assert not re.search(r"\bgid: \d+", yaml.safe_dump(model))


def test_a_posix_group_the_read_model_holds_and_the_yaml_lost_is_a_hard_failure(tmp_path, monkeypatch):
    def mutate(root: Path):
        ms = root / "meta-state"
        ms.mkdir(exist_ok=True)
        _write_yaml(ms / "identity.yaml", {"groups": {"pxghost": {"managed": True, "builder": "posix-local",
                                                                  "identity_type": "posix"}}})
    run = _prepared(tmp_path, monkeypatch, mutate)
    try:
        summary = run.run(["identity"], apply=False)
        assert not summary.ok
        assert any("'pxghost'" in e and "unmanaged: true" in e for e in summary.validation_errors), \
            summary.validation_errors
    finally:
        run.restore_cwd()


def test_an_unmanaged_posix_group_is_recorded_unmanaged_and_never_drifts(tmp_path, monkeypatch):
    from cs_image_system.engine import state_query

    def mutate(root: Path):
        p = root / "groups" / "group-pxgroup.yaml"
        data = yaml.safe_load(p.read_text())
        data["groups"][0]["unmanaged"] = True
        _write_yaml(p, data)
        ms = root / "meta-state"
        ms.mkdir(exist_ok=True)
        _write_yaml(ms / "identity.yaml", {"groups": {"pxgroup": {"managed": True, "builder": "posix-local"}}})
    run = _prepared(tmp_path, monkeypatch, mutate)
    try:
        summary = run.run(["identity"], apply=False)
        assert summary.ok, (summary.error, summary.validation_errors)
        model = yaml.safe_load((run.meta_state / "identity.yaml").read_text())
        assert model["groups"]["pxgroup"]["managed"] is False, "kept in the YAML as unmanaged: no longer managed"
        # whatever a provider would say of it, an unmanaged group is not drift -- even one seen before
        ms = run.ctx.meta_state
        recorded = ms.identity_read_model()
        recorded["groups"]["pxgroup"]["seen"] = True
        ms.write_identity_read_model(recorded)
        report = state_query.StateReport(run="test")
        drift = state_query.group_drift(run.ctx, {"pxgroup": {"present": False}}, report)
        assert not [d for d in drift if d.name == "pxgroup"], drift
        recorded["groups"]["pxgroup"]["managed"] = True          # the control: managed, the same answer is hard
        ms.write_identity_read_model(recorded)
        assert [d.hard for d in state_query.group_drift(run.ctx, {"pxgroup": {"present": False}}) if d.name == "pxgroup"] == [True]
    finally:
        run.restore_cwd()


# ------------------------------------------- the read-only group builder


# ------------------------------------------------------- the OPA client


# ---------------------------------------------- the template (dummy) builders

def test_the_dummy_builders_return_an_asset_set_and_a_declared_dummy_builder_runs(tmp_path: Path, monkeypatch):
    from cs_image_system.contract.assets import AssetSet
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.dummy_plugin.dummy_builders import DummyGroupBuilder, DummyUserBuilder
    for cls in (DummyGroupBuilder, DummyUserBuilder):
        out = cls.generate_items_during(SimpleNamespace(), ExecutionLifecyclePhase.GROUP_GENERATION)  # type: ignore[arg-type]
        assert isinstance(out, AssetSet) and len(out) == 0, cls.__name__
    # the live reproduction: a declared `type: dummy` group builder and a group on it
    root = copy_config(tmp_path)
    gb = root / "cfg" / "group-builders.yml"
    data = yaml.safe_load(gb.read_text())
    data["group_builders"].append({"name": "dummy-groups", "type": "dummy", "org": "example", "team": "example"})
    gb.write_text(yaml.safe_dump(data, sort_keys=False))
    groups = root / "groups" / "group-dummy.yaml"
    groups.write_text(yaml.safe_dump({"groups": [{"name": "dummygroup", "type": "dummy-groups",
                                                  "description": "a group on the template builder"}]}))
    run = FixtureRun(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["identity"], apply=False)
        assert summary.ok, summary.error
    finally:
        run.restore_cwd()


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


    # (--only-providers, which this test once saw splitting a comma list, was
    # retired; tests/test_retired_surfaces.py refuses it)
def test_the_template_models_keep_org_and_team_and_refuse_credentials():
    from cs_image_system.dummy_plugin.dummy_models import DummyGroupBuilderModel
    cast(Any, DummyGroupBuilderModel)(name="g", type="dummy", org="o", team="t")
    for key in ("key", "secret", "api_host"):
        with pytest.raises(ValueError):
            cast(Any, DummyGroupBuilderModel)(name="g", type="dummy", org="o", team="t", **{key: "x"})


def test_the_dummy_user_builder_writes_under_its_own_root(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "group-builders.yml", lambda d: d["user_builders"].append(
        {"name": "dummy-users", "type": "dummy", "org": "example", "team": "example"}))
    run = FixtureRun(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["identity"], apply=False).ok
        rel = [p.relative_to(run.generated) for p in run.generated.rglob("*.tf")]
        written = [p for p in rel if "dummy" in str(p).lower()]
        assert written and all(str(p).startswith("identity/dummy-users/") for p in written), written
        assert not list(run.generated.rglob("Dummy-tf"))
    finally:
        run.restore_cwd()
