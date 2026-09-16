# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""GCP increment 3 (PLAN.md): pd / filestore / gcs storage plugins, the GCE
instance plugin, IAP session parity and per-runtime base-image
prerequisites -- all proven by generation over a GCE overlay of the AWS
fixture (nothing reaches GCP) plus a local `tofu validate` of the
generated GCE roots when tofu is installed.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.test_v2_explore_gcp import GCE_RUNTIME, _edit, _find, gce_overlay
from tests.v2_support import REPO, V2Run, copy_config


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


def test_gate1_prerequisites_are_per_runtime(gce3):
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


def test_gates_2_3_storage_roots(gce3):
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


def test_gate4_instance_root_and_launch_parameters(gce3):
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


def test_gate6_state_query_hooks_exist(gce3):
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    ctx = gce3.ctx
    gcp = ctx.runtime_builders[GCE_RUNTIME]
    assert isinstance(gcp, GCPCloudBuilder)
    assert gcp.session_mechanism() == "iap"
    assert callable(getattr(gcp, "query_images"))
    pd = ctx.storage_builders["gcp-pd"]
    assert callable(getattr(pd, "_lookup"))
    fs = ctx.storage_builders["gcp-filestore"]
    with pytest.raises(NotImplementedError):
        fs._lookup(next(s for s in ctx.storages if s.get_name() == "gce_share"))


@pytest.mark.skipif(shutil.which("tofu") is None, reason="tofu not installed")
def test_generated_gce_roots_validate_with_tofu(gce3, tmp_path):
    summary = gce3.run(["identity", "storage", "base-image", "instance-image"], apply=False)
    assert summary.ok, summary.error
    # module_source_base is ../tfmodules relative to the config root
    link = gce3.config_root.parent / "tfmodules"
    if not link.exists():
        os.symlink(REPO / "tfmodules", link)
    roots = [gce3.generated / "storage" / "gcp-pd", gce3.generated / "storage" / "gcp-filestore",
             gce3.generated / "storage" / "gcp-gcs", gce3.generated / "instance-image" / "tofu-gce"]
    for r in roots:
        wd = next(p.parent for p in r.rglob("*.tf"))
        for args in (["init", "-backend=false", "-input=false", "-no-color"], ["validate", "-no-color"]):
            res = subprocess.run(["tofu", *args], cwd=wd, capture_output=True, text=True, timeout=600)
            assert res.returncode == 0, f"{wd}: tofu {args[0]}\n{res.stdout}\n{res.stderr}"
