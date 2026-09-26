# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 63, the dead fields, dead code and misleading messages (decided by
the operator field by field, 2026-09-25). One section per package bullet;
every test here failed before its fix.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, copy_config, load_context, reset_singletons, stub_environment


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _backend(data: dict, name: str) -> dict:
    return next(b for b in data["state_backends"] if b["name"] == name)


# ------------------------------------------------------ 1. state backends

def _s3(**kw):
    from cs_image_system.tf_s3_state_plugin.tf_s3_state_models import TofuS3StateBuilderModel
    return TofuS3StateBuilderModel(name="s3-x", type="s3", bucket="b", key="k", **kw)


def test_s3_backend_arguments_pass_through_when_set_and_stay_silent_at_default():
    assert _s3().pass_through() == {}
    m = _s3(allowed_account_ids=["123456789012"], max_retries=9, skip_credentials_validation=True,
            shared_config_file="/etc/aws/config", no_proxy=["a", "b"],
            assume_role={"role_arn": "arn:aws:iam::1:role/r", "session_name": "csis"},
            endpoints={"s3": "https://s3.example.invalid"})
    got = m.pass_through()
    assert got == {"allowed_account_ids": ["123456789012"], "max_retries": 9,
                   "skip_credentials_validation": True, "shared_config_files": ["/etc/aws/config"],
                   "no_proxy": "a,b",
                   "assume_role": {"role_arn": "arn:aws:iam::1:role/r", "session_name": "csis"},
                   "endpoints": {"s3": "https://s3.example.invalid"}}, got
    reg = m.to_backend_registration()
    from cs_image_system.hashicorp_utils.collector import render_backend_value
    text = "\n".join(render_backend_value(v) for v in reg.backend_settings("ws").values())
    assert '{ role_arn = "arn:aws:iam::1:role/r", session_name = "csis" }' in text, text
    assert '["123456789012"]' in text and "9" in text
    assert reg.remote_state_settings("ws")["assume_role"]["role_arn"] == "arn:aws:iam::1:role/r"


@pytest.mark.parametrize("key, needle", [
    ("access_key", "credentials never live in the configuration tree"),
    ("secret_key", "credentials never live in the configuration tree"),
    ("skips_credentials_validation", "`skip_credentials_validation`"),
    ("required_plugins", "a state backend has no plugins"),
])
def test_refused_s3_keys_name_what_to_do(key, needle):
    with pytest.raises(Exception) as exc:
        _s3(**{key: "x" if key != "required_plugins" else []})
    assert needle in str(exc.value) and "s3-x" in str(exc.value), str(exc.value)


@pytest.mark.parametrize("path", ["a/../b", "./x/./y", "..", "/"])
def test_a_local_backend_path_has_one_spelling(path):
    from cs_image_system.local_state_plugin.local_state_models import LocalStateBuilderModel
    with pytest.raises(Exception) as exc:
        LocalStateBuilderModel(name="loc", type="local", path=path)
    assert "loc" in str(exc.value)


def test_a_local_backend_path_that_is_fine_still_loads():
    from cs_image_system.local_state_plugin.local_state_models import LocalStateBuilderModel
    for path in ("state", "./state", "a/b/", "/var/lib/csis-state", ".", "./"):
        LocalStateBuilderModel(name="loc", type="local", path=path)


def test_a_state_backend_alias_binds(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "state-backends-3.yml", lambda d: _backend(d, "local-dev").update(aliases=["on-disk"]))
    _edit(root / "cfg" / "group-builders.yml",
          lambda d: next(b for b in d["group_builders"] if b["name"] == "oktagroups").update(
              state_configuration="on-disk"))
    stub_environment(monkeypatch)
    load_context(root)
    try:
        from cs_image_system.hashicorp_utils.collector import TerraformCollector
        reg = TerraformCollector().resolve_backend("on-disk")
        assert reg is not None and reg.name == "local-dev"
        from cs_image_system.base.commands.validate import check_state_locations
        from cs_image_system.base.global_context import GlobalTypeContext
        errors = [str(e) for e in check_state_locations(GlobalTypeContext())]
        assert not any("not declared" in e for e in errors), errors
    finally:
        reset_singletons()


def test_a_state_backends_declared_executable_must_exist(tmp_path: Path, monkeypatch):
    from cs_image_system.base.commands.validate import check_state_backend_executables
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "state-backends-3.yml",
          lambda d: _backend(d, "local-dev").update(executable="no-such-tofu"))
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        errors = [str(e) for e in check_state_backend_executables(ctx)]
        assert errors == ["Executable no-such-tofu specified for state backend local-dev not found in "
                          "executables list."], errors
    finally:
        reset_singletons()


def test_a_decrypted_backend_setting_is_written_as_its_ciphertext():
    from cs_image_system.base.encryption import Decrypted
    from cs_image_system.hashicorp_utils.collector import render_backend_value
    value = Decrypted("plain-profile", marker="ENC[age:QUJD]")
    assert render_backend_value(value) == '"ENC[age:QUJD]"'


# ------------------------------------------------------ 2. the AWS runtime

def _runtime(data: dict, name: str) -> dict:
    return next(r for r in data["runtime_builders"] if r["name"] == name)


def test_ena_and_sriov_reach_the_amazon_ebs_source_when_declared(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "runtime-builders.yml",
          lambda d: _runtime(d, "aws-east2-runtime").update(ena_support=True, sriov_support=False))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image"], apply=False).ok
        src = "".join(p.read_text() for p in run.generated.rglob("*source*.pkr.hcl") if "pckr-ebs-ans" in str(p))
        assert "ena_support = true" in src and "sriov_support = false" in src, src[:400]
    finally:
        run.restore_cwd()


def test_security_group_ids_is_refused(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "runtime-builders.yml",
          lambda d: _runtime(d, "aws-east2-runtime")["networking"].update(security_group_ids=["sg-1"]))
    stub_environment(monkeypatch)
    try:
        with pytest.raises(Exception) as exc:
            load_context(root)
        assert "security_group_ids" in str(exc.value)
    finally:
        reset_singletons()


def test_a_subnet_outside_the_vpc_is_refused(tmp_path: Path, monkeypatch):
    from cs_image_system.aws_runtime import aws_utils
    stub_environment(monkeypatch)
    real = aws_utils.get_vpc_map_and_default_vpc_id

    def with_subnets(session_config):
        vpcs, default, sgs = real(session_config)
        return ({v: {"subnets": [{"subnet_id": "subnet-somewhere-else"}]} for v in vpcs}, default, sgs)
    monkeypatch.setattr(aws_utils, "get_vpc_map_and_default_vpc_id", with_subnets)
    try:
        with pytest.raises(Exception) as exc:
            load_context(copy_config(tmp_path))
        assert "is not in VPC" in str(exc.value), str(exc.value)
    finally:
        reset_singletons()


def test_the_image_query_never_rewrites_the_entrys_own_query(tmp_path: Path, monkeypatch):
    import copy as _copy
    from cs_image_system.aws_runtime.aws_utils import remap_for_image_query
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    try:
        osb = ctx.os_builders["basic-rhel-9"]
        entry = next(e for e in osb.get_configs_for_image_builders().values()
                     if e.get_image_builder() == "pckr-ebs-ans")
        before = _copy.deepcopy(dict(entry.query))
        remap_for_image_query(entry)
        remap_for_image_query(entry)
        assert dict(entry.query) == before
    finally:
        reset_singletons()


# ------------------------------------------------------ 3. the GCP runtime

def test_query_images_returns_only_the_series_asked_about(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace
    from cs_image_system.gcloud_runtime import gcp_utils
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    real_query_images = GCPCloudBuilder.query_images      # the harness stubs it
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    try:
        images = [SimpleNamespace(name=n, status="READY", creation_timestamp="t", labels={"csis_series": s})
                  for n, s in (("a-1", "imgfile-basic-dask"), ("b-1", "basic-rh-10"), ("c-1", "someone-else"))]
        monkeypatch.setattr(gcp_utils, "_make_images_client",
                            lambda cfg: SimpleNamespace(list=lambda request: images))
        got = real_query_images(ctx.runtime_builders["gcloud-east1"], ["imgfile-basic-dask", "basic-rh-10"])
        assert sorted(i["name"] for i in got) == ["a-1", "b-1"], got
    finally:
        reset_singletons()


def test_a_tag_key_gce_cannot_take_is_refused_at_validate(tmp_path: Path, monkeypatch):
    from cs_image_system.base.commands.validate import check_label_keys
    root = copy_config(tmp_path)

    def edit(d):
        dask = next(i for i in d["images"] if i["name"] == "imgfile-basic-dask")
        dask.setdefault("tags", {})["2024"] = "cohort"
    _edit(root / "images" / "image1.yaml", edit)
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        errors = [str(e) for e in check_label_keys(ctx)]
        assert any("image 'imgfile-basic-dask': tag key '2024' on runtime gcloud-east1" in e for e in errors), errors
        assert not any("aws-east2-runtime" in e for e in errors), "AWS tags take any key"
    finally:
        reset_singletons()


def test_the_fixture_has_no_label_finding(tmp_path: Path, monkeypatch):
    from cs_image_system.base.commands.validate import check_label_keys
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    try:
        assert check_label_keys(ctx) == []
    finally:
        reset_singletons()


def test_a_disk_archive_script_without_a_project_is_refused_at_generation(tmp_path: Path, monkeypatch):
    from cs_image_system.base.models.storage import STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    try:
        pd = ctx.storage_builders["gcp-pd"]
        disk = next(s for s in ctx.storages if s.get_name() == "gce_data")
        monkeypatch.setattr(type(pd), "_project", lambda self: None)
        with pytest.raises(ValueError, match="the archive scripts need project"):
            pd.transition_actions(disk, STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED)
    finally:
        reset_singletons()
