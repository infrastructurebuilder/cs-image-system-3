# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 63, the low-hanging items: each one function, one test, found by the
documentation stage reading the code against its README and left as it was
until now. Every test here failed before its fix.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tests.v2_support import FIXTURE_CONFIG, V2Run, copy_config, load_context, reset_singletons, stub_environment


# ---------------------------------------------------- 1. the dummy builders

def test_the_dummy_builders_return_an_asset_set_and_a_declared_dummy_builder_runs(tmp_path: Path, monkeypatch):
    from cs_image_system.base.basic.asset import AssetSet
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.dummy_plugin.dummy_builders import DummyGroupBuilder, DummyUserBuilder
    for cls in (DummyGroupBuilder, DummyUserBuilder):
        out = cls.generate_items_during(SimpleNamespace(), ExecutionLifecyclePhase.GROUP_GENERATION)  # type: ignore[arg-type]
        assert isinstance(out, AssetSet) and len(out) == 0, cls.__name__
    # the reproduction of 2026-09-23: a declared `type: dummy` group builder and a group on it
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


# ------------------------------------------------------------- 2. mask

def _mask(monkeypatch, identity: str | None):
    from typer.testing import CliRunner
    from cs_image_system.system import cli as climod
    if identity is None:
        monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    else:
        monkeypatch.setenv("CSIS_CONFIG_IDENTITY", identity)
    return CliRunner().invoke(climod.app, ["--root-dir", str(FIXTURE_CONFIG), "mask"])


def test_mask_refuses_loudly_when_it_cannot_open_a_marker_and_masks_when_it_can(monkeypatch):
    without = _mask(monkeypatch, None)
    assert without.exit_code == 1, without.output
    assert "mask: FAILED" in without.output and "nothing is masked" in without.output
    assert "::add-mask::" not in without.output
    with_identity = _mask(monkeypatch, str(FIXTURE_CONFIG / ".age-identity"))
    assert with_identity.exit_code == 0, with_identity.output
    assert with_identity.output.count("::add-mask::") > 0


# ------------------------------------------- 3. a packer string default

def test_a_packer_string_default_is_quoted_and_the_version_variable_says_what_it_emits():
    import hcl2
    from cs_image_system.hashicorp_utils.hashicorp import FO, Builder, packer_variable

    def render(**kw) -> str:
        return hcl2.dumps(packer_variable(Builder(), **kw).build(), formatter_options=FO)
    text = render(name="x", type="string", default="1.0.0")
    assert 'default = "1.0.0"' in text, text
    text = render(name="y", type="bool", default=True)
    assert "default = true" in text, text
    text = render(name="z", type="string", default=None, env_var="Z")
    assert 'default = env("Z")' in text, text
    from cs_image_system.packer_plugin import packer_builder
    src = Path(packer_builder.__file__).read_text()
    assert 'name="base_image_version"' in src and 'default="1.0.0"' not in src, "the env variable is what is emitted; no promise of 1.0.0"


# ----------------------------------------- 5. a registry collision named

def test_a_registry_collision_is_named_without_the_models_repr(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    sb = root / "cfg" / "state-backends-2.yml"
    data = yaml.safe_load(sb.read_text())
    twin = dict(data["state_backends"][0])
    twin["name"] = twin["name"].upper()          # normalises to the same registry key
    twin.pop("is_default", None)
    data["state_backends"].append(twin)
    sb.write_text(yaml.safe_dump(data, sort_keys=False))
    stub_environment(monkeypatch)
    with pytest.raises(ValueError) as exc:
        load_context(root)
    message = str(exc.value)
    assert "collide on the registry key" in message and "rename one" in message, message
    assert "TofuS3StateBuilderModel(" not in message and "bucket=" not in message, "no repr, no field values"
    reset_singletons()


# ------------------------------- 6. the migration's previous-location file

def test_the_previous_location_file_carries_no_record_only_key():
    from cs_image_system.base.commands.state_migration import RECORD_ONLY_KEYS, render_record
    record = {"backend": "s3-east1", "type": "s3", "run": "r0", "location": "s3://old/statefiles/ws.tfstate",
              "bucket": "old", "key": "statefiles", "region": "us-east-1", "encrypt": True}
    lines = render_record(record, "# previous")
    assert lines == ["# previous", 'bucket = "old"', 'key = "statefiles"', 'region = "us-east-1"', "encrypt = true"], lines
    assert "location" in RECORD_ONLY_KEYS


# ------------------------- 7. a GCE instance receives the build it baked

def test_the_gce_root_receives_the_build_its_run_baked_under_its_own_variable(tmp_path: Path, monkeypatch):
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.base.lifecycles import Lifecycle
    from cs_image_system.base.models.provider_specific_image import GenericProviderSpecificImage, PSISourceKind
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["instance-image"], apply=False).ok
        ctx = run.ctx
        psi = GenericProviderSpecificImage.resolved(source_name="imgfile-basic-dask", source_kind=PSISourceKind.IMAGE,
                                                    runtime="gcloud-east1", identifier="projects/p/global/images/dask-0007")
        monkeypatch.setattr(ctx, "get_provider_specific_image", lambda source, runtime: psi)
        ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
        ctx.instance_builders["tofu-gce"].pre_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
        tfvars = (run.generated / "instance-image" / "tofu-gce" / "instance-generation" / "instances.auto.tfvars").read_text()
        assert 'gce_test_image = "projects/p/global/images/dask-0007"' in tfvars, tfvars
        assert "_ami_id" not in tfvars, "the AWS root's variable name, which no GCE root declares"
        root = (run.generated / "instance-image" / "tofu-gce" / "instance-generation").glob("*.tf")
        assert any('variable "gce_test_image"' in p.read_text() for p in root), "the root declares the variable the tfvars sets"
    finally:
        ctx.current_lifecycle = None
        run.restore_cwd()


# ------------------------------ 8. the attributes probe step can load

def test_the_attributes_probe_step_carries_the_configuration(tmp_path: Path, monkeypatch):
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    root = copy_config(tmp_path)
    p = root / "groups" / "group-tcmet.yaml"
    data = yaml.safe_load(p.read_text())
    data["groups"][0]["attributes"] = {"unix_gid": 180999}
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        gb = next(b for b in run.ctx.group_builders.values() if isinstance(b, OktaTfGroupBuilder))
        deferred = gb.get_commands_to_run_after(ExecutionLifecyclePhase.GROUP_GENERATION).finalize_executables
        lines = [" ".join([str(e.binary or e.name), *[str(a) for a in (e.args or [])]]) for e in deferred]
        probe = [ln for ln in lines if "identity-attributes --probe --dry-run-apply" in ln]
        assert len(probe) == 1, lines
        assert "--root-dir" in probe[0] and "--no-dry-run" in probe[0], probe[0]
    finally:
        run.restore_cwd()


# ------------------------------------- 9. the SSM profile wins a bake

def test_the_ssm_profile_wins_the_bake_when_both_profiles_are_set(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    p = root / "cfg" / "runtime-builders.yml"
    data = yaml.safe_load(p.read_text())
    aws = next(r for r in data["runtime_builders"] if r["name"] == "aws-east2-runtime")
    assert aws.get("session_instance_profile"), "the fixture's AWS runtime declares an SSM profile"
    aws["iam_instance_profile"] = "the-other-profile"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image"], apply=False).ok
        sources = list((run.generated / "base-image").rglob("*.pkr.hcl"))
        text = "\n".join(s.read_text() for s in sources)
        assert 'iam_instance_profile = "AmazonSSMRoleForInstancesQuickSetup"' in text
        assert "the-other-profile" not in text, "the SSM profile wins on every source"
    finally:
        run.restore_cwd()


# ----------------------------------- 10. a dry run never asks the registry

def test_a_dry_run_never_asks_the_registry_for_a_hostname_claim(tmp_path: Path, monkeypatch):
    from cs_image_system.base import launch_params as lp
    from cs_image_system.base.lifecycles import Lifecycle
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    calls: list[str] = []

    def listen():
        # after the harness installed its own stubs (V2Run's stub_environment)
        monkeypatch.setattr(OktaTfGroupBuilder, "can_query_servers", lambda self: True)
        monkeypatch.setattr(OktaTfGroupBuilder, "registered_servers", lambda self, g: calls.append(g) or [])
    run = V2Run(tmp_path, monkeypatch)                     # dry
    try:
        listen()
        run.ctx.config["apply_instances"] = True
        assert run.ctx.dry_run
        assert lp.validate_claimed_hostnames(run.ctx, [Lifecycle.INSTANCE_IMAGE]) == []
        assert calls == [], "a dry run with the apply flag on made no network call"
    finally:
        run.restore_cwd()
    real = V2Run(tmp_path / "real", monkeypatch, dry_run=False)
    try:
        listen()
        real.ctx.config["apply_instances"] = True
        lp.validate_claimed_hostnames(real.ctx, [Lifecycle.INSTANCE_IMAGE])
        assert calls, "a real run that can launch asks the registry"
    finally:
        real.restore_cwd()


# -------------------------------- 11. preflight reads every cfg file

def test_preflight_finds_a_runtime_declared_in_any_cfg_file(tmp_path: Path):
    from cs_image_system.base.commands.preflight import raw_session_infos
    root = copy_config(tmp_path)
    src = root / "cfg" / "runtime-builders.yml"
    before = {i.runtime for i in raw_session_infos(root)}
    assert before, "the fixture's runtimes are preflighted from their own file"
    (root / "cfg" / "clouds.yaml").write_text(src.read_text())      # the same declarations, another file name
    src.unlink()
    after = {i.runtime for i in raw_session_infos(root)}
    assert after == before, f"{after} != {before}: a runtime declared in another cfg file is preflighted too"


# ------------------------------------- 12. the OPA listing reads every page

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


# ------------------------------------ 13. the configuration loads safely

def test_a_python_tag_in_the_configuration_is_refused_not_constructed(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    (root / "cfg" / "zz-tag.yml").write_text("evil: !!python/object/apply:os.system ['echo pwned']\n")
    stub_environment(monkeypatch)
    with pytest.raises(Exception) as exc:
        load_context(root)
    assert "python/object" in str(exc.value) or "could not determine a constructor" in str(exc.value), str(exc.value)
    reset_singletons()
    from cs_image_system.base import global_context
    src = Path(global_context.__file__).read_text()
    assert "yaml.unsafe_load(stream)" not in src and "yaml.safe_load(stream)" in src
