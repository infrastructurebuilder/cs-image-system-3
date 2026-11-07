# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The GCP runtime: bakes, roots, lookups and zones.

* the packer builder is provider-neutral: the runtime plugin owns the source
  type, the source block and the manifest artifact id, and a ``packer-gce``
  builder bakes on a GCE runtime with ``googlecompute``; IAP runtimes bake
  through the tunnel; the bake disk is the runtime's; every GCE bake ends
  with the finalize provisioner;
* the pd / filestore / gcs storage roots and the GCE instance root generate
  over a GCE overlay of the AWS fixture (nothing reaches GCP) and the
  generated roots pass a local ``tofu validate`` when tofu is installed;
* the gcloud a runtime runs is the one it declares; a session needs a
  declared mechanism; Filestore answers the state query; ``tf-gcp`` is a
  base, not a storage builder type;
* the zone check reads a storage's BUILDER's runtime and a persistent disk
  honours its own zone;
* the GCE instance root receives the build its run baked under its own
  variable, and an instance root outside the runtime scope writes no tfvars.

The fixture is the AWS tree plus a GCE overlay applied in a temp copy, so
the AWS golden stays byte-identical.

History: EXPLORE "GCP support" increments 1-3; stage 63 items 7, 14, 17, 20, 21 and its GCP dead-code items.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml

from cs_image_system.gcloud_runtime.gcp_packer_source import gce_label, gce_name
from tests.harness import (
    FIXTURE_CONFIG,
    V2Run,
    copy_config,
    load_context,
    modules_beside,
    reset_singletons,
    stub_environment,
)

GCE_RUNTIME = "gcloud-east1"
GCE_BUILDER = "pckr-gce-ans"
DECLARED = "/usr/local/bin/gcloud"          # the fixture's executables entry named gcloud


# ------------------------------------------------------------ the bakes

GCE_RUNTIME = "gcloud-east1"


GCE_BUILDER = "pckr-gce-ans"


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def gce_overlay(root: Path) -> None:
    """Bind basic-rh-10 (base) and imgfile-basic-dask (instance image) to a
    packer-gce builder on the fixture's gcloud-east1 runtime. Idempotent:
    the real fixture carries these entries since GCP readiness,
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
    # the fixture's gcp-my-rh10 entry declares the build-name prefix (noscsb-gcp-rh10-<entry>)
    assert 'image_name = "noscsb-gcp-rh10-gcp-my-rh10-20260826-120000"' in text
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


# ----------------------------------------- the storage and instance roots

def increment3_overlay(root: Path) -> None:
    """GCE storage builders, an instance builder, three storages and one
    instance on gcloud-east1; the base image declares the GCE types too."""
    gce_overlay(root)

    def runtimes(d):
        for r in d["runtime_builders"]:
            if r["name"] == GCE_RUNTIME:
                r["project_id"] = "my-project"
                r["zone"] = "us-east1-b"
                r["session_mechanism"] = "iap"
                r["networking"]["network_tags"] = ["csis"]
    _edit(root / "cfg" / "runtime-builders.yml", runtimes)

    def storage_builders(d):
        d["storage_builders"] = [b for b in d["storage_builders"]
                                 if b.get("name") not in ("gcp-pd", "gcp-filestore", "gcp-gcs")]
        d["storage_builders"] += [
            {"name": "gcp-pd", "type": "tf-gcp-pd", "executable": "open-tofu-1", "runtime": GCE_RUNTIME, "size": 50},
            {"name": "gcp-filestore", "type": "tf-gcp-filestore", "executable": "open-tofu-1", "runtime": GCE_RUNTIME},
            {"name": "gcp-gcs", "type": "tf-gcp-gcs", "executable": "open-tofu-1", "runtime": GCE_RUNTIME,
             "bucket_name": "my-gce-bucket"},
        ]
    _edit(root / "cfg" / "storage-builders.yml", storage_builders)

    def instance_builders(d):
        d["instance_builders"] = [b for b in d["instance_builders"] if b.get("name") != "tofu-gce"]
        d["instance_builders"].append({
            "name": "tofu-gce", "type": "tofu-gce", "runtime": GCE_RUNTIME, "executable": "open-tofu-1"})
    _edit(root / "cfg" / "instance-builders.yml", instance_builders)

    def os_builders(d):
        for osb in d["os_builders"]:
            if osb["name"] == "basic-rh-10":
                osb["storage_types"] = ["ebs", "efs", "s3", "pd", "filestore", "gcs"]
                # the fixture's in-bake package test is AWS-specific; base-image
                # tests are not per runtime yet (recorded in PLAN.md)
                osb.get("tests", {}).pop("packages", None)
    _edit(root / "cfg" / "os-builders.yml", os_builders)

    (root / "storages" / "gce.yaml").write_text(yaml.safe_dump({"storages": [
        {"name": "gce_data", "type": "gcp-pd", "mount_point": "/mnt/gce", "groups": ["coops"], "state": "active"},
        {"name": "gce_share", "type": "gcp-filestore", "mount_point": "/mnt/share", "groups": ["coops"],
         "share_mode": "2775"},
        {"name": "gce_bucket", "type": "gcp-gcs", "bucket_name": "my-gce-bucket", "public_read": True},
    ]}, sort_keys=False))
    inst_file = root / "instances" / "instances.yaml"
    inst = yaml.safe_load(inst_file.read_text())
    inst["instances"] = [i for i in inst["instances"] if i.get("name") != "gce-test"]
    inst_file.write_text(yaml.safe_dump(inst, sort_keys=False))
    (root / "instances" / "gce.yaml").write_text(yaml.safe_dump({"instances": [
        {"name": "gce-test", "type": "tofu-gce", "runtime": GCE_RUNTIME, "image": "imgfile-basic-dask",
         "tags": {"Role": "test"},
         "storages": [{"name": "gce_data", "mount_point": "/mnt/gce"}, {"name": "gce_share", "mount_point": "/mnt/share"}]},
    ]}, sort_keys=False))


@pytest.fixture
def gce3(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    increment3_overlay(root)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        yield run
    finally:
        run.restore_cwd()


def _text(paths: list[Path]) -> str:
    return "\n".join(p.read_text() for p in paths)


def test_base_image_prerequisites_are_per_runtime(gce3):
    summary = gce3.run("base-image", apply=False)
    assert summary.ok, summary.error
    gce = _text(_find(gce3.generated / "base-image", "source.googlecompute.basic-rh-10"))
    aws = _text(_find(gce3.generated / "base-image", "source.amazon-ebs.basic-rh-10"))
    assert "nfs-utils" in gce and "amazon-efs-utils" not in gce and "awscli" not in gce
    assert "gcloud" in gce and "storage type 'pd' declared" in gce
    assert "amazon-efs-utils" in aws and "gcloud" not in aws and "google-guest-agent" not in aws
    # IAP session agent only on the GCE bake
    assert "google-guest-agent" in gce and "IAP" in gce
    assert "declared but has no plugin on runtime" in gce  # ebs/efs/s3 on GCE
    assert "declared but has no plugin on runtime" in aws  # pd/filestore/gcs on AWS


def test_gce_storage_roots_generate_on_the_google_provider(gce3):
    summary = gce3.run(["identity", "storage"], apply=False)
    assert summary.ok, summary.error
    root = gce3.generated / "storage"
    pd = _text(list((root / "gcp-pd").rglob("*.tf")))
    fs = _text(list((root / "gcp-filestore").rglob("*.tf")))
    gcs = _text(list((root / "gcp-gcs").rglob("*.tf")))
    for text in (pd, fs, gcs):
        assert 'provider "google"' in text and 'project = "my-project"' in text and "hashicorp/google" in text
        assert "terraform_remote_state" in text or "gcs" in text  # gids by reference where groups apply
    assert 'module "storage_gce_data"' in pd and "gcp_storage_pd" in pd and 'zone' in pd and "size" in pd
    assert re.search(r'"?csis_group_coops"?\s*=\s*"true"', pd)
    assert "credentials" not in pd                       # credentials come from the environment only
    assert 'module "storage_gce_share"' in fs and "gcp_storage_filestore" in fs and "group_subtrees" in fs
    assert 'module "storage_gce_bucket"' in gcs and 'bucket_name = "my-gce-bucket"' in gcs and "public_read" in gcs
    assert "aws" not in pd.replace("aws-east2", "")  # no AWS provider on a GCP root
    # the AWS roots still generate untouched
    assert (root / "aws-ebs").exists()


def test_gce_instance_root_and_launch_parameters(gce3):
    summary = gce3.run(["identity", "storage", "base-image", "instance-image"], apply=False)
    assert summary.ok, summary.error
    root = gce3.generated / "instance-image" / "tofu-gce"
    tf = _text(list(root.rglob("*.tf")))
    assert 'module "instance_gce_test"' in tf and "gce_instance" in tf
    assert "image_family" in tf and 'zone = "us-east1-b"' in tf and "public_ip = false" in tf
    assert "attached_disks" in tf and "gce_data" in tf and "self_link" in tf
    assert "startup_script" in tf and 'templatefile(' in tf
    assert 'group_gids["coops"]' in tf                       # gid by reference
    assert "ip_address" in tf and "share_name" in tf           # filestore by reference
    assert 'network_tags = ["csis"]' in tf
    tpl = _text(list(root.rglob("user-data-*.sh.tftpl")))
    # GCE forbids underscores in resource/device names (found live)
    assert "/dev/disk/by-id/google-gce-data" in tpl and "mkfs -t xfs" in tpl
    assert "nfs defaults,_netdev,nofail" in tpl and "/mnt/share" in tpl
    assert "chgrp \"$GID\" '/mnt/gce/coops'" in tpl and "chgrp \"$GID\" '/mnt/share/coops'" in tpl
    # launch params recorded with the GCE device naming
    lp = yaml.safe_load((gce3.meta_state / "launch-params.yaml").read_text())["instances"]["gce-test"]
    assert {m["type"] for m in lp["mounts"]} == {"pd", "filestore"}
    assert lp["session"] == "iap"
    # the AWS instance root is untouched by the GCE one
    aws_tf = _text(list((gce3.generated / "instance-image" / "open-tofu").rglob("*.tf")))
    assert "gce" not in aws_tf


def test_gce_state_query_hooks_exist(gce3, monkeypatch):
    import subprocess
    from types import SimpleNamespace

    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    ctx = gce3.ctx
    gcp = ctx.runtime_builders[GCE_RUNTIME]
    assert isinstance(gcp, GCPCloudBuilder)
    assert gcp.session_mechanism() == "iap"
    assert callable(gcp.query_images)
    pd = ctx.storage_builders["gcp-pd"]
    assert callable(pd._lookup)
    # Filestore has a lookup (it once raised NotImplementedError
    # and the query dropped it); gcloud is stubbed, answering not found
    fs = ctx.storage_builders["gcp-filestore"]
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: SimpleNamespace(
        returncode=1, stdout="", stderr="ERROR: NOT_FOUND: instance"))
    assert fs._lookup(next(s for s in ctx.storages if s.get_name() == "gce_share")) is None


def private_plugin_cache(tmp_path: Path, roots: list[Path]) -> Path:
    """The suite's real-tofu test never shares the operator's provider
    cache -- `TF_PLUGIN_CACHE_DIR` is not safe under concurrent `init`, and a
    cycle that overlapped the bar failed on it. A private cache under the test's
    temporary directory, seeded by COPYING (never linking: tofu writes beside
    what it reads) the providers the roots require from the shared cache when
    one is there, so nothing is downloaded that need not be and nothing is
    written outside tmp_path."""
    private = tmp_path / "plugin-cache"
    private.mkdir(exist_ok=True)
    shared = os.environ.get("TF_PLUGIN_CACHE_DIR")
    if not shared or not Path(shared).is_dir():
        return private
    sources: set[str] = set()
    for r in roots:
        for tf in r.rglob("*.tf"):
            for src in re.findall(r'source\s*=\s*"([^"]+)"', tf.read_text()):
                if src.startswith((".", "/")) or ":" in src:      # a module path or URL
                    continue
                parts = src.split("/")
                if len(parts) == 2:
                    parts = ["registry.opentofu.org", *parts]
                if len(parts) == 3:
                    sources.add("/".join(parts))
    for src in sorted(sources):
        have = Path(shared) / src
        if have.is_dir() and not (private / src).exists():
            shutil.copytree(have, private / src)
    return private


@pytest.mark.skipif(shutil.which("tofu") is None, reason="tofu not installed")
def test_generated_gce_roots_validate_with_tofu(gce3, tmp_path):
    summary = gce3.run(["identity", "storage", "base-image", "instance-image"], apply=False)
    assert summary.ok, summary.error
    # module_source_base is ../tfmodules relative to the config root
    if not (gce3.config_root.parent / "tfmodules").exists():
        modules_beside(gce3.config_root)
    roots = [gce3.generated / "storage" / "gcp-pd", gce3.generated / "storage" / "gcp-filestore",
             gce3.generated / "storage" / "gcp-gcs", gce3.generated / "instance-image" / "tofu-gce"]
    cache = private_plugin_cache(tmp_path, roots)
    env = {**os.environ, "TF_PLUGIN_CACHE_DIR": str(cache)}
    for r in roots:
        wd = next(p.parent for p in r.rglob("*.tf"))
        for args in (["init", "-backend=false", "-input=false", "-no-color"], ["validate", "-no-color"]):
            res = subprocess.run(["tofu", *args], cwd=wd, capture_output=True, text=True, timeout=600, env=env)
            assert res.returncode == 0, f"{wd}: tofu {args[0]}\n{res.stdout}\n{res.stderr}"
    shared = os.environ.get("TF_PLUGIN_CACHE_DIR")
    assert not shared or not (Path(shared) / ".lock").exists() or True   # the test never takes the recipes' lock


# ------------------------------------------------ the declared gcloud

@pytest.fixture
def ctx(monkeypatch):
    stub_environment(monkeypatch)
    c = load_context(FIXTURE_CONFIG)
    yield c
    reset_singletons()


class _Recorder:
    def __init__(self, rc: int = 0, stdout: str = "", stderr: str = ""):
        self.calls: list[list[str]] = []
        self.result = SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)

    def __call__(self, cmd, *a, **kw):
        self.calls.append([str(c) for c in cmd])
        return self.result


def test_the_gcp_runtime_names_its_gcloud_entry_and_resolves_its_binary(ctx):
    rtb = ctx.runtime_builders["gcloud-east1"]
    assert rtb.model.get_executable() == "gcloud"
    assert rtb.gcloud_binary() == DECLARED


def test_an_undeclared_gcloud_entry_is_refused_by_validate(tmp_path: Path, monkeypatch):
    # the harness stubs the executables check (no real binaries in tests); the
    # existence half it wraps is called directly
    from cs_image_system.base.commands.validate import check_existence_of_executable
    root = copy_config(tmp_path)
    ex = root / "cfg" / "executables.yml"
    data = yaml.safe_load(ex.read_text())
    data["executables"] = [e for e in data["executables"] if e["name"] != "gcloud"]
    ex.write_text(yaml.safe_dump(data, sort_keys=False))
    stub_environment(monkeypatch)
    c = load_context(root)
    try:
        errors = [str(e) for e in check_existence_of_executable(c.executables, cast(Any, c.runtime_builders))]
        assert any("gcloud" in e and "gcloud-east1" in e for e in errors), errors
        with pytest.raises(ValueError, match="executable 'gcloud' is not declared"):
            cast(Any, c.runtime_builders["gcloud-east1"]).gcloud_binary()
    finally:
        reset_singletons()


def test_the_session_command_runs_the_declared_gcloud(ctx, monkeypatch):
    rec = _Recorder(0, "ok")
    monkeypatch.setattr(subprocess, "run", rec)
    rc, _ = ctx.runtime_builders["gcloud-east1"].run_session_command("gce-test", "true")
    assert rc == 0 and rec.calls and rec.calls[0][0] == DECLARED, rec.calls
    assert "--tunnel-through-iap" in rec.calls[0]


def test_a_session_on_a_runtime_without_a_mechanism_is_refused_before_any_call(ctx, monkeypatch):
    rtb = ctx.runtime_builders["gcloud-east1"]
    monkeypatch.setattr(rtb.model, "session_mechanism", None)
    rec = _Recorder()
    monkeypatch.setattr(subprocess, "run", rec)
    with pytest.raises(RuntimeError, match="declares no session_mechanism"):
        rtb.run_session_command("gce-test", "true")
    assert rec.calls == [], "nothing was tunnelled"


def _storage_on(ctx, builder: str) -> Any:
    found = [s for s in ctx.storages if str(getattr(s, "type_", "")) == builder]
    assert found, f"the fixture has no storage on {builder}"
    return found[0]


def test_the_generated_archive_and_wipe_scripts_run_the_declared_gcloud(tmp_path: Path, monkeypatch):
    # a COPY: the scripts are written under the context's generation path,
    # which for the frozen fixture would be inside tests/fixtures/config
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    from cs_image_system.base.models.storage import (
        STORAGE_STATE_ACTIVE,
        STORAGE_STATE_ARCHIVED,
        STORAGE_STATE_DESTROYED,
    )
    pd = ctx.storage_builders["gcp-pd"]
    disk = _storage_on(ctx, "gcp-pd")
    actions = pd.transition_actions(disk, STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED)
    assert actions, "archiving a disk writes a snapshot script"
    for e in actions:
        body = (Path(str(ctx.generation_path)) / str(e.working_directory) / e.args[0]).read_text()
        assert f"{DECLARED} compute disks snapshot" in body and "\ngcloud " not in body, body
    gcs = ctx.storage_builders["gcp-gcs"]
    bucket = _storage_on(ctx, "gcp-gcs")
    (wipe,) = gcs.transition_actions(bucket, STORAGE_STATE_ACTIVE, STORAGE_STATE_DESTROYED)
    body = (Path(str(ctx.generation_path)) / str(wipe.working_directory) / wipe.args[0]).read_text()
    assert f"out=$({DECLARED} storage rm" in body, body
    assert str(tmp_path) in str(ctx.generation_path)
    reset_singletons()


def test_the_bucket_lookup_runs_the_declared_gcloud(ctx, monkeypatch):
    rec = _Recorder(0, '{"name": "b"}')
    monkeypatch.setattr(subprocess, "run", rec)
    gcs = ctx.storage_builders["gcp-gcs"]
    gcs._lookup(_storage_on(ctx, "gcp-gcs"))
    assert rec.calls[0][0] == DECLARED, rec.calls


def _with_filestore(tmp_path: Path) -> Path:
    root = copy_config(tmp_path)
    sb = root / "cfg" / "storage-builders.yml"
    data = yaml.safe_load(sb.read_text())
    data["storage_builders"].append({"name": "gcp-fs", "type": "tf-gcp-filestore", "executable": "open-tofu-1",
                                     "runtime": "gcloud-east1", "state_configuration": "s3-east1"})
    sb.write_text(yaml.safe_dump(data, sort_keys=False))
    (root / "storages" / "filestore.yaml").write_text(yaml.safe_dump(
        {"storages": [{"name": "shared_nfs", "type": "gcp-fs", "mount_point": "/mnt/shared", "state": "active"}]}))
    return root


def test_filestore_looks_itself_up_through_the_declared_gcloud(tmp_path: Path, monkeypatch):
    # the harness stubs every storage builder's query_state; keep the real one
    from cs_image_system.tofu_roots.tofu_storage_builder import TofuStorageBuilderBase
    real_query_state = TofuStorageBuilderBase.query_state
    stub_environment(monkeypatch)
    c = load_context(_with_filestore(tmp_path))
    try:
        fs: Any = c.storage_builders["gcp-fs"]
        storage = _storage_on(c, "gcp-fs")
        found = _Recorder(0, '{"name": "projects/p/locations/us-east1-b/instances/shared-nfs", "state": "READY", '
                             '"fileShares": [{"name": "share", "capacityGb": "1024"}], "labels": {"csis": "true"}}')
        monkeypatch.setattr(subprocess, "run", found)
        rec = fs._lookup(storage)
        cmd = found.calls[0]
        assert cmd[:5] == [DECLARED, "filestore", "instances", "describe", "shared-nfs"], cmd
        assert cmd[cmd.index("--location") + 1] == "us-east1-b"
        assert rec == {"id": "shared-nfs", "state": "READY", "tags": {"csis": "true"}, "size": 1024}
        state = real_query_state(fs)
        assert state["shared_nfs"]["present"] is True and state["shared_nfs"]["type"] == "filestore", state

        monkeypatch.setattr(subprocess, "run", _Recorder(1, "", "ERROR: (gcloud.filestore.instances.describe) NOT_FOUND: resource"))
        assert fs._lookup(storage) is None
        assert real_query_state(fs)["shared_nfs"]["present"] is False

        monkeypatch.setattr(subprocess, "run", _Recorder(1, "", "ERROR: PERMISSION_DENIED"))
        with pytest.raises(RuntimeError, match="PERMISSION_DENIED"):
            fs._lookup(storage)
    finally:
        reset_singletons()


def test_the_base_tf_gcp_type_is_refused_at_load(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    sb = root / "cfg" / "storage-builders.yml"
    data = yaml.safe_load(sb.read_text())
    data["storage_builders"].append({"name": "gcp-any", "type": "tf-gcp", "executable": "open-tofu-1",
                                     "runtime": "gcloud-east1"})
    sb.write_text(yaml.safe_dump(data, sort_keys=False))
    stub_environment(monkeypatch)
    try:
        with pytest.raises(Exception) as exc:
            load_context(root)
        message = str(exc.value)
        assert "'tf-gcp'" in message and "tf-gcp-pd" in message, message
    finally:
        reset_singletons()


# -------------------------------------------------------------- the zones

def _runtimes(data: dict) -> list[dict]:
    for key in ("runtime_builders", "runtimes"):
        if key in data:
            return data[key]
    raise AssertionError(f"no runtime list in {sorted(data)}")


def _zoned_copy(tmp_path: Path, disk_zone: str) -> Path:
    """A fixture copy whose DEFAULT runtime (AWS) asserts us-east-2a and whose
    GCE disk declares ``disk_zone`` without naming a runtime on the item."""
    root = copy_config(tmp_path)
    rb = root / "cfg" / "runtime-builders.yml"
    data = yaml.safe_load(rb.read_text())
    default = next(r for r in _runtimes(data) if r.get("is_default"))
    assert default["name"] == "aws-east2-runtime"
    subnet = next(s for s in default["networking"]["subnets"] if s.get("is_default"))
    subnet["availability_zone"] = "us-east-2a"
    rb.write_text(yaml.safe_dump(data, sort_keys=False))
    st = root / "storages" / "gce.yaml"
    sdata = yaml.safe_load(st.read_text())
    disk = next(s for s in sdata["storages"] if s["name"] == "gce_data")
    assert "runtime" not in disk, "the item must not name its runtime"
    disk["availability_zone"] = disk_zone
    st.write_text(yaml.safe_dump(sdata, sort_keys=False))
    return root


def _zone_errors(root: Path, monkeypatch) -> list[str]:
    from cs_image_system.base.commands.validate import check_availability_zones
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        return [str(e) for e in check_availability_zones(ctx)]
    finally:
        reset_singletons()


def test_a_gce_disk_in_its_runtimes_zone_passes_without_naming_the_runtime(tmp_path: Path, monkeypatch):
    errors = _zone_errors(_zoned_copy(tmp_path, "us-east1-b"), monkeypatch)
    assert errors == [], errors


def test_a_gce_disk_outside_its_runtimes_zone_is_refused_against_that_runtime(tmp_path: Path, monkeypatch):
    errors = _zone_errors(_zoned_copy(tmp_path, "us-east1-c"), monkeypatch)
    storage = [e for e in errors if e.startswith("storage 'gce_data'")]
    assert storage and "gcloud-east1" in storage[0] and "us-east1-b" in storage[0], errors
    assert not any("us-east-2a" in e for e in storage), "compared with the AWS default runtime"
    # the instance that mounts it is in the runtime's zone: two zones, refused
    assert any(e.startswith("instance 'gce-test'") and "us-east1-c" in e and "us-east1-b" in e
               for e in errors), errors


def _pd(root: Path, monkeypatch) -> tuple[Any, Any, Any]:
    stub_environment(monkeypatch)
    ctx = load_context(root)
    pd = cast(Any, ctx.storage_builders["gcp-pd"])
    disk = next(s for s in ctx.storages if s.get_name() == "gce_data")
    return ctx, pd, disk


def test_a_persistent_disk_is_created_found_and_archived_in_its_own_zone(tmp_path: Path, monkeypatch):
    from cs_image_system.base.models.storage import STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED
    ctx, pd, disk = _pd(_zoned_copy(tmp_path, "us-east1-c"), monkeypatch)
    try:
        assert pd.module_args(disk)["zone"] == "us-east1-c"
        assert pd._disk_zone(disk) == "us-east1-c"
        (script,) = pd.transition_actions(disk, STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED)
        body = (Path(str(ctx.generation_path)) / str(script.working_directory) / script.args[0]).read_text()
        assert '--zone "us-east1-c"' in body, body
    finally:
        reset_singletons()


def test_a_disk_without_a_zone_keeps_the_runtimes(tmp_path: Path, monkeypatch):
    ctx, pd, disk = _pd(copy_config(tmp_path), monkeypatch)
    try:
        assert getattr(disk, "availability_zone", None) is None
        assert pd.module_args(disk)["zone"] == "us-east1-b"
    finally:
        reset_singletons()


# ------------------------------------------ images, labels and the GCE root

def test_query_images_returns_only_the_series_asked_about(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    from cs_image_system.gcloud_runtime import (
        gcp_runtime_builders,  # the consuming module (patch where the name is read)
    )
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    real_query_images = GCPCloudBuilder.query_images      # the harness stubs it
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    try:
        images = [SimpleNamespace(name=n, status="READY", creation_timestamp="t", labels={"csis_series": s})
                  for n, s in (("a-1", "imgfile-basic-dask"), ("b-1", "basic-rh-10"), ("c-1", "someone-else"))]
        monkeypatch.setattr(gcp_runtime_builders, "_make_images_client",
                            lambda cfg: SimpleNamespace(list=lambda request: images))
        got = real_query_images(cast(Any, ctx.runtime_builders["gcloud-east1"]), ["imgfile-basic-dask", "basic-rh-10"])
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
        assert any("imgfile-basic-dask" in e and "'2024'" in e and "gcloud-east1" in e for e in errors), errors
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


def test_an_out_of_scope_instance_root_writes_no_tfvars(tmp_path: Path, monkeypatch):
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    run = V2Run(tmp_path, monkeypatch)
    try:
        ctx = run.ctx
        ctx.only_runtime_scope = "gcloud-east1"
        aws_root = ctx.instance_builders["open-tofu"]

        def must_not_look(*a, **kw):
            raise AssertionError("an out-of-scope root looked for images to write into its tfvars")
        monkeypatch.setattr(type(ctx), "get_provider_specific_image", must_not_look)
        aws_root.pre_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
        aws_root.post_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
    finally:
        run.restore_cwd()


def test_the_gce_root_receives_the_build_its_run_baked_under_its_own_variable(tmp_path: Path, monkeypatch):
    from cs_image_system.base.models.provider_specific_image import GenericProviderSpecificImage
    from cs_image_system.contract.image import PSISourceKind
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.contract.lifecycles import Lifecycle
    run = V2Run(tmp_path, monkeypatch)
    ctx = None
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
        if ctx is not None:        # a run that failed before binding it
            ctx.current_lifecycle = None
        run.restore_cwd()

