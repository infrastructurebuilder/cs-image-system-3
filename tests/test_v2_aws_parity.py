# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""AWS parity for the sanctioned paths (stage 11.1): the AWS runtime answers
the booted-image query, disposes of an AMI (deregister + snapshots) and
verifies a launched instance over SSM, so `dispose image` works for AMIs
and an AWS instance may be declared ephemeral.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.v2_support import V2Run, copy_config


class FakeEC2:
    def __init__(self) -> None:
        self.instances = {"test2": {"InstanceId": "i-1", "ImageId": "ami-dask-1"}}
        self.images = {"ami-old": {"ImageId": "ami-old", "BlockDeviceMappings": [
            {"Ebs": {"SnapshotId": "snap-1"}}, {"Ebs": {"SnapshotId": "snap-2"}}, {"VirtualName": "ephemeral0"}]}}
        self.deregistered: list[str] = []
        self.deleted_snapshots: list[str] = []

    def describe_instances(self, Filters):
        name = next(f["Values"][0] for f in Filters if f["Name"] == "tag:Name")
        inst = self.instances.get(name)
        return {"Reservations": [{"Instances": [inst]}] if inst else []}

    def describe_images(self, ImageIds):
        return {"Images": [self.images[i] for i in ImageIds if i in self.images]}

    def deregister_image(self, ImageId):
        self.deregistered.append(ImageId)

    def delete_snapshot(self, SnapshotId):
        self.deleted_snapshots.append(SnapshotId)


@pytest.fixture
def aws(tmp_path: Path, monkeypatch):
    from cs_image_system.aws_runtime import aws_utils
    ec2 = FakeEC2()
    monkeypatch.setattr(aws_utils, "ec2_client", lambda cfg: ec2)
    run = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path), dry_run=False)
    try:
        yield run, ec2
    finally:
        run.restore_cwd()


def test_aws_boot_image_query(aws):
    run, ec2 = aws
    rtb = run.ctx.runtime_builders["aws-east2-runtime"]
    assert rtb.can_query_instance_boot_image()
    assert rtb.query_instance_boot_image("test2") == "ami-dask-1"
    assert rtb.query_instance_boot_image("nobody") is None


def test_aws_dispose_deregisters_and_deletes_snapshots(aws):
    run, ec2 = aws
    rtb = run.ctx.runtime_builders["aws-east2-runtime"]
    assert rtb.dispose_image("ami-old") is True
    assert ec2.deregistered == ["ami-old"] and ec2.deleted_snapshots == ["snap-1", "snap-2"]
    assert rtb.dispose_image("ami-gone") is False            # already gone: record still dropped by the caller


def test_dispose_image_command_now_works_for_amis(aws):
    from cs_image_system.base.commands.dispose import dispose_images
    run, ec2 = aws
    ms = run.ctx.meta_state
    ms.add_build({"build_id": "ami-old", "series": "imgfile-basic-dask", "runtime": "aws-east2-runtime",
                  "name": "old", "parent": "vendor", "run": "r0"})
    results = dispose_images(["ami-old"])
    assert [r.build_id for r in results] == ["ami-old"] and results[0].deleted is True
    assert ms.build("ami-old") is None and ec2.deregistered == ["ami-old"]


def test_aws_verification_over_ssm(aws, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    run, ec2 = aws
    rtb = run.ctx.runtime_builders["aws-east2-runtime"]
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(AwsCloudBuilder, "run_session_command",
                        lambda self, name, script, timeout=300: (0, "LAUNCH_APPLIED\n1\n"))
    result = rtb.verify_instance("test2", expected_build="ami-dask-1", expect_mounts=1, timeout=1)
    assert result["ok"] and {c["name"]: c["ok"] for c in result["checks"]} == {
        "startup scripts": True, "booted image": True, "data disks mounted": True}
    monkeypatch.setattr(AwsCloudBuilder, "run_session_command",
                        lambda self, name, script, timeout=300: (0, "LAUNCH_APPLIED\n0\n"))
    result = rtb.verify_instance("test2", expected_build="ami-other", expect_mounts=1, timeout=1)
    assert not result["ok"]
    assert {c["name"]: c["ok"] for c in result["checks"]} == {
        "startup scripts": True, "booted image": False, "data disks mounted": False}
    monkeypatch.setattr(AwsCloudBuilder, "run_session_command",
                        lambda self, name, script, timeout=300: (1, "TargetNotConnected"))
    result = rtb.verify_instance("test2", expected_build="ami-dask-1", timeout=0)
    assert not result["ok"] and "no completion marker" in result["checks"][0]["detail"]


def test_user_data_ends_with_the_completion_marker(aws):
    from cs_image_system.base.launch_params import compute_launch_params, user_data_template
    run, _ = aws
    inst = next(i for i in run.ctx.instances if i.get_name() == "test2")
    text = user_data_template(compute_launch_params(run.ctx, inst))
    assert text.rstrip().splitlines()[-1] == "date -u +%FT%TZ > /var/lib/csis/launch-applied"


def test_instance_userdata_runs_before_the_marker_and_is_a_launch_parameter(aws):
    """The declared `userdata` lines are the last act before the completion
    marker, under `set -e` (a failing line = a failed startup, ledger 68), and
    they are part of the immutable launch parameters."""
    from cs_image_system.base.launch_params import compute_launch_params, user_data_template
    run, _ = aws
    inst = next(i for i in run.ctx.instances if i.get_name() == "test2")
    inst.userdata = "echo proof > /tmp/proof\nfalse"
    params = compute_launch_params(run.ctx, inst)
    assert params["userdata"] == "echo proof > /tmp/proof\nfalse"
    tail = user_data_template(params).rstrip().splitlines()[-5:]
    assert tail == ["# instance userdata (declared on the instance)", "echo proof > /tmp/proof", "false",
                    "mkdir -p /var/lib/csis", "date -u +%FT%TZ > /var/lib/csis/launch-applied"]
    inst.userdata = ""
    params = compute_launch_params(run.ctx, inst)
    assert "userdata" not in params and "userdata" not in user_data_template(params)


def test_an_aws_instance_may_be_ephemeral(tmp_path, monkeypatch):
    import yaml
    root = copy_config(tmp_path)
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    for i in d["instances"]:
        if i["name"] == "test2":
            i["ephemeral"] = True
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        run.ctx.config["apply_instances"] = ["aws-east2-runtime"]
        summary = run.run(["instance-image"], apply=True, only=["none"])
        assert summary.ok, summary.error
        script = (run.generated / "instance-image" / "run-instance-image.sh").read_text()
        assert "verify instance test2" in script and "-var=ephemeral_present=false" in script
        assert "--allow-destroy module.instance_test2" in script
    finally:
        run.restore_cwd()


# ------------------------------------------------------ restamp (stage 11.2)

def test_restamp_records_the_current_fingerprint_on_heads_and_retags(tmp_path, monkeypatch):
    from cs_image_system.base.commands.restamp import restamp, restamp_plan
    from cs_image_system.base.lineage import bake_reason, find_image
    root = copy_config(tmp_path)
    run = V2Run(tmp_path, monkeypatch, config_root=root, dry_run=False)   # the harness journals retags
    retags = run.retags
    try:
        ms = run.ctx.meta_state
        common = {"parent": "vendor", "chain": [], "mods": [], "local_mods": False, "update": None,
                  "tests": {"assertions": 0, "in_bake": True},
                  "capabilities": {"identity_types": ["okta"], "storage_types": ["ebs"]}}
        ms.add_build({"build_id": "ami-older", "series": "basic-rh-10", "runtime": "aws-east2-runtime",
                      "name": "n", "run": "2026_09_01t00_00_00_000000", "input_fingerprint": "1" * 64, **common})
        ms.add_build({"build_id": "ami-old-head", "series": "basic-rh-10", "runtime": "aws-east2-runtime",
                      "name": "n", "run": "2026_09_02t00_00_00_000000", "input_fingerprint": "0" * 64, **common})
        image = find_image(run.ctx, "basic-rh-10", "aws-east2-runtime")
        reason = bake_reason(run.ctx, image, "aws-east2-runtime")
        assert reason is not None and reason.startswith("inputs changed")
        plan = restamp_plan(run.ctx, "aws-east2-runtime", ["basic-rh-10"])
        assert [(r.build_id, r.previous[:4]) for r in plan] == [("ami-old-head", "0000")]   # heads only
        results = restamp("aws-east2-runtime", ["basic-rh-10"])
        assert results[0].retagged is True and retags[-1][0] == "ami-old-head"
        assert set(retags[-1][1]) == {"csis_fingerprint"}
        head = ms.build("ami-old-head")
        assert head is not None and head["input_fingerprint"] == results[0].current
        assert head["fingerprint_restamped"][0]["previous"] == "0" * 64
        older = ms.build("ami-older")
        assert older is not None and older["input_fingerprint"] == "1" * 64   # untouched
        run.ctx.bake_decisions.clear()
        assert bake_reason(run.ctx, image, "aws-east2-runtime") is None        # current now
        assert restamp_plan(run.ctx, "aws-east2-runtime", ["basic-rh-10"]) == []
    finally:
        run.restore_cwd()


def test_restamp_dry_run_changes_nothing(tmp_path, monkeypatch):
    from cs_image_system.base.commands.restamp import restamp
    root = copy_config(tmp_path)
    run = V2Run(tmp_path, monkeypatch, config_root=root)                    # dry run
    try:
        ms = run.ctx.meta_state
        ms.add_build({"build_id": "ami-x", "series": "basic-rh-10", "runtime": "aws-east2-runtime", "name": "n",
                      "run": "2026_09_02t00_00_00_000000", "parent": "vendor", "input_fingerprint": "0" * 64})
        plan = restamp("aws-east2-runtime")
        assert [r.build_id for r in plan] == ["ami-x"] and plan[0].retagged is None
        untouched = ms.build("ami-x")
        assert untouched is not None and untouched["input_fingerprint"] == "0" * 64
    finally:
        run.restore_cwd()


# ------------------------------------------------------ relabel (ledger 66)

def _seed_follow_pair(ms) -> None:
    common = {"parent": "vendor", "chain": [], "mods": [], "local_mods": False, "update": None,
              "tests": {"assertions": 0, "in_bake": True},
              "capabilities": {"identity_types": ["okta"], "storage_types": ["pd"]},
              "run": "2026_09_08t12_48_23_888542", "runtime": "gcloud-east1"}
    ms.add_build({**common, "build_id": "base-1", "series": "basic-rh-10", "name": "b",
                  "input_fingerprint": "e792c328f39cd099" + "0" * 48})
    ms.add_build({**common, "build_id": "dask-1", "series": "imgfile-basic-dask", "name": "d",
                  "parent": "base-1", "input_fingerprint": "1733b718d8c52101" + "0" * 48})


def _real_images(dask_parent="series-basic-rh-10", dask_fp="293d6de5ab5f3b4f"):
    return [
        {"image_id": "base-1", "name": "base-1", "state": "READY", "created": "", "tags": {
            "csis_series": "basic-rh-10", "csis_parent": "vendor", "csis_run": "2026_09_08t12_48_23_888542",
            "csis_fingerprint": "e792c328f39cd099"}},
        {"image_id": "dask-1", "name": "dask-1", "state": "READY", "created": "", "tags": {
            "csis_series": "imgfile-basic-dask", "csis_parent": dask_parent, "csis_run": "2026_09_08t12_48_23_888542",
            "csis_fingerprint": dask_fp}},
    ]


def test_relabel_retags_only_the_images_whose_tags_disagree_with_their_record(tmp_path, monkeypatch):
    """The live 2026-09-08 case: a follow image baked in the same run as its
    parent kept packer's generation-time labels (`series-…` parent, a
    placeholder fingerprint); its record is the truth, so relabel re-tags it
    and leaves the consistent base image alone."""
    from cs_image_system.base.commands.relabel import relabel, relabel_plan
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    root = copy_config(tmp_path)
    run = V2Run(tmp_path, monkeypatch, config_root=root, dry_run=False)
    retags = run.retags
    try:
        _seed_follow_pair(run.ctx.meta_state)
        monkeypatch.setattr(GCPCloudBuilder, "query_images", lambda self, series: _real_images())
        plan = relabel_plan(run.ctx, "gcloud-east1")
        assert [(r.build_id, r.differences) for r in plan] == [
            ("dask-1", ["parent: tag=series-basic-rh-10 record=base-1",
                        "fingerprint: tag=293d6de5ab5f3b4f record=1733b718d8c52101"])]
        results = relabel("gcloud-east1")
        assert results[0].retagged is True
        assert retags[-1] == ("dask-1", {"csis_series": "imgfile-basic-dask", "csis_parent": "base-1",
                                         "csis_run": "2026_09_08t12_48_23_888542",
                                         "csis_fingerprint": "1733b718d8c52101"})
        monkeypatch.setattr(GCPCloudBuilder, "query_images",
                            lambda self, series: _real_images("base-1", "1733b718d8c52101"))
        assert relabel_plan(run.ctx, "gcloud-east1") == []                 # reality now matches
        with pytest.raises(ValueError, match="unknown runtime"):
            relabel_plan(run.ctx, "nowhere")
    finally:
        run.restore_cwd()


def test_relabel_dry_run_retags_nothing(tmp_path, monkeypatch):
    from cs_image_system.base.commands.relabel import relabel
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    root = copy_config(tmp_path)
    run = V2Run(tmp_path, monkeypatch, config_root=root)                    # dry run
    try:
        _seed_follow_pair(run.ctx.meta_state)
        monkeypatch.setattr(GCPCloudBuilder, "query_images", lambda self, series: _real_images())
        plan = relabel("gcloud-east1", builds=["dask-1"])
        assert [r.build_id for r in plan] == ["dask-1"] and plan[0].retagged is None
        assert run.retags == []
    finally:
        run.restore_cwd()


def test_session_command_tolerates_the_invocation_race(aws, monkeypatch):
    """SSM's GetCommandInvocation raises InvocationDoesNotExist for a moment
    after SendCommand returns; the poll keeps waiting instead of failing
    (found live: the unmount had run on the instance, no receipt was written)."""
    from cs_image_system.aws_runtime import aws_utils
    run, ec2 = aws

    class Err(Exception):
        def __init__(self, code):
            super().__init__(code)
            self.response = {"Error": {"Code": code}}

    class FakeSSM:
        def __init__(self):
            self.polls = 0

        def send_command(self, **kw):
            return {"Command": {"CommandId": "cmd-1"}}

        def get_command_invocation(self, **kw):
            self.polls += 1
            if self.polls < 3:
                raise Err("InvocationDoesNotExist")
            return {"Status": "Success", "StandardOutputContent": "unmounted: /mnt/x\n", "StandardErrorContent": ""}
    ssm = FakeSSM()
    monkeypatch.setattr(aws_utils, "aws_client", lambda service, cfg: ssm)
    monkeypatch.setattr("time.sleep", lambda s: None)
    rtb = run.ctx.runtime_builders["aws-east2-runtime"]
    rc, out = rtb.run_session_command("test2", "true", timeout=30)
    assert (rc, out) == (0, "unmounted: /mnt/x\n") and ssm.polls == 3
    # any other client error still raises
    ssm.polls = -100
    ssm.get_command_invocation = lambda **kw: (_ for _ in ()).throw(Err("AccessDeniedException"))
    with pytest.raises(Err):
        rtb.run_session_command("test2", "true", timeout=30)
