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


# ------------------------------------------------------ 4. the default OS plugin

def _osb_entry(data: dict, osb: str, image_builder: str) -> dict:
    """The OS builder's entry for an image builder; basic-rhel-9's only entry
    names it as `default`, so the first entry stands in for it."""
    o = next(x for x in data["os_builders"] if x["name"] == osb)
    return next((e for e in o["runtimes"] if e.get("image_builder") == image_builder), o["runtimes"][0])


def test_an_entry_image_id_pins_the_vendor_image_and_skips_the_query(tmp_path: Path, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "os-builders.yml",
          lambda d: _osb_entry(d, "basic-rhel-9", "pckr-ebs-ans").update(image_id="ami-0pinnedvendor0"))
    asked: list[str] = []

    def by_id(self, entry, image_id):
        asked.append(image_id)
        return (image_id, "amazon", {"ImageId": image_id, "RootDeviceName": "/dev/sda1"})
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    monkeypatch.setattr(AwsCloudBuilder, "query_provider_image_by_id", by_id)
    try:
        assert run.run(["base-image"], apply=False).ok
        assert asked == ["ami-0pinnedvendor0"]
        src = "".join(p.read_text() for p in run.generated.rglob("*source-basic-rhel-9*.pkr.hcl"))
        assert "ami-0pinnedvendor0" in src, src[:300]
    finally:
        run.restore_cwd()


def test_image_name_on_an_entry_is_refused(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "os-builders.yml",
          lambda d: _osb_entry(d, "basic-rhel-9", "pckr-ebs-ans").update(image_name="RHEL-9*"))
    stub_environment(monkeypatch)
    try:
        with pytest.raises(Exception) as exc:
            load_context(root)
        assert "image_name" in str(exc.value)
    finally:
        reset_singletons()


def test_the_entry_disk_size_is_the_bake_disk_and_the_fingerprints(tmp_path: Path, monkeypatch):
    from cs_image_system.base.lineage import bake_disk_size
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "os-builders.yml",
          lambda d: _osb_entry(d, "basic-rhel-9", "pckr-ebs-ans").update(default_primary_disk_size=150))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        ctx = run.ctx
        rhel9 = ctx.os_builders["basic-rhel-9"]
        assert bake_disk_size(ctx, rhel9, "aws-east2-runtime") == 150
        assert bake_disk_size(ctx, ctx.os_builders["basic-rh-10"], "aws-east2-runtime") == 200   # the OS builder's
        assert bake_disk_size(ctx, ctx.os_builders["basic-rh-10"], "gcloud-east1") == 10          # the runtime wins
        assert run.run(["base-image"], apply=False).ok
        src = "".join(p.read_text() for p in run.generated.rglob("*source-basic-rhel-9*.pkr.hcl"))
        assert "volume_size           = 150" in src or "volume_size = 150" in src, src
    finally:
        run.restore_cwd()


def test_an_entry_config_reaches_its_own_templates(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "os-builders.yml",
          lambda d: _osb_entry(d, "basic-rhel-9", "pckr-ebs-ans").update(
              config={"label": "from-the-entry"}, description="bake {{ config.label }}"))
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        osb = ctx.os_builders["basic-rhel-9"]
        entry = list(osb.get_configs_for_image_builders().values())[0]
        assert entry.get_description() == "bake from-the-entry"
        assert entry.get_config() == {"label": "from-the-entry"}
    finally:
        reset_singletons()


def test_an_unsupported_rhel_major_is_refused_at_load_whatever_the_policy(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)

    def edit(d):
        o = next(x for x in d["os_builders"] if x["name"] == "basic-rhel-9")
        o["family_version"] = "7"
        o["update"] = {"policy": "none"}
    _edit(root / "cfg" / "os-builders.yml", edit)
    stub_environment(monkeypatch)
    try:
        with pytest.raises(Exception) as exc:
            load_context(root)
        assert "Unsupported RHEL version" in str(exc.value)
    finally:
        reset_singletons()


def test_a_bare_update_policy_name_stays_refused():
    from cs_image_system.base.models.update_policy import UpdatePolicy
    with pytest.raises(ValueError, match="must be a mapping"):
        UpdatePolicy.from_config("none")


# ------------------------------------------------------ 5. the packer plugin

def _image_vars(root: Path, image: str, variables: dict) -> None:
    def edit(d):
        next(i for i in d["images"] if i["name"] == image)["variables"] = variables
    _edit(root / "images" / "image1.yaml", edit)


def test_image_variables_become_packer_variables(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _image_vars(root, "imgfile-basic-dask", {"dask_flavor": "standard", "workers": 4, "gpu": False})
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        text = "".join(p.read_text() for p in run.generated.rglob("*-vars.pkr.hcl") if "instance-image" in str(p))
        assert 'variable "dask_flavor"' in text and 'default = "standard"' in text, text
        assert 'variable "workers"' in text and "type = number" in text and "default = 4" in text, text
        assert 'variable "gpu"' in text and "default = false" in text, text
    finally:
        run.restore_cwd()


@pytest.mark.parametrize("key, value, needle", [
    ("tiers", ["a", "b"], "must be a string, number or bool"),
    ("9lives", "x", "is not a packer variable name"),
])
def test_an_image_variable_packer_cannot_take_is_refused(key, value, needle):
    from cs_image_system.packer_plugin.packer_builder import image_packer_variable
    with pytest.raises(ValueError) as exc:
        image_packer_variable("imgfile-basic-dask", key, value)
    assert needle in str(exc.value) and "imgfile-basic-dask" in str(exc.value)


def test_two_images_giving_one_variable_the_same_value_declare_it_once(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _image_vars(root, "imgfile-basic-dask", {"flavour": "same"})
    _image_vars(root, "imgfile-data-science", {"flavour": "same"})
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
    finally:
        run.restore_cwd()


def test_two_images_giving_one_variable_different_values_are_refused(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _image_vars(root, "imgfile-basic-dask", {"flavour": "a"})
    _image_vars(root, "imgfile-data-science", {"flavour": "b"})
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["base-image", "instance-image"], apply=False)
        assert not summary.ok and "flavour" in str(summary.error), summary.error
    finally:
        run.restore_cwd()

def test_an_image_builders_machine_type_sits_between_the_entry_and_the_runtime(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "image-builders.yml",
          lambda d: next(b for b in d["image_builders"] if b["name"] == "pckr-gce-ans").update(
              default_machine_type="e2-highmem-2"))

    def drop_entry_machine(d):
        dask = next(i for i in d["images"] if i["name"] == "imgfile-basic-dask")
        for r in dask.get("runtimes") or []:
            r.pop("machine_type", None)
            r.pop("default_machine_type", None)
    _edit(root / "images" / "image1.yaml", drop_entry_machine)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        src = "".join(p.read_text() for p in run.generated.rglob("*source-imgfile-basic-dask*.pkr.hcl")
                      if "pckr-gce-ans" in str(p))
        assert "e2-highmem-2" in src, src
    finally:
        run.restore_cwd()


# ------------------------------------------------------ 6. the ansible plugin

def _mod_builder(data: dict, name: str) -> dict:
    return next(b for b in data["mod_builders"] if b["name"] == name)


def test_ansible_strings_are_escaped_and_the_user_override_wins(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "mod-builders.yml", lambda d: _mod_builder(d, "ansible-default").update(
        extra_arguments=['--extra-vars', 'motd="hello"'], configuration_user="deployer"))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        text = "".join(p.read_text() for p in run.generated.rglob("*build.pkr.hcl") if "instance-image" in str(p))
        assert '"motd=\\"hello\\""' in text, "a quote inside an argument is escaped"
        assert 'user = "deployer"' in text and 'user = "packer"' not in text, "configuration_user wins"
    finally:
        run.restore_cwd()


def test_a_missing_playbook_is_refused_at_generation(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)

    def edit(d):
        dask = next(i for i in d["images"] if i["name"] == "imgfile-basic-dask")
        mod = next(m for m in dask["modifications"] if m.get("playbooks"))
        mod["playbooks"] = ["no-such-playbook.yml"]
    _edit(root / "images" / "image1.yaml", edit)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["base-image", "instance-image"], apply=False)
        assert not summary.ok and "no-such-playbook.yml" in str(summary.error), summary.error
    finally:
        run.restore_cwd()


def test_a_modification_with_no_builder_and_no_default_is_a_named_refusal(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "mod-builders.yml", lambda d: _mod_builder(d, "ansible-default").update(is_default=False))
    stub_environment(monkeypatch)
    try:
        with pytest.raises(Exception) as exc:
            load_context(root)
        # refused by name at load (the builder-list check fires first; the
        # orchestrator's own refusal covers an item that reaches it anyway),
        # never an AttributeError at generation
        message = str(exc.value)
        assert ("names no builder" in message or "No default builder found in mod_builder list" in message), message
    finally:
        reset_singletons()


# ------------------------------------------------------ 7. the bash plugin

def test_bash_configuration_user_runs_the_lines_as_that_user(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "mod-builders.yml",
          lambda d: _mod_builder(d, "bash-remote").update(configuration_user="modder"))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        text = "".join(p.read_text() for p in run.generated.rglob("*build.pkr.hcl") if "instance-image" in str(p))
        assert "sudo su - modder -c" in text, "the shell provisioner runs the item as the user"
    finally:
        run.restore_cwd()


def test_bash_configuration_user_and_execute_command_together_are_refused():
    from cs_image_system.bash_mod_plugin.bash_models import BashModBuilderModel
    with pytest.raises(Exception, match="declare one"):
        BashModBuilderModel(name="b", type="bash-remote", configuration_user="u", execute_command="x")


def test_bash_extra_arguments_is_refused():
    from cs_image_system.bash_mod_plugin.bash_models import BashModBuilderModel
    with pytest.raises(Exception, match="extra_arguments"):
        BashModBuilderModel(name="b", type="bash-remote", extra_arguments=["-x"])


def test_the_on_image_bundle_replays_the_ensure_lines_first(tmp_path: Path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        scripts = [p for p in run.generated.rglob("inline.sh") if "derivative-setup" in str(p)]
        assert scripts, "the bundle carries the derivative-setup item"
        body = scripts[0].read_text()
        assert "for p in git;" in body and body.index("for p in git;") < body.index("echo 'derivative setup'"), body
    finally:
        run.restore_cwd()


# ------------------------------------------------------ 8. the okta plugin

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
