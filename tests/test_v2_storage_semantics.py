# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Storage semantics (stage 10.11-13, operator 2026-09-08): a storage exists
exactly as long as its declaration.

* deleting the entry is the demise: the next storage run plans the
  whitelisted destroy of the UNDECLARED storage (wipe first for a bucket)
  and records the tombstone with action `undeclared`;
* a tombstone keeps history, not the name: a re-declared name is a new
  GENERATION (action `regenerate`), never a refused resurrection;
* single-attach cardinality stays a configuration error, and the refusal
  names the multi-host builders on the same runtime.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, command_lines, copy_config


def _record(root: Path, name: str, state: str, facts: dict | None = None, generation: int = 1) -> None:
    ms = root / "meta-state"
    ms.mkdir(exist_ok=True)
    p = ms / "storage-state.yaml"
    data = yaml.safe_load(p.read_text()) if p.exists() else {}
    data.setdefault("storages", {})[name] = {
        "state": state, "generation": generation,
        "history": [{"from": None, "to": "active", "run": "r0", "generation": 1}]
        + ([{"from": "active", "to": "destroyed", "run": "r1", "generation": 1}] if state == "destroyed" else []),
        **({"facts": facts} if facts else {}),
    }
    p.write_text(yaml.safe_dump(data, sort_keys=True))


def _undeclare_storage(root: Path, name: str) -> None:
    for p in (root / "storages").glob("*.y*ml"):
        d = yaml.safe_load(p.read_text()) or {}
        before = len(d.get("storages") or [])
        d["storages"] = [s for s in (d.get("storages") or []) if s.get("name") != name]
        if len(d["storages"]) != before:
            p.write_text(yaml.safe_dump(d, sort_keys=False))


def _undeclare_instance(root: Path, *names: str) -> None:
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text()) or {}
    d["instances"] = [i for i in (d.get("instances") or []) if i["name"] not in names]
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _gates(script: str) -> dict[str, str]:
    out = {}
    for line in command_lines(script):
        if "gate-plan" in line:
            out[line.split('"')[1]] = line
    return out


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    runs: list[V2Run] = []

    def make(**kw) -> V2Run:
        run = V2Run(tmp_path, monkeypatch, config_root=root, **kw)
        runs.append(run)
        return run
    try:
        yield root, make
    finally:
        for r in runs:
            r.restore_cwd()


def test_a_declared_storage_with_a_tombstone_is_a_new_generation(prepared):
    root, make = prepared
    _record(root, "gce_data", "destroyed", {"builder": "gcp-pd", "type": "pd"})
    run = make()
    summary = run.run(["storage"], apply=True)          # no "cannot be resurrected"
    assert summary.ok, summary.error
    tf = "\n".join(p.read_text() for p in (run.generated / "storage" / "gcp-pd").rglob("*.tf"))
    assert 'module "storage_gce_data"' in tf              # created again
    from cs_image_system.base.lifecycles import Lifecycle
    from cs_image_system.base.read_models import record_storage_transitions
    run.ctx.config["apply_storage"] = ["gcloud-east1"]
    record_storage_transitions(run.ctx, Lifecycle.STORAGE)
    ms = run.ctx.meta_state
    assert ms.storage_state("gce_data") == "active"
    assert ms.storage_generation("gce_data") == 2
    last = ms.storage_states()["gce_data"]["history"][-1]
    assert last["action"] == "regenerate" and last["generation"] == 2
    assert ms.storage_read_model()["storages"]["gce_data"]["generation"] == 2


def test_an_undeclared_storage_is_a_whitelisted_destroy_with_its_wipe(prepared):
    root, make = prepared
    _record(root, "gce_bucket", "active",
            {"builder": "gcp-gcs", "type": "gcs", "bucket_name": "csis-sandbox-86233086783-default-bucket"})
    _record(root, "mnt_data", "active", {"builder": "aws-ebs", "type": "ebs"})
    _undeclare_instance(root, "test2")                   # test2 attached mnt_data
    _undeclare_storage(root, "gce_bucket")
    _undeclare_storage(root, "mnt_data")
    run = make()
    assert not any(s.get_name() in ("gce_bucket", "mnt_data") for s in run.ctx.storages)
    summary = run.run(["storage"], apply=True)
    assert summary.ok, summary.error                     # N22 is gone: not an error
    script = (run.generated / "storage" / "run-storage.sh").read_text()
    gates = _gates(script)
    assert "--allow-destroy module.storage_gce_bucket" in gates["gcp-gcs/storage-generation"]
    assert "--allow-destroy module.storage_mnt_data" in gates["aws-ebs/storage-generation"]
    assert "bash wipe-gce_bucket.sh" in script
    wipe = (run.generated / "storage" / "gcp-gcs" / "storage-generation" / "wipe-gce_bucket.sh").read_text()
    assert "gs://csis-sandbox-86233086783-default-bucket/**" in wipe
    # the module call is absent (that IS the destroy); the root still exists
    tf = "\n".join(p.read_text() for p in (run.generated / "storage" / "gcp-gcs").rglob("*.tf"))
    assert 'module "storage_gce_bucket"' not in tf and "backend" in tf
    from cs_image_system.base.lifecycles import Lifecycle
    from cs_image_system.base.read_models import record_storage_transitions
    run.ctx.config["apply_storage"] = ["gcp-gcs"]        # only the bucket's root applied
    record_storage_transitions(run.ctx, Lifecycle.STORAGE)
    ms = run.ctx.meta_state
    assert ms.storage_state("gce_bucket") == "destroyed"
    assert ms.storage_states()["gce_bucket"]["history"][-1]["action"] == "undeclared"
    assert ms.storage_state("mnt_data") == "active"      # its root only planned


def test_an_undeclared_storage_whose_record_names_no_root_is_refused(prepared):
    root, make = prepared
    _record(root, "efs-storage", "active")                # no facts, no read-model
    _undeclare_storage(root, "efs-storage")
    run = make()
    summary = run.run(["storage"], apply=False)
    assert not summary.ok
    assert any("names no storage builder" in e for e in summary.validation_errors)


def test_single_attach_refusal_names_the_shared_alternatives(prepared):
    root, make = prepared
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    for i in d["instances"]:
        if i["name"] == "test":
            i["storages"] = [{"name": "mnt_data", "mount_point": "/mnt/data"}]   # test2 already attaches it
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    run = make()
    summary = run.run(["storage"], apply=False)
    assert not summary.ok
    err = next(e for e in summary.validation_errors if "single-attach" in e)
    assert "multi-host storage builders on aws-east2-runtime: ['aws-efs', 'aws-s3']" in err


# --------------------------------------------------- archived (stage 11.6)

def _set_storage_state(root: Path, name: str, state: str) -> None:
    for p in (root / "storages").glob("*.y*ml"):
        d = yaml.safe_load(p.read_text()) or {}
        changed = False
        for s in d.get("storages") or []:
            if s.get("name") == name:
                s["state"] = state
                changed = True
        if changed:
            p.write_text(yaml.safe_dump(d, sort_keys=False))


def test_archiving_a_pd_snapshots_first_and_destroys_the_disk(prepared):
    root, make = prepared
    _undeclare_instance(root, "gce-test")                  # archived requires no attachments (N21)
    _record(root, "gce_data", "active", {"builder": "gcp-pd", "type": "pd"})
    _set_storage_state(root, "gce_data", "archived")
    run = make()
    summary = run.run(["storage"], apply=True)
    assert summary.ok, summary.validation_errors or summary.error
    script = (run.generated / "storage" / "run-storage.sh").read_text()
    lines = [ln for ln in command_lines(script) if ln.split('"')[1] == "gcp-pd/storage-generation"]
    archive = next(i for i, ln in enumerate(lines) if "bash archive-gce-data.sh" in ln)
    plan = next(i for i, ln in enumerate(lines) if "plan -input=false" in ln)
    assert archive < plan
    assert "--allow-destroy module.storage_gce_data" in next(ln for ln in lines if "gate-plan" in ln)
    body = (run.generated / "storage" / "gcp-pd" / "storage-generation" / "archive-gce-data.sh").read_text()
    assert 'gcloud compute disks snapshot "gce-data" --snapshot-names "csis-gce-data-archive"' in body
    assert "already exists" in body                        # idempotent across attempts
    tf = "\n".join(p.read_text() for p in (run.generated / "storage" / "gcp-pd").rglob("*.tf"))
    assert 'module "storage_gce_data"' not in tf and "ARCHIVED" in tf
    # the recorded transition carries the archive name
    from cs_image_system.base.lifecycles import Lifecycle
    from cs_image_system.base.read_models import record_storage_transitions
    run.ctx.config["apply_storage"] = ["gcloud-east1"]
    record_storage_transitions(run.ctx, Lifecycle.STORAGE)
    entry = run.ctx.meta_state.storage_states()["gce_data"]
    assert entry["state"] == "archived" and entry["facts"]["archive"] == "csis-gce-data-archive"


def test_restoring_a_pd_creates_it_from_the_snapshot_then_deletes_the_snapshot(prepared):
    root, make = prepared
    _record(root, "gce_data", "archived", {"builder": "gcp-pd", "type": "pd", "archive": "csis-gce-data-archive"})
    run = make()                                            # declared active (the fixture)
    run.ctx.config["apply_storage"] = ["gcloud-east1"]
    summary = run.run(["storage"], apply=True)
    assert summary.ok, summary.validation_errors or summary.error
    tf = "\n".join(p.read_text() for p in (run.generated / "storage" / "gcp-pd").rglob("*.tf"))
    assert 'snapshot = "csis-gce-data-archive"' in tf
    lines = [ln for ln in command_lines((run.generated / "storage" / "run-storage.sh").read_text())
             if ln.split('"')[1] == "gcp-pd/storage-generation"]
    apply_i = next(i for i, ln in enumerate(lines) if "apply -input=false tfplan" in ln)
    restore = next(i for i, ln in enumerate(lines) if "bash restore-gce-data.sh" in ln)
    assert restore > apply_i
    body = (run.generated / "storage" / "gcp-pd" / "storage-generation" / "restore-gce-data.sh").read_text()
    assert 'gcloud compute snapshots delete "csis-gce-data-archive"' in body
    assert "--allow-destroy" not in next(ln for ln in lines if "gate-plan" in ln)


def test_destroying_an_archived_pd_deletes_the_archive_and_whitelists_nothing(prepared):
    root, make = prepared
    _undeclare_instance(root, "gce-test")
    _record(root, "gce_data", "archived", {"builder": "gcp-pd", "type": "pd", "archive": "csis-gce-data-archive"})
    _set_storage_state(root, "gce_data", "destroyed")
    run = make()
    summary = run.run(["storage"], apply=True)
    assert summary.ok, summary.validation_errors or summary.error
    lines = [ln for ln in command_lines((run.generated / "storage" / "run-storage.sh").read_text())
             if ln.split('"')[1] == "gcp-pd/storage-generation"]
    assert any("bash unarchive-gce-data.sh" in ln for ln in lines)
    assert "--allow-destroy" not in next(ln for ln in lines if "gate-plan" in ln)   # no disk to destroy


def test_archived_is_refused_where_the_builder_cannot_archive(prepared):
    root, make = prepared
    _undeclare_instance(root, "test", "test2")
    _record(root, "efs-storage", "active", {"builder": "aws-efs", "type": "efs"})
    _set_storage_state(root, "efs-storage", "archived")
    run = make()
    summary = run.run(["storage"], apply=False)
    assert not summary.ok
    assert any("requests archived, which its builder does not realize" in e for e in summary.validation_errors)


# ------------------------------------------ archived for EBS (stage 15)

def test_archiving_an_ebs_volume_snapshots_first_and_destroys_it(prepared):
    root, make = prepared
    _undeclare_instance(root, "test2")                      # test2 attaches mnt_data (N21: unattached only)
    _record(root, "mnt_data", "active", {"builder": "aws-ebs", "type": "ebs"})
    _set_storage_state(root, "mnt_data", "archived")
    run = make()
    summary = run.run(["storage"], apply=True)
    assert summary.ok, summary.validation_errors or summary.error
    lines = [ln for ln in command_lines((run.generated / "storage" / "run-storage.sh").read_text())
             if ln.split('"')[1] == "aws-ebs/storage-generation"]
    archive = next(i for i, ln in enumerate(lines) if "bash archive-mnt_data.sh" in ln)
    plan = next(i for i, ln in enumerate(lines) if "plan -input=false" in ln)
    assert archive < plan
    assert "--allow-destroy module.storage_mnt_data" in next(ln for ln in lines if "gate-plan" in ln)
    body = (run.generated / "storage" / "aws-ebs" / "storage-generation" / "archive-mnt_data.sh").read_text()
    assert 'aws ec2 create-snapshot --region "us-east-2" --profile "noaa"' in body
    assert "Key=Name,Value=csis-mnt-data-archive" in body and "wait snapshot-completed" in body
    assert "already exists" in body                        # idempotent across attempts
    tf = "\n".join(p.read_text() for p in (run.generated / "storage" / "aws-ebs").rglob("*.tf"))
    assert 'module "storage_mnt_data"' not in tf and "ARCHIVED" in tf
    from cs_image_system.base.lifecycles import Lifecycle
    from cs_image_system.base.read_models import record_storage_transitions
    run.ctx.config["apply_storage"] = ["aws-east2-runtime"]
    record_storage_transitions(run.ctx, Lifecycle.STORAGE)
    entry = run.ctx.meta_state.storage_states()["mnt_data"]
    assert entry["state"] == "archived" and entry["facts"]["archive"] == "csis-mnt-data-archive"


def test_restoring_an_ebs_volume_creates_it_from_the_snapshot_then_deletes_it(prepared):
    root, make = prepared
    _record(root, "mnt_data", "archived", {"builder": "aws-ebs", "type": "ebs", "archive": "csis-mnt-data-archive"})
    run = make()                                            # declared active (the fixture)
    run.ctx.config["apply_storage"] = ["aws-east2-runtime"]
    summary = run.run(["storage"], apply=True)
    assert summary.ok, summary.validation_errors or summary.error
    tf = "\n".join(p.read_text() for p in (run.generated / "storage" / "aws-ebs").rglob("*.tf"))
    assert 'snapshot_name = "csis-mnt-data-archive"' in tf
    lines = [ln for ln in command_lines((run.generated / "storage" / "run-storage.sh").read_text())
             if ln.split('"')[1] == "aws-ebs/storage-generation"]
    apply_i = next(i for i, ln in enumerate(lines) if "apply -input=false tfplan" in ln)
    restore = next(i for i, ln in enumerate(lines) if "bash restore-mnt_data.sh" in ln)
    assert restore > apply_i
    body = (run.generated / "storage" / "aws-ebs" / "storage-generation" / "restore-mnt_data.sh").read_text()
    assert "delete-snapshot" in body and "csis-mnt-data-archive" in body
    assert "--allow-destroy" not in next(ln for ln in lines if "gate-plan" in ln)


def test_destroying_an_archived_ebs_volume_deletes_the_archive_and_whitelists_nothing(prepared):
    root, make = prepared
    _undeclare_instance(root, "test2")
    _record(root, "mnt_data", "archived", {"builder": "aws-ebs", "type": "ebs", "archive": "csis-mnt-data-archive"})
    _set_storage_state(root, "mnt_data", "destroyed")
    run = make()
    summary = run.run(["storage"], apply=True)
    assert summary.ok, summary.validation_errors or summary.error
    lines = [ln for ln in command_lines((run.generated / "storage" / "run-storage.sh").read_text())
             if ln.split('"')[1] == "aws-ebs/storage-generation"]
    assert any("bash unarchive-mnt_data.sh" in ln for ln in lines)
    assert "--allow-destroy" not in next(ln for ln in lines if "gate-plan" in ln)


def test_archived_ebs_lookup_expects_the_snapshot_not_the_volume(prepared, monkeypatch):
    from cs_image_system.aws_runtime import aws_utils
    root, make = prepared
    _record(root, "mnt_data", "archived", {"builder": "aws-ebs", "type": "ebs", "archive": "csis-mnt-data-archive"})
    run = make()

    class FakeEC2:
        def __init__(self, snaps):
            self.snaps, self.calls = snaps, []

        def describe_snapshots(self, **kw):
            self.calls.append(("snapshots", kw)); return {"Snapshots": self.snaps}

        def describe_volumes(self, **kw):
            self.calls.append(("volumes", kw)); return {"Volumes": []}
    ec2 = FakeEC2([{"SnapshotId": "snap-1", "State": "completed", "VolumeSize": 100,
                    "Tags": [{"Key": "Name", "Value": "csis-mnt-data-archive"}]}])
    monkeypatch.setattr(aws_utils, "aws_client", lambda service, cfg: ec2)
    builder = run.ctx.storage_builders["aws-ebs"]
    storage = next(s for s in run.ctx.storages if s.get_name() == "mnt_data")
    rec = builder._lookup(storage)
    assert rec == {"id": "snap-1", "state": "archived", "size": 100, "archive": "snap-1", "snapshot_state": "completed",
                   "tags": {"Name": "csis-mnt-data-archive"}}
    assert ec2.calls[0][0] == "snapshots" and ec2.calls[0][1]["Filters"][0]["Values"] == ["csis-mnt-data-archive"]
    assert builder._lookup(storage) is not None and not any(c[0] == "volumes" for c in ec2.calls)
    ec2.snaps = []
    assert builder._lookup(storage) is None                 # archive gone: HARD missing for the state query


# ------------------------------------------ data lifecycles (stage 15)

def _set_storage_lifecycle(root: Path, name: str, spec) -> None:
    for p in (root / "storages").glob("*.y*ml"):
        d = yaml.safe_load(p.read_text()) or {}
        changed = False
        for s in d.get("storages") or []:
            if s.get("name") == name:
                if spec is None:
                    s.pop("lifecycle", None)
                else:
                    s["lifecycle"] = spec
                changed = True
        if changed:
            p.write_text(yaml.safe_dump(d, sort_keys=False))


def test_declared_lifecycles_reach_the_modules_and_the_read_model(prepared):
    root, make = prepared
    run = make()                                            # the fixture declares both (stage 15)
    summary = run.run(["storage"], apply=False)
    assert summary.ok, summary.validation_errors or summary.error
    s3 = "\n".join(p.read_text() for p in (run.generated / "storage" / "aws-s3").rglob("*.tf"))
    assert 'lifecycle_rules = [{' in s3 and '"storage_class" = "STANDARD_IA"' in s3 and '"transition_days" = 30' in s3
    efs = "\n".join(p.read_text() for p in (run.generated / "storage" / "aws-efs").rglob("*.tf"))
    assert 'transition_to_ia = "AFTER_30_DAYS"' in efs
    rm = run.ctx.meta_state.storage_read_model()["storages"]
    assert rm["default-bucket"]["lifecycle"] == {"transition_days": 30, "storage_class": "STANDARD_IA"}
    assert rm["efs-storage"]["lifecycle"] == {"ia_days": 30} and rm["mnt_data"]["lifecycle"] == {}


def test_lifecycle_declarations_are_validated_per_builder(prepared):
    root, make = prepared
    _set_storage_lifecycle(root, "mnt_data", {"ia_days": 30})               # EBS: no data lifecycle
    _set_storage_lifecycle(root, "default-bucket", {"transition_days": 30, "storage_class": "TAPE", "nope": 1})
    _set_storage_lifecycle(root, "efs-storage", {"ia_days": 45})
    run = make()
    summary = run.run(["storage"], apply=False)
    assert not summary.ok
    errs = "\n".join(summary.validation_errors)
    assert "storage 'mnt_data' (aws-ebs) declares a data lifecycle, which its builder does not realize" in errs
    assert "unknown lifecycle keys ['nope']" in errs and "storage_class must be one of" in errs
    assert "lifecycle.ia_days must be one of" in errs
    _set_storage_lifecycle(root, "mnt_data", None)
    _set_storage_lifecycle(root, "default-bucket", {"expire_days": 0})
    _set_storage_lifecycle(root, "efs-storage", None)
    run = make()
    summary = run.run(["storage"], apply=False)
    assert not summary.ok and any("expire_days must be a positive int" in e for e in summary.validation_errors)


def test_state_query_reports_a_declared_lifecycle_the_resource_lacks(prepared):
    from cs_image_system.base.state_query import DRIFT_STALE, storage_drift
    root, make = prepared
    _record(root, "default-bucket", "active", {"builder": "aws-s3", "type": "s3"})
    _record(root, "efs-storage", "active", {"builder": "aws-efs", "type": "efs"})
    run = make()
    real = {"default-bucket": {"present": True, "type": "s3", "state": "active", "lifecycle": {}},
            "efs-storage": {"present": True, "type": "efs", "state": "available", "lifecycle": {"TransitionToIA": "AFTER_30_DAYS"}}}
    drift = storage_drift(run.ctx, real)
    assert [(d.name, d.drift) for d in drift] == [("default-bucket", DRIFT_STALE)]
    assert "declares a data lifecycle that the resource does not carry yet" in drift[0].detail
    real["default-bucket"]["lifecycle"] = {"rules": ["csis"]}
    assert storage_drift(run.ctx, real) == []
    del real["default-bucket"]["lifecycle"]                  # a provider that reported nothing makes no claim
    assert storage_drift(run.ctx, real) == []


def test_the_instance_root_reads_storage_state_from_the_second_backend(tmp_path, monkeypatch):
    """stage 46: the instance root's own state is in the default backend; the
    storage state it binds to lives in the second, and the datasource says so."""
    from v2_support import V2Run
    run = V2Run(tmp_path, monkeypatch)
    assert run.run(["identity", "storage", "instance-image"], apply=False).ok
    inst = run.generated / "instance-image" / "open-tofu" / "instance-generation"
    root = (inst / "open-tofu-instance-generation.tf").read_text()
    assert 'bucket = "my-east1-tfstate-bucket"' in root and 'key = "statefiles/csia/aws_ebs.tfstate"' in root
    assert 'bucket = "noaa-ioos-cloud-sandbox-tfstate"' in (inst / "open-tofu-instance-generation.tfbackend.hcl").read_text()
