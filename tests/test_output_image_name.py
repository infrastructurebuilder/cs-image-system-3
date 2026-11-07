# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0
"""A declared output image name.

``output_image_name`` is real at three levels, each overriding the one
above: the OS builder, its ``runtimes[]`` entry, and an image's
``runtimes[]`` entry. The declared value is the PREFIX of every build's
name; the run's timestamp is still appended. A tree that declares nothing
gets the default names (``<image>-<image builder>``, a base image
``<OS builder>-<runtime>``). ``validate`` refuses a prefix that carries the
run's timestamp (an ``execution.timestamp`` template, rendered at load),
two prefixes on one runtime of which one begins the other as the runtime
makes them (the ``<prefix>*`` lookups would cross; two that collapse to one
GCE name are the same case), and a full name the runtime cannot take
(AWS's AMI name rules; GCE's 63 characters). The frozen fixture declares
its names without the timestamp, and the golden carries them.

History: stage 105 (the names stage 22.3 had commented out).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from harness import FIXED_TIMESTAMP, copy_config, load_context, reset_singletons, stub_environment

REPO = Path(__file__).resolve().parents[1]
AWS, GCE = "aws-east2-runtime", "gcloud-east1"


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _image_entry(d, image: str, builder: str) -> dict:
    img = next(i for i in d["images"] if i["name"] == image)
    return next(r for r in img["runtimes"] if r.get("image_builder") == builder)


def _declare(root: Path, image: str, builder: str, prefix: str) -> None:
    """Declare ``output_image_name`` on one image's entry, in whichever
    file of the copy's ``images/`` holds the image."""
    for f in sorted((root / "images").glob("*.yaml")):
        if any(i.get("name") == image for i in (yaml.safe_load(f.read_text()) or {}).get("images", [])):
            _edit(f, lambda d: _image_entry(d, image, builder).update(output_image_name=prefix))
            return
    raise AssertionError(f"no image {image} in {root / 'images'}")


def _names(ctx, runtime: str) -> dict[str, tuple[str, bool]]:
    from cs_image_system.base.image_names import output_names_by_runtime
    return {who: (prefix, declared) for who, prefix, declared in output_names_by_runtime(ctx)[runtime]}


def _findings(ctx) -> list[str]:
    from cs_image_system.base.commands.validate import check_image_names
    return [str(e) for e in check_image_names(ctx)]


# ------------------------------------------------------------------ the field
def test_the_shadowing_property_is_gone_and_the_field_is_real_at_three_levels():
    from cs_image_system.base.models.base_image import BaseImageImageBuilderSubconfig
    from cs_image_system.base.models.image import ImageImageBuilderSubconfig
    from cs_image_system.base.models.os_builder_model import OsBuilderModel
    from cs_image_system.base.models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
    from cs_image_system.contract.operating_system import OsBuilderModelProtocol
    assert not isinstance(getattr(OSBuilderBaseImageBuilderSubconfig, "output_image_name", None), property)
    for cls in (OsBuilderModel, OSBuilderBaseImageBuilderSubconfig, ImageImageBuilderSubconfig, BaseImageImageBuilderSubconfig):
        assert "output_image_name" in cls.__dataclass_fields__, cls.__name__
    # the field and its getter are the kit model's (no plugin reads
    # them; the core does), not the protocol's
    assert "output_image_name" not in OsBuilderModelProtocol.__annotations__
    assert callable(getattr(OsBuilderModel, "get_output_image_name", None))


def test_the_fixture_declares_the_seven_names_without_a_timestamp():
    text = (REPO / "tests" / "fixtures" / "config" / "cfg" / "os-builders.yml").read_text()
    declared = re.findall(r'^\s+output_image_name: (".*")$', text, re.M)
    assert len(declared) == 7, declared
    assert not any("execution" in d for d in declared)
    assert not re.search(r"^\s+# output_image_name", text, re.M), "stage 22.3's commented lines are gone"


def test_the_fixtures_prefixes_resolve_as_declared_and_have_no_finding(tmp_path: Path, monkeypatch, caplog):
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    try:
        aws = _names(ctx, AWS)
        assert aws["OS builder 'my-deb-12'"] == ("AWS-aws-my-deb-12BB-debian-12", True)     # the entry's, over the builder's
        assert aws["OS builder 'basic-rhel-9'"] == ("NOSCSB-AWS-RHEL9-aws-my-rhel9", True)
        assert aws["OS builder 'basic-rh-10'"] == ("NOSCSB-AWS-RH10-basic-rh-10-aws-my-rhel8", True)
        assert aws["image 'imgfile-basic-dask'"] == ("imgfile-basic-dask-pckr-ebs-ans", False)
        gce = _names(ctx, GCE)
        assert gce["OS builder 'basic-rh-10'"] == ("noscsb-gcp-rh10-gcp-my-rh10", True)
        assert gce["image 'imgfile-basic-dask'"] == ("imgfile-basic-dask-pckr-gce-ans", False)
        with caplog.at_level(logging.INFO, logger="cs_image_system.base.commands.validate"):
            assert _findings(ctx) == []
        lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("image name:")]
        assert any("imgfile-basic-dask-pckr-ebs-ans-<timestamp>" in ln and AWS in ln and "declared" not in ln for ln in lines), lines
        assert any("NOSCSB-AWS-RH10-basic-rh-10-aws-my-rhel8-<timestamp>" in ln and "declared" in ln for ln in lines), lines
    finally:
        reset_singletons()


def test_a_tree_that_declares_nothing_keeps_todays_names(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    f = root / "cfg" / "os-builders.yml"
    f.write_text(re.sub(r"^\s+output_image_name: .*\n", "", f.read_text(), flags=re.M))
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        for runtime, who in ((AWS, "OS builder 'my-deb-12'"), (AWS, "OS builder 'basic-rh-10'"), (GCE, "OS builder 'basic-rh-10'")):
            osb = who.split("'")[1]
            assert _names(ctx, runtime)[who] == (f"{osb}-{runtime}", False)
        assert _names(ctx, AWS)["image 'imgfile-basic-dask-two'"] == ("imgfile-basic-dask-two-pckr-ebs-ans", False)
        assert _findings(ctx) == []
    finally:
        reset_singletons()


def test_the_os_builders_name_is_the_entrys_when_the_entry_names_none(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)

    def edit(d):
        osb = next(o for o in d["os_builders"] if o["name"] == "basic-rhel-9")
        osb["runtimes"][0].pop("output_image_name")
    _edit(root / "cfg" / "os-builders.yml", edit)
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        assert _names(ctx, AWS)["OS builder 'basic-rhel-9'"] == ("NOSCSB-basic-rhel-9-rhel-9", True)
    finally:
        reset_singletons()


def test_an_images_entry_names_its_builds_and_the_deferred_lookup(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _declare(root, "imgfile-basic-dask", "pckr-ebs-ans", "coops-dask-{{ this.name }}")
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        sub = ctx.images_map["imgfile-basic-dask"]._runtime_map[AWS]
        assert sub.get_image_output_name() == "coops-dask-pckr-ebs-ans"            # `this` is the entry
        # the timestamp tag stays in `_final_name` until the packer builder renders the run's values
        assert sub.get_final_name() == "coops-dask-pckr-ebs-ans-{{ execution.timestamp }}"
        from cs_image_system.packer_plugin.packer_image_builder import PackerEbsImageBuilder
        assert PackerEbsImageBuilder._final_name(ctx, sub) == f"coops-dask-pckr-ebs-ans-{FIXED_TIMESTAMP}"
        rtb = ctx.runtime_builders[AWS]
        psi = rtb.create_provider_specific_image_deferred(image=ctx.images_map["imgfile-basic-dask"], subconfig=sub)
        assert psi.deferred_name_pattern == "coops-dask-pckr-ebs-ans"
        assert ctx.images_map["imgfile-basic-dask"]._runtime_map[GCE].get_image_output_name() == "imgfile-basic-dask-pckr-gce-ans"
    finally:
        reset_singletons()


# ------------------------------------------------------------------ the rules
def test_a_template_naming_the_timestamp_is_refused(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    # an image's entry keeps the tag (the collections are not string-cycled); an OS builder's
    # entry in cfg/ has it rendered to the stamp at load. Both are the same refusal.
    _declare(root, "imgfile-basic-dask", "pckr-ebs-ans", "dask-{{ execution.timestamp }}")

    def edit(d):
        osb = next(o for o in d["os_builders"] if o["name"] == "basic-rhel-9")
        osb["runtimes"][0]["output_image_name"] = "rhel9-{{ execution.timestamp }}"
    _edit(root / "cfg" / "os-builders.yml", edit)
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        found = _findings(ctx)
        assert len(found) == 2, found
        img = next(f for f in found if f.startswith("image 'imgfile-basic-dask'"))
        assert AWS in img and "dask-{{ execution.timestamp }}" in img and FIXED_TIMESTAMP in img
        osb = next(f for f in found if f.startswith("OS builder 'basic-rhel-9'"))
        assert f"rhel9-{FIXED_TIMESTAMP}" in osb
        assert all("execution.timestamp" in f for f in found)       # the remedy is named
    finally:
        reset_singletons()


def test_a_template_nothing_renders_is_refused(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _declare(root, "imgfile-basic-dask", "pckr-ebs-ans", "dask-{{ nobody.home }}")
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        found = _findings(ctx)
        assert len(found) == 1 and "nobody.home" in found[0], found
    finally:
        reset_singletons()


def test_a_prefix_that_begins_anothers_on_one_runtime_is_refused(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _declare(root, "imgfile-basic-dask-two", "pckr-ebs-ans", "imgfile-basic-dask-pckr-ebs-ans-two")
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        found = _findings(ctx)
        assert len(found) == 1, found
        assert found[0].startswith("image 'imgfile-basic-dask' and image 'imgfile-basic-dask-two'")
        assert AWS in found[0] and "'imgfile-basic-dask-pckr-ebs-ans-two'" in found[0]
    finally:
        reset_singletons()


def test_two_names_that_collapse_to_one_gce_name_are_refused_and_aws_keeps_case(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _declare(root, "imgfile-basic-dask", "pckr-gce-ans", "NOSCSB.GCP.RH10.GCP.MY.RH10")
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        found = _findings(ctx)
        assert len(found) == 1, found
        assert f"OS builder 'basic-rh-10' and image 'imgfile-basic-dask' on runtime {GCE}" in found[0]
        assert "collapse" in found[0]
        assert ctx.runtime_builders[GCE].image_name_as_made("NOSCSB.GCP.RH10.GCP.MY.RH10") == "noscsb-gcp-rh10-gcp-my-rh10"
        assert ctx.runtime_builders[AWS].image_name_as_made("NOSCSB.GCP") == "NOSCSB.GCP"
    finally:
        reset_singletons()


def test_a_name_the_runtime_cannot_take_is_refused_naming_the_rule(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)

    _declare(root, "imgfile-basic-dask", "pckr-ebs-ans", "dask:head")
    _declare(root, "imgfile-basic-dask", "pckr-gce-ans", "x" * 60)
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        found = _findings(ctx)
        assert len(found) == 2, found
        aws = next(f for f in found if f"on runtime {AWS}" in f)
        assert f"'dask:head-{FIXED_TIMESTAMP}'" in aws and "':'" in aws
        gce = next(f for f in found if f"on runtime {GCE}" in f)
        assert "63" in gce
    finally:
        reset_singletons()


def test_the_runtime_rules_themselves():
    from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
    aws_rule = __import__("cs_image_system.aws_runtime.aws_runtime_builders", fromlist=["AwsCloudBuilder"]).AwsCloudBuilder.image_name_problem
    gce_rule = __import__("cs_image_system.gcloud_runtime.gcp_runtime_builders", fromlist=["GCPCloudBuilder"]).GCPCloudBuilder.image_name_problem
    short = aws_rule(None, "ab")
    assert short and "3 to 128" in short and "'ab'" in short
    assert "3 to 128" in (aws_rule(None, "a" * 129) or "")
    assert aws_rule(None, "Fine (name) [v1] a.b/c-d'e@f_g") is None
    assert gce_rule(None, "Any Case Is Fine-20260826-120000") is None
    assert gce_rule(None, "a" * 64) is not None
    assert RuntimeBuilderBase.image_name_problem(None, "anything at all!") is None            # type: ignore[arg-type]
    assert RuntimeBuilderBase.image_name_as_made(None, "As Is") == "As Is"                   # type: ignore[arg-type]


# ------------------------------------------------------------------ the docs
def test_the_docs_say_how_a_build_is_named():
    conf = (REPO / "docs" / "CONFIGURATION.md").read_text()
    assert conf.count("| `output_image_name` |") == 3, "the field at its three levels"
    ops = (REPO / "docs" / "OPERATIONS.md").read_text()
    assert "How an image is named" in ops and "`<prefix>*`" in ops
    daily = " ".join((REPO / "docs" / "DAILY_DRIVER.md").read_text().split())
    assert "How an image is named" in daily          # the operations section, by its title
