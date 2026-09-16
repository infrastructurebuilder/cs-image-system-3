# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""EXPLORE "GCP support", increments 1 and 2: the packer builder is
provider-neutral (the runtime plugin owns the source type, the source block
and the manifest artifact id) and a ``packer-gce`` builder bakes on a GCE
runtime with ``googlecompute``.

The fixture is the AWS tree plus a GCE overlay applied in a temp copy, so
the AWS golden stays byte-identical (checked by the gate tests).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, copy_config

from cs_image_system.gcloud_runtime.gcp_packer_source import gce_label, gce_name

GCE_RUNTIME = "gcloud-east1"
GCE_BUILDER = "pckr-gce-ans"


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def gce_overlay(root: Path) -> None:
    """Bind basic-rh-10 (base) and imgfile-basic-dask (instance image) to a
    packer-gce builder on the fixture's gcloud-east1 runtime. Idempotent:
    the real fixture carries these entries since GCP readiness (2026-09-02),
    so every append is skipped when its target already exists."""
    def image_builders(d):
        if any(b.get("name") == GCE_BUILDER for b in d["image_builders"]):
            return
        d["image_builders"].append({
            "name": GCE_BUILDER, "type": "packer-gce", "runtime": GCE_RUNTIME,
            "executable": "packer",
            "required_plugins": [
                {"name": "googlecompute", "source": "github.com/hashicorp/googlecompute", "version": ">= 1.0.0"},
                {"name": "ansible", "source": "github.com/hashicorp/ansible", "version": ">= 1.0.0"},
            ]})
    _edit(root / "cfg" / "image-builders.yml", image_builders)

    def os_builders(d):
        for osb in d["os_builders"]:
            if osb["name"] == "basic-rh-10":
                if any(r.get("name") == "gcp-my-rh10" for r in osb["runtimes"]):
                    return
                osb["runtimes"].append({
                    "name": "gcp-my-rh10", "image_builder": GCE_BUILDER,
                    "output_image_name": "noscsb-gcp-rh10-{{ this.name }}-{{ execution.timestamp }}",
                    "owners": ["rhel-cloud"],
                    "query": {"filters": {"name": "rhel-8-*"}}})
    _edit(root / "cfg" / "os-builders.yml", os_builders)

    def base_images(d):
        for b in d["base_images"]:
            if b["name"] == "basic-rh-10":
                if any(r.get("name") == "gcp-my-rh10" for r in b["runtimes"]):
                    return
                b["runtimes"].append({
                    "name": "gcp-my-rh10", "runtime": GCE_RUNTIME,
                    "output_image_name": "GCP-RH10-{{ this.name }}-{{ execution.timestamp }}",
                    "owners": ["rhel-cloud"], "query": {"filters": {"name": "rhel-8-*"}}})
    _edit(root / "base_images" / "base-images1.yaml", base_images)

    def images(d):
        for i in d["images"]:
            if i["name"] == "imgfile-basic-dask":
                if any(r.get("image_builder") == GCE_BUILDER for r in i["runtimes"]):
                    return
                i["runtimes"].append({"image_builder": GCE_BUILDER})
    _edit(root / "images" / "image1.yaml", images)


@pytest.fixture
def gce(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    gce_overlay(root)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        yield run
    finally:
        run.restore_cwd()


def _find(generated: Path, needle: str, name_glob: str = "*.pkr.hcl") -> list[Path]:
    return sorted(p for p in generated.rglob(name_glob) if needle in p.read_text())


def test_gce_names_and_labels_are_valid():
    assert gce_name("NOSCSB-AWS-RHEL8-basic-rh-10-20260826_120000") == "noscsb-aws-rhel8-basic-rh-10-20260826-120000"
    assert gce_name("8ball") == "i-8ball"
    assert len(gce_name("x" * 100)) == 63
    assert gce_label("Project=My Project") == "project-my-project"


def test_runtime_plugins_own_the_packer_source_type(gce):
    ctx = gce.ctx
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    aws = next(b for b in ctx.runtime_builders.values() if isinstance(b, AwsCloudBuilder))
    gcp = ctx.runtime_builders[GCE_RUNTIME]
    assert isinstance(gcp, GCPCloudBuilder)
    assert aws.packer_source_type() == "amazon-ebs" and gcp.packer_source_type() == "googlecompute"
    assert aws.build_id_from_artifact("us-east-2:ami-0abc") == "ami-0abc"
    assert gcp.build_id_from_artifact("noscsb-gcp-rh10-basic-rh-10-20260826-120000") == \
        "noscsb-gcp-rh10-basic-rh-10-20260826-120000"
    ib = ctx.image_builders[GCE_BUILDER]
    assert ib.get_packer_source_type() == "googlecompute"
    assert ctx.image_builders["pckr-ebs-ans"].get_packer_source_type() == "amazon-ebs"


def test_base_image_bakes_with_googlecompute(gce):
    summary = gce.run("base-image", apply=False)
    assert summary.ok, summary.error
    srcs = _find(gce.generated / "base-image", 'source "googlecompute" "basic-rh-10"')
    assert len(srcs) == 1, srcs
    text = srcs[0].read_text()
    assert 'source_image = "debian-11-v1"' in text            # the stubbed vendor lookup
    assert "source_image_project_id" in text and '"debian-cloud"' in text
    assert 'image_family = "basic-rh-10"' in text              # series == family
    assert 'image_name = "basic-rh-10-gcloud-east1-20260826-120000"' in text
    assert re.search(r'csis_series\s+= "basic-rh-10"', text) and re.search(r'csis_parent\s+= "vendor"', text)
    assert "ami_name" not in text and "amazon-ami" not in text
    builds = _find(gce.generated / "base-image", 'source.googlecompute.basic-rh-10')
    assert len(builds) == 1
    build = builds[0].read_text()
    assert 'only   = ["googlecompute.basic-rh-10"]' in build   # V2 provisioners follow the source type
    assert "amazon-ebs" not in build
    # the AWS bake of the same base image is untouched
    aws = _find(gce.generated / "base-image", 'source "amazon-ebs" "basic-rh-10"')
    assert len(aws) == 1 and "googlecompute" not in aws[0].read_text()


def test_instance_image_bakes_from_the_series_family(gce):
    summary = gce.run(["base-image", "instance-image"], apply=False)
    assert summary.ok, summary.error
    srcs = _find(gce.generated / "instance-image", 'source "googlecompute" "imgfile-basic-dask"')
    assert len(srcs) == 1, srcs
    text = srcs[0].read_text()
    # deferred parent (no manifest in a dry run): GCE resolves the family itself
    assert 'source_image_family = "basic-rh-10"' in text
    # per-runtime machine_type (finding 41): the dask bake declares e2-medium
    # (1-2 GB machines OOM under the dask mods), never the literal "default"
    assert 'machine_type = "e2-medium"' in text
    builds = _find(gce.generated / "instance-image", 'source.googlecompute.imgfile-basic-dask')
    assert len(builds) == 1
    build = builds[0].read_text()
    # the ansible modification and the V2 activation target the GCE source
    assert 'only = ["googlecompute.imgfile-basic-dask"]' in build
    assert 'only   = ["googlecompute.imgfile-basic-dask"]' in build
    assert "amazon-ebs" not in build


def test_per_runtime_tests_override_lands_in_the_gce_bake(gce):
    """Finding 40: the GCE bake's in-bake verification uses the runtime
    entry's tests, not the builder-level (AWS-shaped) spec -- asserted on
    the EMITTED commands because the first implementation extended the
    wrong subconfig class and no test caught it."""
    assert gce.run(["base-image"], apply=False).ok
    gce_build = "\n".join(p.read_text() for p in
                          (gce.generated / "base-image" / GCE_BUILDER).rglob("*build.pkr.hcl"))
    assert "rpm -q google-guest-agent" in gce_build
    assert "nfs-utils" not in gce_build
    aws_build = "\n".join(p.read_text() for p in
                          (gce.generated / "base-image" / "pckr-ebs-ans").rglob("*build.pkr.hcl"))
    assert "rpm -q nfs-utils" in aws_build  # builder-level tests still govern AWS


def test_gce_bake_disk_size_comes_from_the_runtime(gce):
    """Finding 51: an instance's boot disk is exactly its image's disk, and
    the OS builder's 200 GB default cost ~$8/month per instance. The GCE
    runtime's default_disk_size sizes every bake on it (base and instance
    images alike), asserted on the emitted sources."""
    assert gce.run(["base-image", "instance-image"], apply=False).ok
    rt = yaml.safe_load((gce.config_root / "cfg" / "runtime-builders.yml").read_text())
    size = next(r["default_disk_size"] for r in rt["runtime_builders"] if r["name"] == GCE_RUNTIME)
    assert 0 < int(size) < 200                            # the fixture declares a small bake disk
    for lifecycle, name in (("base-image", "basic-rh-10"), ("instance-image", "imgfile-basic-dask")):
        srcs = _find(gce.generated / lifecycle, f'source "googlecompute" "{name}"')
        assert len(srcs) == 1, (lifecycle, srcs)
        assert re.search(rf"disk_size\s*=\s*{int(size)}\b", srcs[0].read_text()), (lifecycle, name)
        assert "disk_size = 200" not in srcs[0].read_text()


def test_gce_attached_disk_device_name_matches_the_mounted_by_id_path(gce):
    """Finding 50 (found live on gce-test): the disk was attached as
    device_name "gce_data" while the startup script mounted
    /dev/disk/by-id/google-gce-data -- GCE exposes "google-<device_name>",
    so the script died at the missing device and nothing was mounted. The
    attachment and the mount path now share one sanitization."""
    assert gce.run(["instance-image"], apply=False).ok
    root = gce.generated / "instance-image" / "tofu-gce" / "instance-generation"
    module = (root / "tofu-gce-instance-generation-instance-gce_test.tf").read_text()
    assert re.search(r'"?device_name"?\s*=\s*"gce-data"', module), module
    assert not re.search(r'"?device_name"?\s*=\s*"gce_data"', module)   # the old, mismatched name
    template = (root / "user-data-gce_test.sh.tftpl").read_text()
    assert "/dev/disk/by-id/google-gce-data" in template
    assert "/mnt/gce-data" in template and "mkfs" in template


def test_gce_bakes_end_with_the_finalize_provisioner(gce):
    """Finding 47: every GCE bake's LAST provisioner guarantees the build
    user's google-sudoers membership, so the guest agent's first-boot
    removal of the stale bake user cannot abort metadata key provisioning
    (found live: the gce-test launch refused every SSH/IAP session).
    Asserted on the EMITTED commands, per the finding-40 lesson."""
    assert gce.run(["base-image", "instance-image"], apply=False).ok
    for lifecycle in ("base-image", "instance-image"):
        gce_build = "\n".join(p.read_text() for p in
                              (gce.generated / lifecycle / GCE_BUILDER).rglob("*build.pkr.hcl"))
        assert "runtime bake finalization (gcloud-east1)" in gce_build, lifecycle
        assert "gpasswd -a" in gce_build and "google-sudoers" in gce_build, lifecycle
        # verification stays ahead of finalization: assertions judge the image
        assert gce_build.rindex("runtime bake finalization") > gce_build.rindex("in-bake verification"), lifecycle
        aws_build = "\n".join(p.read_text() for p in
                              (gce.generated / lifecycle / "pckr-ebs-ans").rglob("*build.pkr.hcl"))
        assert "google-sudoers" not in aws_build, lifecycle  # AWS bakes untouched


def test_iap_runtimes_bake_through_the_iap_tunnel(gce):
    """Finding 54 (found live): packer reached the build VM over its external
    IP on tcp:22, which only worked while the default VPC's default-allow-ssh
    rule existed; deleting that rule (deliberate hygiene) timed out every
    bake. On an IAP runtime the bake tunnels like sessions do."""
    assert gce.run(["base-image", "instance-image"], apply=False).ok
    for lifecycle, name in (("base-image", "basic-rh-10"), ("instance-image", "imgfile-basic-dask")):
        text = _find(gce.generated / lifecycle, f'source "googlecompute" "{name}"')[0].read_text()
        assert re.search(r"use_iap\s*=\s*true", text), (lifecycle, name)
        assert "omit_external_ip" not in text            # egress for dnf/pip still needs the ephemeral IP
    aws = _find(gce.generated / "base-image", 'source "amazon-ebs" "basic-rh-10"')[0].read_text()
    assert "use_iap" not in aws


def test_runtimes_without_iap_do_not_ask_for_the_tunnel(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    gce_overlay(root)
    def runtimes(d):
        for r in d["runtime_builders"]:
            if r["name"] == GCE_RUNTIME:
                r["session_mechanism"] = None
    _edit(root / "cfg" / "runtime-builders.yml", runtimes)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image"], apply=False).ok
        text = _find(run.generated / "base-image", 'source "googlecompute" "basic-rh-10"')[0].read_text()
        assert "use_iap" not in text
    finally:
        run.restore_cwd()
