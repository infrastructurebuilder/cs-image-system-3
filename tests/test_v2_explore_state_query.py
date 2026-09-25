# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""EXPLORE "Using Systemic State" / "Existing Systemic State Migration":
the read-only state query, its drift classes, the import (migration) path
and the validator that refuses to run on hard drift.

Providers are faked at the plugin hook seam (``query_images`` /
``query_state``): the drift rules are what is under test, not boto3.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.v2_support import V2Run

from cs_image_system.base import state_query as sq
from cs_image_system.base.lineage import TAG_PREFIX
from cs_image_system.base.lifecycles import Lifecycle


def _tags(series: str, run: str = "run-1", parent: str = "external", fp: str = "abc") -> dict[str, str]:
    return {f"{TAG_PREFIX}series": series, f"{TAG_PREFIX}run": run,
            f"{TAG_PREFIX}parent": parent, f"{TAG_PREFIX}fingerprint": fp,
            f"{TAG_PREFIX}identity_types": "okta", f"{TAG_PREFIX}storage_types": "ebs"}


def _image(image_id: str, series: str, **kw) -> dict:
    return {"image_id": image_id, "name": f"{series}-{image_id}", "state": "available",
            "created": "2026-08-27T00:00:00Z", "tags": _tags(series, **kw)}


def _build(build_id: str, series: str, runtime: str, run: str = "run-1", parent: str = "external",
           fp: str = "abcdef0123456789") -> dict:
    return {"build_id": build_id, "series": series, "runtime": runtime, "name": f"{series}-{build_id}",
            "parent": parent, "input_fingerprint": fp, "run": run,
            "capabilities": {"identity_types": ["okta"], "storage_types": ["ebs"]}, "mods": [], "chain": []}


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    """A context whose plugins answer from canned reality."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuStorageBuilder

    reality: dict = {"images": {}, "storages": {}, "groups": {}}   # images keyed by runtime name
    run = V2Run(tmp_path, monkeypatch)   # first: its stubs would override ours
    monkeypatch.setattr(AwsCloudBuilder, "query_images",
                        lambda self, series: list(reality["images"].get(self.get_name(), [])))
    monkeypatch.setattr(TofuStorageBuilder, "query_state",
                        lambda self: {s.get_name(): reality["storages"].get(s.get_name(), {"present": False, "type": self.capability_type()})
                                      for s in self.model._storages})
    monkeypatch.setattr(OktaTfGroupBuilder, "query_state",
                        lambda self: {g.get_name(): reality["groups"].get(g.get_name(), {"present": True, "gid": 1})
                                      for g in self.get_groups_for_builder()})
    try:
        yield run, reality
    finally:
        run.restore_cwd()


def _runtime(ctx) -> str:
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    return sorted(n for n, b in ctx.runtime_builders.items() if isinstance(b, AwsCloudBuilder))[0]


def test_no_drift_when_reality_matches(world):
    run, reality = world
    ctx = run.ctx
    rt = _runtime(ctx)
    ctx.meta_state.add_build(_build("ami-1", "basic-rh-10", rt))
    reality["images"] = {rt: [_image("ami-1", "basic-rh-10", fp="abcdef")]}
    report = sq.query_state(ctx)
    assert report.drift == []
    assert report.unavailable == []
    assert report.reality["images"][rt][0]["image_id"] == "ami-1"


def test_missing_pinned_build_is_hard_drift(world):
    run, reality = world
    ctx = run.ctx
    rt = _runtime(ctx)
    ctx.meta_state.add_build(_build("ami-gone", "basic-rh-10", rt))
    ctx.meta_state.bind_instance("some-instance", "ami-gone", ctx.run_id)
    reality["images"] = {}
    report = sq.query_state(ctx)
    missing = report.by_class(sq.DRIFT_MISSING)
    assert [d.name for d in missing] == ["ami-gone"]
    assert missing[0].hard and "PINNED" in missing[0].detail
    # the report persists and the next run refuses to proceed
    sq.write_state_report(ctx, report)
    errors = sq.validate_state_report(ctx, [Lifecycle.INSTANCE_IMAGE])
    assert len(errors) == 1 and "ami-gone" in errors[0] and "re-run 'state query'" in errors[0]


def test_unpinned_missing_build_is_soft(world):
    run, reality = world
    ctx = run.ctx
    ctx.meta_state.add_build(_build("ami-old", "basic-rh-10", _runtime(ctx)))
    report = sq.query_state(ctx)
    assert [d.hard for d in report.by_class(sq.DRIFT_MISSING)] == [False]
    sq.write_state_report(ctx, report)
    assert sq.validate_state_report(ctx, []) == []


def test_foreign_and_changed_images(world):
    run, reality = world
    ctx = run.ctx
    rt = _runtime(ctx)
    ctx.meta_state.add_build(_build("ami-1", "basic-rh-10", rt, run="run-1", fp="abcdef"))
    reality["images"] = {rt: [
        _image("ami-1", "basic-rh-10", run="run-9", fp="abcdef"),   # tag disagrees with lineage
        _image("ami-hand", "basic-rh-10", run="by-hand"),            # tagged as ours, unrecorded
    ]}
    report = sq.query_state(ctx)
    changed = report.by_class(sq.DRIFT_CHANGED)
    assert [d.name for d in changed] == ["ami-1"] and "run: lineage=run-1 tag=run-9" in changed[0].detail
    foreign = report.by_class(sq.DRIFT_FOREIGN)
    assert [d.name for d in foreign] == ["ami-hand"] and "not in lineage" in foreign[0].detail


def test_pin_to_unknown_build_is_hard(world):
    run, _ = world
    ctx = run.ctx
    ctx.meta_state.bind_image("some-image", "ami-nowhere", ctx.run_id)
    report = sq.query_state(ctx)
    pins = [d for d in report.drift if d.kind == "pin"]
    assert pins and pins[0].hard and pins[0].name == "image:some-image"


def test_storage_drift_classes(world):
    run, reality = world
    ctx = run.ctx
    names = [s.get_name() for s in ctx.storages]
    assert len(names) >= 3, names
    gone, foreign, tomb = names[0], names[1], names[2]
    ms = ctx.meta_state
    ms.record_storage_transition(gone, None, "active", "run-1")
    ms.record_storage_transition(tomb, None, "active", "run-1")
    ms.record_storage_transition(tomb, "active", "destroyed", "run-2")
    reality["storages"] = {
        foreign: {"present": True, "type": "ebs", "id": "vol-1", "state": "available"},
        tomb: {"present": True, "type": "ebs", "id": "vol-2", "state": "available"},
    }
    report = sq.query_state(ctx)
    by_name = {d.name: d for d in report.drift if d.kind == "storage"}
    assert by_name[gone].drift == sq.DRIFT_MISSING and by_name[gone].hard
    assert by_name[foreign].drift == sq.DRIFT_FOREIGN
    assert by_name[tomb].drift == sq.DRIFT_STALE and "still exists" in by_name[tomb].detail


def test_group_drift(world):
    run, reality = world
    ctx = run.ctx
    from cs_image_system.base.read_models import identity_read_model
    ctx.meta_state.write_identity_read_model(identity_read_model(ctx))
    model = ctx.meta_state.identity_read_model()["groups"]
    # managed groups only: a lookup-only group (the fixture's `readers`,
    # stage 63 item 18) never drifts, whatever the provider says
    names = sorted(n for n, rec in model.items() if rec["managed"])
    root_admins = {a for rec in model.values() if rec["is_root"] for a in rec["admins"]}
    reality["groups"] = {
        names[0]: {"present": False},
        names[1]: {"present": True, "gid": None},
        names[2]: {"present": True, "gid": 180007,
                   "members": sorted(set(model[names[2]]["members"]) | {"stranger"}),
                   "admins": sorted(set(model[names[2]]["admins"]) | root_admins)},
        # token liveness (finding 32): deleted out-of-band -> HARD missing;
        # a record WITHOUT the key (probe silent) must say nothing
        names[3]: {"present": True, "gid": 180010, "enrollment_token": False,
                   "members": sorted(model[names[3]]["members"]),
                   "admins": sorted(set(model[names[3]]["admins"]) | root_admins)},
    }
    report = sq.query_state(ctx)
    by_name = {d.name: d for d in report.drift if d.kind == "group"}
    assert by_name[names[0]].drift == sq.DRIFT_MISSING and by_name[names[0]].hard
    assert by_name[names[1]].drift == sq.DRIFT_MISSING and "no gid" in by_name[names[1]].detail
    assert by_name[names[2]].drift == sq.DRIFT_CHANGED and "stranger" in by_name[names[2]].detail
    assert "admins" not in by_name[names[2]].detail  # root admins merged: no admin drift
    tok = by_name[names[3]]
    assert tok.drift == sq.DRIFT_MISSING and tok.hard and "enrollment token" in tok.detail
    assert "state rm" in tok.detail  # the repair is named (identity plans ERROR, finding 32)
    assert names[4] not in by_name  # matches, no token key: no drift


def test_unavailable_provider_is_reported_not_fatal(world, monkeypatch):
    run, _ = world
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder

    def boom(self, series):
        raise RuntimeError("no credentials")
    monkeypatch.setattr(AwsCloudBuilder, "query_images", boom)
    report = sq.query_state(run.ctx)
    assert any(u.startswith("images/") and "no credentials" in u for u in report.unavailable)
    assert not any(report.reality["images"].get(n) for n in report.reality["images"])   # nothing from AWS
    assert not any(k.startswith("aws") for k in report.reality["images"])


def test_import_adopts_foreign_images_and_storages(world):
    run, reality = world
    ctx = run.ctx
    rt = _runtime(ctx)
    storage = ctx.storages[0].get_name()
    reality["images"] = {rt: [_image("ami-hand", "basic-rh-10", run="by-hand", parent="ami-base", fp="feed")]}
    reality["storages"] = {storage: {"present": True, "type": "ebs", "id": "vol-9", "state": "available"}}
    before = sq.query_state(ctx)
    assert len(before.by_class(sq.DRIFT_FOREIGN)) == 2
    done = sq.import_foreign(ctx, before)
    assert done == ["image ami-hand -> lineage series basic-rh-10",
                    f"storage {storage} -> active (imported)"]
    rec = ctx.meta_state.build("ami-hand")
    assert rec and rec["imported"] and rec["parent"] == "ami-base" and rec["run"] == "by-hand"
    assert rec["capabilities"] == {"identity_types": ["okta"], "storage_types": ["ebs"]}
    hist = ctx.meta_state.storage_states()[storage]["history"]
    assert hist[-1]["action"] == "import" and hist[-1]["from"] is None
    # meta-state and reality now agree; a second import is a no-op
    assert sq.query_state(ctx).by_class(sq.DRIFT_FOREIGN) == []
    assert sq.import_foreign(ctx, sq.query_state(ctx)) == []


def test_report_file_is_public_safe_json(world):
    run, reality = world
    ctx = run.ctx
    rt = _runtime(ctx)
    reality["images"] = {rt: [_image("ami-1", "basic-rh-10")]}
    path = sq.write_state_report(ctx, sq.query_state(ctx))
    assert path == run.generated / "state-report.json"
    data = json.loads(path.read_text())
    assert data["summary"] == {"missing": 0, "foreign": 1, "changed": 0, "stale": 0}
    assert data["run"] == ctx.run_id


def test_report_refuses_secret_shaped_reality(world):
    run, reality = world
    reality["images"] = {_runtime(run.ctx): [{"image_id": "ami-x", "tags": {"note": "AK" + "IAABCDEFGHIJKLMNOP"}}]}
    from cs_image_system.base.meta_state import MetaStateSecretError
    with pytest.raises(MetaStateSecretError):
        sq.query_state(run.ctx)


def test_state_query_is_a_registered_validator():
    from cs_image_system.base.commands import run_lifecycles as rl
    assert sq.validate_state_report in rl._VALIDATORS


# ------------------------------------------------ finding 49: booted image

def _gce_runtime(ctx) -> str:
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    return sorted(n for n, b in ctx.runtime_builders.items() if isinstance(b, GCPCloudBuilder))[0]


def test_booted_image_differing_from_the_pin_is_changed_drift(world, monkeypatch):
    """Finding 49: a pin moved to a new series head while the instance kept
    running the old image, and nothing compared the two."""
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    run, _ = world
    ctx = run.ctx
    rt = _gce_runtime(ctx)
    ctx.meta_state.add_build(_build("img-old", "imgfile-basic-dask", rt))
    ctx.meta_state.add_build(_build("img-new", "imgfile-basic-dask", rt))
    ctx.meta_state.bind_instance("gce-test", "img-new", "run-x")
    monkeypatch.setattr(GCPCloudBuilder, "query_instance_boot_image", lambda self, name: "img-old")
    report = sq.query_state(ctx)
    hits = [d for d in report.drift if d.kind == "instance" and d.name == "gce-test"]
    assert len(hits) == 1 and hits[0].drift == sq.DRIFT_CHANGED
    assert "booted image img-old" in hits[0].detail and "img-new" in hits[0].detail


def test_booted_image_matching_the_pin_is_clean_and_unanswered_is_unavailable(world, monkeypatch):
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    run, _ = world
    ctx = run.ctx
    rt = _gce_runtime(ctx)
    ctx.meta_state.add_build(_build("img-new", "imgfile-basic-dask", rt))
    ctx.meta_state.bind_instance("gce-test", "img-new", "run-x")
    monkeypatch.setattr(GCPCloudBuilder, "query_instance_boot_image", lambda self, name: "img-new")
    report = sq.query_state(ctx)
    assert not [d for d in report.drift if d.kind == "instance"]
    monkeypatch.setattr(GCPCloudBuilder, "query_instance_boot_image", lambda self, name: None)
    report = sq.query_state(ctx)
    assert not [d for d in report.drift if d.kind == "instance"]
    assert any("instances/gce-test" in u for u in report.unavailable)


def test_runtimes_without_the_boot_query_make_no_claim(world, monkeypatch):
    run, _ = world
    ctx = run.ctx
    # AWS implements the boot query since stage 11.1; the no-claim path is
    # proven by stubbing the capability back off
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_boot_image", lambda self: False)
    rt = _runtime(ctx)
    ctx.meta_state.add_build(_build("ami-new", "imgfile-basic-dask", rt))
    ctx.meta_state.bind_instance("test2", "ami-new", "run-x")
    report = sq.query_state(ctx)
    assert not [d for d in report.drift if d.kind == "instance"]
    assert not [u for u in report.unavailable if "instances/" in u]
