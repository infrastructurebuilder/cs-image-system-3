# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The packer sources a bake is emitted from: what an OS builder's entry, the
runtime and an image's declarations put into them.

* ``ena_support``/``sriov_support`` reach the amazon-ebs source when
  declared; ``security_group_ids`` is refused; the image query never
  rewrites the entry's own query;
* an entry's ``image_id`` pins the vendor image and skips the query;
  ``image_name`` on an entry is refused; the entry's disk size is the bake
  disk; an entry's ``config`` reaches its own templates; an unsupported
  RHEL major is refused at load;
* an image's ``variables`` become packer variables, typed; one packer
  cannot take is refused by name; two images giving one variable the same
  value declare it once and different values are refused; an image
  builder's machine type sits between the entry and the runtime;
* a packer string default is quoted and a ``QString`` prints quoted.

History: stage 63 dead-code items 2, 4, 5 and 10, low-hanging item 3.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness import V2Run, copy_config, load_context, stub_environment


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


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
    with pytest.raises(Exception) as exc:
        load_context(root)
    assert "security_group_ids" in str(exc.value)


def test_the_image_query_never_rewrites_the_entrys_own_query(tmp_path: Path, monkeypatch):
    import copy as _copy

    from cs_image_system.aws_runtime.aws_utils import translate_image_query
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    osb = ctx.os_builders["basic-rhel-9"]
    entry = next(e for e in osb.get_configs_for_image_builders().values()
                 if e.get_image_builder() == "pckr-ebs-ans")
    before = _copy.deepcopy(dict(entry.query))
    translate_image_query(entry.image_query())          # the effective query is a new object
    translate_image_query(entry.image_query())
    assert dict(entry.query) == before


# ------------------------------------------------- the OS builder's entry

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
    with pytest.raises(Exception) as exc:
        load_context(root)
    assert "image_name" in str(exc.value)


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
    osb = ctx.os_builders["basic-rhel-9"]
    entry = list(osb.get_configs_for_image_builders().values())[0]
    assert entry.get_description() == "bake from-the-entry"
    assert entry.get_config() == {"label": "from-the-entry"}


def test_an_unsupported_rhel_major_is_refused_at_load_whatever_the_policy(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)

    def edit(d):
        o = next(x for x in d["os_builders"] if x["name"] == "basic-rhel-9")
        o["family_version"] = "7"
        o["update"] = {"policy": "none"}
    _edit(root / "cfg" / "os-builders.yml", edit)
    stub_environment(monkeypatch)
    with pytest.raises(Exception) as exc:
        load_context(root)
    assert "Unsupported RHEL version" in str(exc.value)


# ------------------------------------------------------ packer variables

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


# --------------------------------------------------------- HCL rendering

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


def test_a_qstring_is_quoted_by_default_and_prints():
    from cs_image_system.hashicorp_utils.hashicorp import QString
    q = QString("abc")
    assert q.quoted is True and str(q) == '"abc"' and q == "abc"
    assert str(QString("abc", quoted=False)) == "abc"

