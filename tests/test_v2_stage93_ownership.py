# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 93: everything the system makes carries its configuration's id,
and the inventories count this configuration's alone.

The walk's F47 and F53: two configurations in one project or account each
saw the other's storages as leftovers (`cloud-empty`) or as foreign
(`state query`), and a declared storage's volume or a machine was found by
its Name across the whole account. Now every module call tags or labels
its thing `csis_config`; a lookup by name takes ours or an unlabelled one
and never another configuration's; the emptiness check leaves another's
alone and says so; `lineage relabel` gives the id to what stands without
it.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.v2_support import V2Run, copy_config

OURS = "cs-image-action-test"          # the fixture's top-level id
THEIRS = "cs-image-system-walk"
AWS = "aws-east2-runtime"
GCE = "gcloud-east1"


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path), dry_run=False)
    try:
        yield r
    finally:
        r.restore_cwd()


def _aws_tags(d: dict[str, str]) -> list[dict[str, str]]:
    return [{"Key": k, "Value": v} for k, v in d.items()]


# ------------------------------------------------------------ 1. everything carries the id

def test_every_storage_and_instance_module_call_carries_the_id(run):
    assert run.run(["storage", "instance-image"], apply=False).ok
    calls = [p for p in run.generated.rglob("*.tf") if "storage-generation" in str(p) or "instance-generation" in str(p)]
    assert calls
    missing = []
    for p in calls:
        text = p.read_text()
        if "module \"" in text and ("tags" in text or "labels" in text) and f'"csis_config" = "{OURS}"' not in text:
            missing.append(str(p.relative_to(run.generated)))
    assert not missing, missing


# ------------------------------------------------------------ 2. lookups take ours, never theirs

def test_an_ebs_volume_of_our_name_that_is_theirs_is_absent_and_noted(run, monkeypatch):
    from cs_image_system.base import state_query as sq
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuEbsStorageBuilder

    class FakeEC2:
        volumes: list[dict[str, Any]] = []

        def describe_volumes(self, Filters):
            name = next(f["Values"][0] for f in Filters if f["Name"] == "tag:Name")
            return {"Volumes": [v for v in self.volumes if dict((t["Key"], t["Value"]) for t in v["Tags"]).get("Name") == name]}

        def describe_snapshots(self, **kw):
            return {"Snapshots": []}

        def create_tags(self, Resources, Tags):
            self.tagged = (Resources, Tags)
    ec2 = FakeEC2()
    monkeypatch.setattr(TofuEbsStorageBuilder, "_aws_client", lambda self, service: ec2)
    sb = next(b for b in run.ctx.storage_builders.values() if isinstance(b, TofuEbsStorageBuilder))
    storage = next(s for s in sb.model._storages)
    name = storage.get_name()
    theirs = {"VolumeId": "vol-theirs", "State": "in-use", "Size": 100, "Tags": _aws_tags({"Name": name, "csis_config": THEIRS})}
    ours = {"VolumeId": "vol-ours", "State": "available", "Size": 100, "Tags": _aws_tags({"Name": name, "csis_config": OURS})}
    legacy = {"VolumeId": "vol-legacy", "State": "available", "Size": 100, "Tags": _aws_tags({"Name": name})}
    FakeEC2.volumes = [theirs, ours]
    assert sb._lookup(storage)["id"] == "vol-ours"                       # ours wins over theirs
    FakeEC2.volumes = [theirs, legacy]
    assert sb._lookup(storage)["id"] == "vol-legacy"                     # unlabelled is still taken for ours
    FakeEC2.volumes = [theirs]
    rec = sb._lookup(storage)
    assert rec == {"present": False, "elsewhere": THEIRS, "what": "an EBS volume"}
    # the harness stubs every storage builder's query_state; this one asks its lookups for real
    def real_query_state(self):
        return {s.get_name(): {"present": (r := self._lookup(s)) is not None, "type": self.capability_type(), **(r or {})}
                for s in self.model._storages}
    monkeypatch.setattr(TofuEbsStorageBuilder, "query_state", real_query_state)
    report = sq.StateReport(run="r")
    found = sq.query_storages(run.ctx, report)
    assert found[name]["present"] is False
    assert any(n.startswith(f"storages/{name}: an EBS volume of that name belongs to configuration '{THEIRS}'")
               for n in report.notes), (report.notes, report.unavailable, found[name])
    # relabel adds the id to a standing volume that lacks it
    FakeEC2.volumes = [legacy]
    assert sb.retag_storage(storage, {"csis_config": OURS}) is True
    assert ec2.tagged == (["vol-legacy"], [{"Key": "csis_config", "Value": OURS}])


def test_an_s3_bucket_of_our_name_that_is_theirs_is_absent(run, monkeypatch):
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuS3StorageBuilder

    class FakeS3:
        tags: dict[str, str] = {}
        put: dict[str, Any] = {}

        def get_bucket_tagging(self, Bucket):
            return {"TagSet": _aws_tags(self.tags)}

        def get_bucket_lifecycle_configuration(self, Bucket):
            return {"Rules": []}

        def put_bucket_tagging(self, Bucket, Tagging):
            self.put = {Bucket: {t["Key"]: t["Value"] for t in Tagging["TagSet"]}}
    s3 = FakeS3()
    monkeypatch.setattr(TofuS3StorageBuilder, "_aws_client", lambda self, service: s3)
    sb = next(b for b in run.ctx.storage_builders.values() if isinstance(b, TofuS3StorageBuilder))
    storage = next(s for s in sb.model._storages)
    FakeS3.tags = {"csis_config": THEIRS}
    assert sb._lookup(storage) == {"present": False, "elsewhere": THEIRS, "what": "an S3 bucket"}
    FakeS3.tags = {"team": "x"}
    assert sb._lookup(storage)["state"] == "active"
    assert sb.retag_storage(storage, {"csis_config": OURS}) is True
    assert list(s3.put.values())[0] == {"team": "x", "csis_config": OURS}      # merged, never replaced


def test_aws_machine_lookups_skip_another_configurations_machine(run, monkeypatch):
    from cs_image_system.aws_runtime import aws_utils
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder

    class FakeEC2:
        instances: list[dict[str, Any]] = []

        def describe_instances(self, Filters):
            name = next(f["Values"][0] for f in Filters if f["Name"] == "tag:Name")
            found = [i for i in self.instances if dict((t["Key"], t["Value"]) for t in i["Tags"]).get("Name") == name]
            return {"Reservations": [{"Instances": found}] if found else []}

        def create_tags(self, Resources, Tags):
            self.tagged = (Resources, Tags)
    ec2 = FakeEC2()
    monkeypatch.setattr(aws_utils, "ec2_client", lambda cfg: ec2)
    rtb = run.ctx.runtime_builders[AWS]
    assert isinstance(rtb, AwsCloudBuilder)
    theirs = {"InstanceId": "i-theirs", "ImageId": "ami-theirs", "State": {"Name": "running"},
              "Tags": _aws_tags({"Name": "test2", "csis_config": THEIRS})}
    FakeEC2.instances = [theirs]
    assert rtb.query_instance_boot_image("test2") is None                 # theirs is not ours to read
    assert rtb.query_instance_power_state("test2") == "absent"
    assert rtb.running_instance_id("test2") is None
    legacy = {"InstanceId": "i-legacy", "ImageId": "ami-legacy", "State": {"Name": "running"}, "Tags": _aws_tags({"Name": "test2"})}
    FakeEC2.instances = [theirs, legacy]
    assert rtb.query_instance_boot_image("test2") == "ami-legacy"         # unlabelled: still ours
    assert rtb.instance_tags("test2") == {"Name": "test2"}
    assert rtb.retag_instance("test2", {"csis_config": OURS}) is True
    assert ec2.tagged == (["i-legacy"], [{"Key": "csis_config", "Value": OURS}])


def test_gce_lookups_and_inventory_tell_ours_from_theirs(run, monkeypatch):
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    rtb = run.ctx.runtime_builders[GCE]
    assert isinstance(rtb, GCPCloudBuilder)
    assert rtb._theirs(SimpleNamespace(labels={"csis_config": THEIRS}))
    assert not rtb._theirs(SimpleNamespace(labels={"csis_config": OURS}))
    assert not rtb._theirs(SimpleNamespace(labels={}))
    # a machine of our name whose labels are theirs reads as absent
    class Client:
        def get(self, project, zone, instance):
            return SimpleNamespace(status="RUNNING", labels={"csis_config": THEIRS}, hostname="", id="1")
    monkeypatch.setattr(GCPCloudBuilder, "_instances_client", lambda self: (Client(), "p", "z"))
    assert rtb.query_instance_power_state("gce-test") == "absent"
    assert rtb.query_instance_identity("gce-test") is None
    assert rtb.instance_tags("gce-test") == {"csis_config": THEIRS}


def test_emptiness_leaves_another_configurations_things_alone_and_names_the_unlabelled(run, monkeypatch):
    from cs_image_system.base.commands.runtime_facts import emptiness
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    monkeypatch.setattr(GCPCloudBuilder, "inventory", lambda self: {
        "instances": ["walk-gce-1", "scratch"], "images": ["team-node-x"],
        "disks": ["gce-data", "their-data", "old-scratch"], "buckets": ["csis-sandbox-86233086783-default-bucket", "their-bucket"],
        "owners": {"instances": {"walk-gce-1": THEIRS, "scratch": OURS}, "images": {"team-node-x": THEIRS},
                   "disks": {"their-data": THEIRS, "gce-data": OURS}, "buckets": {"their-bucket": THEIRS}}})
    result = emptiness(GCE)
    assert result["leftovers"] == {"instances": ["scratch"], "images": [], "disks": ["old-scratch"], "buckets": []}
    assert result["elsewhere"] == {"instances": {THEIRS: 1}, "images": {THEIRS: 1}, "disks": {THEIRS: 1}, "buckets": {THEIRS: 1}}
    assert result["unlabelled"] == {"disks": ["old-scratch"]}
    assert not result["empty"]
    # with nothing of ours beyond the declared storages, theirs alone does not make the runtime un-empty
    monkeypatch.setattr(GCPCloudBuilder, "inventory", lambda self: {
        "instances": ["walk-gce-1"], "images": [], "disks": ["gce-data"], "buckets": ["csis-sandbox-86233086783-default-bucket"],
        "owners": {"instances": {"walk-gce-1": THEIRS}}})
    result = emptiness(GCE)
    assert result["empty"] and result["elsewhere"] == {"instances": {THEIRS: 1}}


# ------------------------------------------------------------ 3. relabel learns the new kinds

def test_relabel_gives_the_id_to_standing_storages_and_machines_that_lack_it(run, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.base.commands.relabel import relabel, relabel_plan
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import (
        TofuEbsStorageBuilder, TofuEfsStorageBuilder, TofuS3StorageBuilder)
    monkeypatch.setattr(AwsCloudBuilder, "query_images", lambda self, series: [])
    ebs = next(b for b in run.ctx.storage_builders.values() if isinstance(b, TofuEbsStorageBuilder))
    ebs_name = next(s.get_name() for s in ebs.model._storages)
    monkeypatch.setattr(TofuEbsStorageBuilder, "query_state", lambda self: {
        ebs_name: {"present": True, "type": "ebs", "id": "vol-legacy", "tags": {"Name": ebs_name}}})
    monkeypatch.setattr(TofuEfsStorageBuilder, "query_state", lambda self: {
        s.get_name(): {"present": True, "type": "efs", "id": "fs-1", "tags": {"csis_config": OURS}} for s in self.model._storages})
    monkeypatch.setattr(TofuS3StorageBuilder, "query_state", lambda self: {
        s.get_name(): {"present": True, "type": "s3", "id": "b", "tags": {"csis_config": THEIRS}} for s in self.model._storages})
    run.ctx.meta_state.record_launch_params("test2", {"launched": True, "hostname": "test2-001"})
    monkeypatch.setattr(AwsCloudBuilder, "instance_tags", lambda self, name: {"Name": name} if name == "test2" else None)
    plan = relabel_plan(run.ctx, AWS)
    assert [(r.kind, r.build_id, r.series, r.tags) for r in plan] == [
        ("storage", "vol-legacy", ebs_name, {"csis_config": OURS}),       # lacks the id: relabelled
        ("instance", "test2-001", "test2", {"csis_config": OURS})]        # the EFS is ours already, the S3 is theirs
    assert "tag absent on the ebs vol-legacy" in plan[0].differences[0]
    retagged: list[tuple[str, str]] = []
    monkeypatch.setattr(TofuEbsStorageBuilder, "retag_storage", lambda self, storage, tags: retagged.append(("storage", storage.get_name())) or True)
    monkeypatch.setattr(AwsCloudBuilder, "retag_instance", lambda self, name, tags: retagged.append(("instance", name)) or True)
    done = relabel(AWS)
    assert [r.retagged for r in done] == [True, True] and retagged == [("storage", ebs_name), ("instance", "test2")]
    # a build filter asks about images alone
    assert relabel_plan(run.ctx, AWS, ["ami-none"]) == []
