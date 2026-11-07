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

from harness import V2Run, command_lines, copy_config, load_context, reset_singletons, stub_environment, tree

LITERAL_GID = re.compile(r"\b(?:owner_)?gid\s*=\s*\d+\b")


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _write_yaml(path: Path, data) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _prepared(tmp_path, monkeypatch, mutate):
    """A config copy mutated BEFORE the context loads."""
    root = copy_config(tmp_path)
    mutate(root)
    return V2Run(tmp_path, monkeypatch, config_root=root)


def test_identity_root_emits_gid_outputs_via_the_shim(v2):
    assert v2.run(["identity"], apply=False).ok
    gen = tree(v2.generated / "identity" / "oktagroups" / "group-generation")
    outputs = gen["oktagroups-group-generation-outputs.tf"]
    assert 'data "external" "group_gids"' in outputs
    assert '"cs-image-system"' in outputs and '"export-gids"' in outputs
    assert 'output "group_gids"' in outputs
    assert "tonumber(gid)" in outputs
    assert 'output "groups"' in outputs
    assert "module.group_coops.user_group_id" in outputs
    root_tf = gen["oktagroups-group-generation.tf"]
    assert "hashicorp/external" in root_tf
    # the query is the shim's structural input: identity type, org/team, group names
    assert 'identity_type = "okta"' in outputs
    assert "basic,coops,secofs,stofs,tcmet" in outputs
    assert not LITERAL_GID.search("\n".join(gen.values()))


def test_identity_read_model_is_structural(v2):
    assert v2.run(["identity"], apply=False).ok
    model = yaml.safe_load((v2.meta_state / "identity.yaml").read_text())
    coops = model["groups"]["coops"]
    assert coops["identity_type"] == "okta"
    assert coops["gid_policy"] == "creation-only"
    assert coops["builder"] == "oktagroups"
    assert coops["members"] == ["avery.alpha", "casey.charlie"]   # mirrors live OPA
    assert "avery.alpha" in coops["admins"]
    assert coops["managed"] is True
    assert model["groups"]["basic"]["is_root"] is True
    assert "avery.alpha" in model["users"]
    assert not re.search(r"\bgid: \d+", yaml.safe_dump(model))


def test_identity_runner_script_is_gated_and_never_applies_unless_configured(v2):
    assert v2.run(["identity"], apply=False).ok
    script = (v2.generated / "identity" / "run-identity.sh").read_text()
    cmds = command_lines(script)
    assert any("tofu plan -input=false -out=tfplan" in c for c in cmds)
    assert any("cs-image-system gate-plan --planfile tfplan" in c for c in cmds)
    assert not any(" apply " in c for c in cmds), "apply_identity is off in the fixture"
    assert "# state: workspace oktagroups -> local://state/oktagroups.tfstate" in script   # on disk


def test_group_disappearance_is_a_hard_failure(tmp_path, monkeypatch):
    def mutate(root: Path):
        ms = root / "meta-state"
        ms.mkdir(exist_ok=True)
        _write_yaml(ms / "identity.yaml", {"groups": {"ghost": {"managed": True, "builder": "oktagroups"}}})
    run = _prepared(tmp_path, monkeypatch, mutate)
    try:
        summary = run.run(["identity"], apply=False)
        assert not summary.ok
        assert any("'ghost'" in e for e in summary.validation_errors)
    finally:
        run.restore_cwd()


def test_unmanaged_group_is_state_rm_never_destroyed(tmp_path, monkeypatch):
    def mutate(root: Path):
        p = root / "groups" / "group-tcmet.yaml"
        data = yaml.safe_load(p.read_text())
        data["groups"][0]["unmanaged"] = True
        _write_yaml(p, data)
        ms = root / "meta-state"
        ms.mkdir(exist_ok=True)
        _write_yaml(ms / "identity.yaml", {"groups": {"tcmet": {"managed": True, "builder": "oktagroups"}}})
    run = _prepared(tmp_path, monkeypatch, mutate)
    try:
        assert run.run(["identity"], apply=False).ok
        gen = tree(run.generated / "identity" / "oktagroups" / "group-generation")
        assert 'module "group_tcmet"' not in gen["oktagroups-group-generation-group-tcmet.tf"]
        assert "UNMANAGED" in gen["oktagroups-group-generation-group-tcmet.tf"]
        cmds = command_lines((run.generated / "identity" / "run-identity.sh").read_text())
        # the removal is the runner's pre-plan step's, decided by what the state
        # holds when it runs (tests/test_group_release.py); generation writes no
        # `state rm`, because what generation knows is a record a dry run rewrites
        assert not any("state rm" in c for c in cmds)
        step = next(i for i, c in enumerate(cmds) if "prune-attachments --builder oktagroups" in c)
        plan = next(i for i, c in enumerate(cmds) if "tofu plan -input=false -out=tfplan" in c)
        assert step < plan, "the step that releases runs before the plan the gate reads"
        # nothing destroys, and no operation's allowance is on the gate; the file
        # the gate reads names dropped MEMBERSHIPS of managed groups only
        assert not any("tofu destroy" in c or " -destroy" in c or "--allow-destroy " in c for c in cmds)
        model = yaml.safe_load((run.meta_state / "identity.yaml").read_text())
        assert model["groups"]["tcmet"]["managed"] is False
    finally:
        run.restore_cwd()


# ------------------------------------------- the read-only group builder

def test_the_read_only_group_builder_answers_the_read_only_truth(monkeypatch):
    from tests.harness import FIXTURE_CONFIG
    from cs_image_system.base.read_models import identity_read_model
    stub_environment(monkeypatch)
    ctx = load_context(FIXTURE_CONFIG)
    try:
        ro = ctx.group_builders["okta-groups-ro"]
        managed = ctx.group_builders["oktagroups"]
        assert [g.get_name() for g in ro.get_groups_for_builder()] == ["readers"]
        assert ro.manages_groups() is False and managed.manages_groups() is True

        def no_opa(*a, **kw):
            raise AssertionError("the read-only builder asked OPA")
        monkeypatch.setattr(type(ro), "_resolver", no_opa)
        assert ro.query_state() == {}
        assert ro.enrollment_token_reference("readers") is None
        assert ro.can_query_servers() is False
        assert ro.can_manage_workload_access() is False
        with pytest.raises(NotImplementedError):
            ro.query_attributes(ro.get_groups_for_builder()[0])
        with pytest.raises(NotImplementedError):
            ro.attribute_conflicts()

        model = identity_read_model(ctx)["groups"]
        assert model["readers"]["managed"] is False and model["readers"]["builder"] == "okta-groups-ro"
        assert model["coops"]["managed"] is True
    finally:
        reset_singletons()


def test_a_read_only_group_is_looked_up_and_never_drifts(tmp_path: Path, monkeypatch):
    from cs_image_system.base import state_query
    from cs_image_system.base.state_query import StateReport
    run = V2Run(tmp_path, monkeypatch)
    try:
        summary = run.run(["identity"], apply=False)
        assert summary.ok, summary.error
        data_tf = "".join(p.read_text() for p in run.generated.rglob("*.tf") if "okta-groups-ro" in str(p))
        assert 'data "okta_group"' in data_tf and '"readers"' in data_tf, "the lookup root emits the lookup"
        assert "module \"group_readers\"" not in "".join(p.read_text() for p in run.generated.rglob("*.tf"))
        # the managed parent's rule would read an absent OPA record as missing [HARD]
        recorded = run.ctx.meta_state.identity_read_model()["groups"]
        assert recorded["readers"]["managed"] is False, "the run's read-model records the lookup as unmanaged"
        report = StateReport(run="test")
        drift = state_query.group_drift(run.ctx, {"readers": {"present": False}}, report)
        assert not [d for d in drift if d.name == "readers"], drift
    finally:
        run.restore_cwd()


# ------------------------------------------------------- the OPA client

def test_the_opa_listing_follows_the_link_header_to_every_page():
    from cs_image_system.okta_opa_plugin.opa_gids import OpaGidResolver, next_page
    assert next_page({"Link": '<https://h/v1/teams/t/security_policy?offset=2>; rel="next", <https://h/x>; rel="prev"'}) \
        == "https://h/v1/teams/t/security_policy?offset=2"
    assert next_page({"link": "<https://h/p2>; rel=next"}) == "https://h/p2"
    assert next_page({"Link": '<https://h/p1>; rel="prev"'}) is None and next_page({}) is None
    pages = {
        "https://h/v1/teams/t/security_policy": ({"list": [{"id": "a"}, {"id": "b"}]},
                                                  {"Link": '<https://h/v1/teams/t/security_policy?offset=2>; rel="next"'}),
        "https://h/v1/teams/t/security_policy?offset=2": ({"list": [{"id": "c"}]},
                                                           {"Link": '</v1/teams/t/security_policy?offset=3>; rel="next"'}),
        "https://h/v1/teams/t/security_policy?offset=3": ({"list": [{"id": "d"}]}, {}),
    }
    asked: list[str] = []

    def full(method, url, headers, body):
        if url.endswith("/service_token"):
            return {"bearer_token": "tok"}, {}
        asked.append(url)
        return pages[url]
    r = OpaGidResolver("https://h", "t", "k", "s", transport_full=full)
    assert [p["id"] for p in (r.security_policies() or [])] == ["a", "b", "c", "d"]
    assert len(asked) == 3, asked
    # a body-only transport (every existing test) still answers one page and no headers
    r1 = OpaGidResolver("https://h", "t", "k", "s",
                        transport=lambda m, u, h, b: {"bearer_token": "tok"} if u.endswith("/service_token") else {"list": [{"id": "x"}]})
    assert [p["id"] for p in (r1.security_policies() or [])] == ["x"]


def test_a_retirement_404_is_read_from_the_status_code_not_the_text():
    import urllib.error
    from email.message import Message
    from cs_image_system.okta_opa_plugin.opa_gids import OpaGidResolver
    r = OpaGidResolver("https://h", "t", "k", "s", transport=lambda *a: {})
    r._login_project = lambda group: "/v1/p"        # type: ignore[method-assign]
    r.token = lambda: "tok"                          # type: ignore[method-assign]

    def says_404_in_a_500(method, url, headers, body):
        raise urllib.error.HTTPError(url, 500, "upstream said 404 somewhere", Message(), None)
    r.transport = says_404_in_a_500                  # type: ignore[assignment]
    with pytest.raises(urllib.error.HTTPError):
        r.retire_server("coops", "abc")

    def real_404(method, url, headers, body):
        raise urllib.error.HTTPError(url, 404, "not found", Message(), None)
    r.transport = real_404                           # type: ignore[assignment]
    assert r.retire_server("coops", "abc") is True


def test_a_missing_opa_key_is_a_real_refusal():
    from cs_image_system.okta_opa_plugin.okta_tf_workspace import OktaTfWorkspaceModelMixin
    probe = type("P", (), {"team": "t", "org": "o", "name": "b",
                           "_team_var": lambda self: "t"})()
    with pytest.raises(ValueError, match="TF_VAR_t_key"):
        OktaTfWorkspaceModelMixin._require_tfvar(probe, "key", "default", {})   # type: ignore[arg-type]


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
    run = V2Run(tmp_path, monkeypatch, config_root=root)
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
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["identity"], apply=False).ok
        rel = [p.relative_to(run.generated) for p in run.generated.rglob("*.tf")]
        written = [p for p in rel if "dummy" in str(p).lower()]
        assert written and all(str(p).startswith("identity/dummy-users/") for p in written), written
        assert not list(run.generated.rglob("Dummy-tf"))
    finally:
        run.restore_cwd()

