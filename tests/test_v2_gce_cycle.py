# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""GCE change cycle (stage 8): transient declarations through ``--overlay``
and an explicitly empty bake surface (``--only none``), so a cycle can
launch, verify and tear down on GCE without editing the live tree.

The overlay files under test are the fixture's copies (stage 28: the live
configuration carries no overlays; ``just gce-decommission`` passes
``--undeclare instance:gce-test`` instead, and the overlay ``undeclare`` form
stays as the tests' device).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder

from tests.v2_support import V2Run, command_lines, copy_config

_REAL_GCE_RETAG = GCPCloudBuilder.retag_image     # captured before any harness stub replaces it

GCE_BUILD = "imgfile-basic-dask-pckr-gce-ans-20260906-034343"
GCE_ROOT = "tofu-gce/instance-generation"
AWS_ROOT = "open-tofu/instance-generation"


def _undeclare(root: Path, *names: str) -> None:
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text()) or {}
    d["instances"] = [i for i in (d.get("instances") or []) if i["name"] not in names]
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _seed_launched(root: Path, name: str, build: str, runtime: str) -> None:
    ms = root / "meta-state"
    ms.mkdir(exist_ok=True)
    (ms / "pins.yaml").write_text(yaml.safe_dump(
        {"images": {}, "instances": {name: build}, "upgrades": []}, sort_keys=True))
    (ms / "launch-params.yaml").write_text(yaml.safe_dump(
        {"instances": {name: {"build": build, "launched": False, "hostname": name}}}, sort_keys=True))
    (ms / "lineage.yaml").write_text(yaml.safe_dump({"builds": [{
        "build_id": build, "name": build, "series": "imgfile-basic-dask", "runtime": runtime,
        "parent": "basic-rh-10-gcloud-east1-20260906-033730", "run": "r0", "chain": ["imgfile-basic-dask"],
        "mods": [], "local_mods": False, "input_fingerprint": "0" * 64,
        "tests": {"assertions": 0, "in_bake": True}, "update": None,
        "capabilities": {"identity_types": ["okta"], "storage_types": ["ebs", "efs", "s3", "pd", "gcs"]}}]},
        sort_keys=True))


def _by_workspace(script: str) -> dict[str, dict[str, object]]:
    """Per workspace: apply emitted? which --root / --overlay the apply-check names?"""
    out: dict[str, dict[str, object]] = {}
    for line in command_lines(script):
        ws = line.split('"')[1]
        e = out.setdefault(ws, {"apply": False, "root": None, "overlays": [], "gate": ""})
        if "apply -input=false tfplan" in line:
            e["apply"] = True
        if "apply-check" in line:
            e["root"] = line.split("--root ")[1].split()[0]
            e["overlays"] = [t.split()[0] for t in line.split("--overlay ")[1:]]
        if "gate-plan" in line:
            e["gate"] = line
    return out


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch):
    """A copy with gce-test UNDECLARED (the live tree's shape: the cycle's
    instance exists only through the launch overlay) and a run factory
    taking the overlays to load."""
    root = copy_config(tmp_path)
    _undeclare(root, "gce-test")
    runs: list[V2Run] = []

    def make_run(*overlays: str) -> V2Run:
        run = V2Run(tmp_path, monkeypatch, config_root=root,
                    overlays=[root / "overlays" / o for o in overlays])
        runs.append(run)
        return run
    try:
        yield root, make_run
    finally:
        for run in runs:
            run.restore_cwd()


def test_launch_overlay_declares_the_instance_and_scopes_the_apply(prepared):
    root, make_run = prepared
    run = make_run("gce-cycle-launch.yaml")
    assert [i.get_name() for i in run.ctx.instances if i.get_name() == "gce-test"] == ["gce-test"]
    assert run.ctx.config["apply_instances"] == ["gcloud-east1"]
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.error
    assert summary.overlays == [str((root / "overlays" / "gce-cycle-launch.yaml").resolve())]
    tf = "\n".join(p.read_text() for p in (run.generated / "instance-image" / "tofu-gce").rglob("*.tf"))
    assert 'module "instance_gce_test"' in tf
    ws = _by_workspace((run.generated / "instance-image" / "run-instance-image.sh").read_text())
    assert ws[GCE_ROOT]["apply"] is True and ws[GCE_ROOT]["root"] == "tofu-gce"
    # the script names the overlay through the root reference (stage 38), never an absolute path
    assert ws[GCE_ROOT]["overlays"] == ['"$CSIS_ROOT/overlays/gce-cycle-launch.yaml"']
    assert ws[AWS_ROOT]["apply"] is False            # plans and gates only
    # --only none: the terraform roots alone, no bake surface at all
    assert not list((run.generated / "instance-image").rglob("*.pkr.hcl"))
    # the tree on disk was not touched
    live = yaml.safe_load((root / "instances" / "instances.yaml").read_text())
    assert not any(i["name"] == "gce-test" for i in (live.get("instances") or []))


def test_decommission_overlay_destroys_the_recorded_instance_only(prepared):
    root, make_run = prepared
    _seed_launched(root, "gce-test", GCE_BUILD, "gcloud-east1")
    run = make_run("gce-cycle-decommission.yaml")
    assert not any(i.get_name() == "gce-test" for i in run.ctx.instances)
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.error
    ws = _by_workspace((run.generated / "instance-image" / "run-instance-image.sh").read_text())
    assert "--allow-destroy module.instance_gce_test" in str(ws[GCE_ROOT]["gate"])
    assert ws[GCE_ROOT]["apply"] is True and ws[GCE_ROOT]["root"] == "tofu-gce"
    assert ws[AWS_ROOT]["apply"] is False and "--allow-destroy" not in str(ws[AWS_ROOT]["gate"])


def test_undeclare_flag_decommissions_like_the_overlay_form(prepared, tmp_path, monkeypatch):
    """Stage 28: ``--undeclare instance:gce-test`` is the decommission overlay
    without the file -- a live configuration needs no overlay to destroy a
    leftover standing instance through the gate."""
    root, _ = prepared
    _seed_launched(root, "gce-test", GCE_BUILD, "gcloud-east1")
    run = V2Run(tmp_path, monkeypatch, config_root=root, undeclare=["instance:gce-test"])
    try:
        # the recipe's --apply-runtime (the knob the overlay used to carry), as
        # the CLI applies it before run_lifecycles -- the harness has no CLI
        run.ctx.apply_runtime = run.ctx.implied_scope = "gcloud-east1"
        run.ctx.config["apply_instances"] = ["gcloud-east1"]
        assert run.ctx.undeclared == [("instances", "gce-test")]
        assert not any(i.get_name() == "gce-test" for i in run.ctx.instances)
        summary = run.run(["instance-image"], apply=True, only=["none"])
        assert summary.ok, summary.error
        assert summary.overlays == [] and summary.undeclared == ["instances:gce-test"]
        ws = _by_workspace((run.generated / "instance-image" / "run-instance-image.sh").read_text())
        assert "--allow-destroy module.instance_gce_test" in str(ws[GCE_ROOT]["gate"])
        assert ws[GCE_ROOT]["apply"] is True and ws[GCE_ROOT]["overlays"] == []   # nothing to re-read at apply
        assert ws[AWS_ROOT]["apply"] is False
    finally:
        run.restore_cwd()


def test_undeclare_is_validated_up_front():
    from cs_image_system.base.global_context import parse_undeclare
    assert parse_undeclare(["instance:gce-test", "storages:scratch"]) == [("instances", "gce-test"), ("storages", "scratch")]
    with pytest.raises(ValueError, match="expected <kind>:<name>"):
        parse_undeclare(["gce-test"])
    with pytest.raises(ValueError, match="unknown kind"):
        parse_undeclare(["widget:x"])


def test_storage_teardown_overlay_tombstones_the_cycle_storages(prepared):
    root, make_run = prepared
    run = make_run("gce-cycle-storage-teardown.yaml")
    states = {s.get_name(): s.state for s in run.ctx.storages}
    assert states["gce_data"] == "destroyed" and states["gce_bucket"] == "destroyed"
    assert states["mnt_data"] == "active"
    # the recorded state is active (a real cycle created them): destroyed is a transition
    ms = run.ctx.meta_state
    for name in ("gce_data", "gce_bucket"):
        ms.record_storage_transition(name, None, "active", "r0")
    summary = run.run(["storage"], apply=True)
    assert summary.ok, summary.error
    script = (run.generated / "storage" / "run-storage.sh").read_text()
    assert "--allow-destroy module.storage_gce_data" in script
    assert "--allow-destroy module.storage_gce_bucket" in script
    # the wipe is a generated script tolerant of an EMPTY bucket (found live)
    assert "bash wipe-gce_bucket.sh" in script
    wipe = (run.generated / "storage" / "gcp-gcs" / "storage-generation" / "wipe-gce_bucket.sh").read_text()
    assert 'gcloud storage rm --recursive "gs://csis-sandbox-86233086783-default-bucket/**"' in wipe
    assert "matched no objects" in wipe and "exit 0" in wipe
    ws = _by_workspace(script)
    applied = {e["root"] for e in ws.values() if e["apply"]}
    assert applied == {"gcp-pd", "gcp-gcs"}
    assert all("--allow-destroy" not in str(e["gate"]) for w, e in ws.items() if w.startswith("aws-"))


def test_overlays_are_validated_up_front(tmp_path: Path):
    from cs_image_system.base.global_context import load_overlay
    bad = tmp_path / "bad.yaml"
    bad.write_text("instnaces: []\n")
    with pytest.raises(ValueError, match="unknown top-level key"):
        load_overlay(bad)
    bad.write_text("instances:\n  - image: x\n")          # no name
    with pytest.raises(ValueError, match="named entries"):
        load_overlay(bad)
    with pytest.raises(ValueError, match="does not exist"):
        load_overlay(tmp_path / "missing.yaml")
    good = tmp_path / "good.yaml"
    good.write_text("config:\n  apply_storage: [gcp-pd]\nstorages:\n  - name: gce_data\n    state: destroyed\n")
    assert load_overlay(good)["config"] == {"apply_storage": ["gcp-pd"]}


def test_apply_check_rereads_the_overlay_config(prepared, capsys):
    """The runner script generated under an overlay re-checks under that
    overlay: the file says false, the overlay lists the GCE runtime."""
    import typer
    from cs_image_system.system.cli import apply_check_command
    root, _ = prepared
    launch = root / "overlays" / "gce-cycle-launch.yaml"
    os.chdir(root / "cfg")
    apply_check_command(lifecycle="instances", config_root=None, apply_root="tofu-gce",
                        root_alias=["gcloud-east1"], overlay=[launch])
    with pytest.raises(typer.Exit) as e:
        apply_check_command(lifecycle="instances", config_root=None, apply_root="open-tofu",
                            root_alias=["aws-east2-runtime"], overlay=[launch])
    assert e.value.exit_code == 3
    assert "for root 'open-tofu'" in capsys.readouterr().err
    with pytest.raises(typer.Exit) as e:                # no overlay: the file's false stands
        apply_check_command(lifecycle="instances", config_root=None, apply_root="tofu-gce",
                            root_alias=["gcloud-east1"])
    assert e.value.exit_code == 3
    with pytest.raises(typer.Exit) as e:                # the overlay vanished: refuse
        apply_check_command(lifecycle="instances", config_root=None, apply_root="tofu-gce",
                            root_alias=["gcloud-east1"], overlay=[root / "overlays" / "gone.yaml"])
    assert e.value.exit_code == 3


def test_only_none_bakes_nothing(tmp_path: Path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        summary = run.run(["base-image", "instance-image"], apply=True, only=["none"])
        assert summary.ok, summary.error
        assert not list(run.generated.rglob("*.pkr.hcl"))
        assert (run.generated / "instance-image" / "run-instance-image.sh").exists()
    finally:
        run.restore_cwd()


# ------------------------------------------------------------ dispose image

BASE_BUILD = "basic-rh-10-gcloud-east1-20260906-033730"


def _seed_gce_chain(root: Path) -> None:
    """Lineage with the GCE base + dask builds and one AWS build; the dask
    image's parent pin at the base (the live shape)."""
    ms = root / "meta-state"
    ms.mkdir(exist_ok=True)
    common = {"mods": [], "local_mods": False, "input_fingerprint": "0" * 64, "update": None,
              "tests": {"assertions": 0, "in_bake": True},
              "capabilities": {"identity_types": ["okta"], "storage_types": ["pd", "gcs"]}}
    (ms / "lineage.yaml").write_text(yaml.safe_dump({"builds": [
        {"build_id": BASE_BUILD, "name": BASE_BUILD, "series": "basic-rh-10", "runtime": "gcloud-east1",
         "parent": "vendor", "run": "r0", "chain": ["basic-rh-10"], **common},
        {"build_id": GCE_BUILD, "name": GCE_BUILD, "series": "imgfile-basic-dask", "runtime": "gcloud-east1",
         "parent": BASE_BUILD, "run": "r1", "chain": ["imgfile-basic-dask"], **common},
        {"build_id": "ami-0829ccceee6db194e", "name": "aws-dask", "series": "imgfile-basic-dask",
         "runtime": "aws-east2-runtime", "parent": "ami-base", "run": "r2", "chain": ["imgfile-basic-dask"], **common},
    ]}, sort_keys=True))
    (ms / "pins.yaml").write_text(yaml.safe_dump(
        {"images": {"imgfile-basic-dask@gcloud-east1": BASE_BUILD,
                    "imgfile-basic-dask@aws-east2-runtime": "ami-base"},
         "instances": {}, "upgrades": []}, sort_keys=True))


@pytest.fixture
def stub_gce_delete(monkeypatch):
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    deleted: list[str] = []
    monkeypatch.setattr(GCPCloudBuilder, "dispose_image", lambda self, build_id: deleted.append(build_id) or True)
    return deleted


def test_dispose_dry_run_deletes_nothing_and_reports_the_plan(tmp_path, monkeypatch, stub_gce_delete):
    from cs_image_system.base.commands.dispose import dispose_images
    root = copy_config(tmp_path)
    _seed_gce_chain(root)
    run = V2Run(tmp_path, monkeypatch, config_root=root)          # dry_run=True
    try:
        results = dispose_images(runtime="gcloud-east1", all_on_runtime=True)
        assert [r.build_id for r in results] == [GCE_BUILD, BASE_BUILD]   # children first
        assert all(r.deleted is None for r in results)
        assert results[1].unpinned == ["imgfile-basic-dask@gcloud-east1"]
        assert stub_gce_delete == []
        assert len(run.ctx.meta_state.builds()) == 3                       # nothing recorded
        assert run.ctx.meta_state.image_pin("imgfile-basic-dask", "gcloud-east1") == BASE_BUILD
    finally:
        run.restore_cwd()


def test_dispose_deletes_drops_records_and_unpins(tmp_path, monkeypatch, stub_gce_delete):
    from cs_image_system.base.commands.dispose import dispose_images
    root = copy_config(tmp_path)
    _seed_gce_chain(root)
    run = V2Run(tmp_path, monkeypatch, config_root=root, dry_run=False)
    try:
        results = dispose_images(runtime="gcloud-east1", all_on_runtime=True)
        assert stub_gce_delete == [GCE_BUILD, BASE_BUILD]
        assert all(r.deleted is True for r in results)
        ms = run.ctx.meta_state
        assert [b["build_id"] for b in ms.builds()] == ["ami-0829ccceee6db194e"]   # the AWS build stays
        assert ms.image_pin("imgfile-basic-dask", "gcloud-east1") is None
        assert ms.image_pin("imgfile-basic-dask", "aws-east2-runtime") == "ami-base"
        ops = [(u["op"], u["name"], u["from"]) for u in ms._pins()["upgrades"]]
        assert ops == [("dispose", "imgfile-basic-dask@gcloud-east1", BASE_BUILD)]
        # the next dask bake first-binds again instead of baking from a deleted parent
        from cs_image_system.base.lineage import pinned_parent_build
        assert pinned_parent_build(run.ctx, run.ctx.images_map["imgfile-basic-dask"], "gcloud-east1") is None
    finally:
        run.restore_cwd()


def test_dispose_refuses_unrecorded_and_in_use_builds(tmp_path, monkeypatch, stub_gce_delete):
    from cs_image_system.base.commands.dispose import dispose_images
    root = copy_config(tmp_path)
    _seed_gce_chain(root)
    ms_dir = root / "meta-state"
    pins = yaml.safe_load((ms_dir / "pins.yaml").read_text())
    pins["instances"]["gce-test"] = GCE_BUILD                     # a launched instance runs it
    (ms_dir / "pins.yaml").write_text(yaml.safe_dump(pins, sort_keys=True))
    run = V2Run(tmp_path, monkeypatch, config_root=root, dry_run=False)
    try:
        with pytest.raises(ValueError, match="not recorded in lineage"):
            dispose_images(["no-such-build"])
        with pytest.raises(ValueError, match="decommission them first"):
            dispose_images([GCE_BUILD])
        with pytest.raises(ValueError, match="decommission them first"):
            dispose_images(runtime="gcloud-east1", all_on_runtime=True)
        with pytest.raises(ValueError, match="was baked on"):
            dispose_images([BASE_BUILD], runtime="aws-east2-runtime")
        assert stub_gce_delete == [] and len(run.ctx.meta_state.builds()) == 3
        # the base alone is disposable (no instance on it): explicit id works
        results = dispose_images([BASE_BUILD])
        assert stub_gce_delete == [BASE_BUILD] and results[0].unpinned == ["imgfile-basic-dask@gcloud-east1"]
    finally:
        run.restore_cwd()


def test_dispose_refuses_a_runtime_that_cannot_dispose(tmp_path, monkeypatch, stub_gce_delete):
    """A runtime without the hook refuses (AWS implements it since TODO
    §11.1, so the base behaviour is stubbed back for this proof)."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
    from cs_image_system.base.commands.dispose import dispose_images
    monkeypatch.setattr(AwsCloudBuilder, "dispose_image", RuntimeBuilderBase.dispose_image)
    root = copy_config(tmp_path)
    _seed_gce_chain(root)
    run = V2Run(tmp_path, monkeypatch, config_root=root, dry_run=False)
    try:
        with pytest.raises(NotImplementedError, match="cannot dispose"):
            dispose_images(["ami-0829ccceee6db194e"])
        assert len(run.ctx.meta_state.builds()) == 3                       # nothing recorded
    finally:
        run.restore_cwd()


# --------------------------------------------------- step 6: readiness leftovers

def test_gce_bakes_are_preemptible_when_the_runtime_says_so(tmp_path, monkeypatch):
    """GCP-READINESS §6: the runtime's bake_preemptible lands on the
    googlecompute source (spot build VMs; a preempted bake re-runs)."""
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["base-image"], apply=False, only=["basic-rh-10@gcloud-east1"]).ok
        text = "\n".join(p.read_text() for p in run.generated.rglob("*.pkr.hcl") if "source-" in p.name)
        assert "preemptible = true" in text
    finally:
        run.restore_cwd()


def test_gcs_state_lookup_goes_through_gcloud(tmp_path, monkeypatch):
    """GCP-READINESS §7 parity: the bucket is looked up with
    `gcloud storage buckets describe` -- present, absent (not found), or
    unavailable (any other failure raises, so the query reports it)."""
    import subprocess
    from types import SimpleNamespace
    run = V2Run(tmp_path, monkeypatch)
    try:
        from cs_image_system.tf_gcp_plugin.tf_gcp_storage_builder import TofuGcsStorageBuilder
        builder = run.ctx.storage_builders["gcp-gcs"]
        assert isinstance(builder, TofuGcsStorageBuilder)
        bucket = next(s for s in run.ctx.storages if s.get_name() == "gce_bucket")
        calls: list[list[str]] = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return fake_run.result
        monkeypatch.setattr(subprocess, "run", fake_run)
        fake_run.result = SimpleNamespace(returncode=0, stderr="", stdout=(
            '{"name": "csis-sandbox-86233086783-default-bucket", "location": "US-EAST1", '
            '"storageClass": "STANDARD", "labels": {"csis_storage": "gce-bucket"}}'))
        rec = builder._lookup(bucket)
        assert rec == {"id": "csis-sandbox-86233086783-default-bucket", "state": "active",
                       "location": "US-EAST1", "storage_class": "STANDARD",
                       "tags": {"csis_storage": "gce-bucket"}}
        # stage 63 item 14: the declared binary, not a bare name from PATH
        assert calls[-1][:4] == ["/usr/local/bin/gcloud", "storage", "buckets", "describe"]
        assert calls[-1][4] == "gs://csis-sandbox-86233086783-default-bucket"
        fake_run.result = SimpleNamespace(returncode=1, stdout="", stderr="ERROR: ... 404 ... not found")
        assert builder._lookup(bucket) is None
        fake_run.result = SimpleNamespace(returncode=1, stdout="", stderr="ERROR: reauthentication required")
        with pytest.raises(RuntimeError, match="buckets describe"):
            builder._lookup(bucket)
    finally:
        run.restore_cwd()


# ---------------------------------------------------- relabel (ledger 66)

def test_gce_retag_merges_lineage_truth_into_the_image_labels(tmp_path, monkeypatch):
    """A follow image baked in the same run as its parent carries
    generation-time labels (`csis_parent: series-…`, a placeholder
    fingerprint); after the bake the runtime relabels it from the record,
    keeping every other label and the label fingerprint GCE requires."""
    from cs_image_system.gcloud_runtime import gcp_utils

    class Image:
        labels = {"csis_parent": "series-basic-rh-10", "csis_fingerprint": "293d6de5ab5f3b4f",
                  "csis_series": "imgfile-basic-dask", "dask": "true"}
        label_fingerprint = "abc123="

    class Op:
        def result(self):
            return None

    class FakeImages:
        def __init__(self):
            self.calls: list[dict] = []

        def get(self, project, image):
            self.calls.append({"get": (project, image)})
            return Image()

        def set_labels(self, project, resource, global_set_labels_request_resource):
            req = global_set_labels_request_resource
            self.calls.append({"set": (project, resource, req.label_fingerprint, dict(req.labels))})
            return Op()

    fake = FakeImages()
    monkeypatch.setattr(gcp_utils, "_make_images_client", lambda cfg: fake)
    root = copy_config(tmp_path)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        rtb = run.ctx.runtime_builders["gcloud-east1"]
        assert isinstance(rtb, GCPCloudBuilder)
        assert _REAL_GCE_RETAG(rtb, GCE_BUILD, {                      # the real hook, not the harness stub
            "csis_parent": "basic-rh-10-gcloud-east1-20260906-034343",
            "csis_fingerprint": "1733b718d8c52101"}) is True
        assert fake.calls[0] == {"get": ("csis-sandbox", GCE_BUILD)}
        project, resource, fp, labels = fake.calls[1]["set"]
        assert (project, resource, fp) == ("csis-sandbox", GCE_BUILD, "abc123=")
        assert labels == {"csis_parent": "basic-rh-10-gcloud-east1-20260906-034343",
                          "csis_fingerprint": "1733b718d8c52101",
                          "csis_series": "imgfile-basic-dask", "dask": "true"}
    finally:
        run.restore_cwd()


# ------------------------------------------------ overlay undeclare (ledger 68)

def test_an_overlay_can_undeclare_a_tree_entry_for_one_invocation(prepared, tmp_path):
    """`{name: X, undeclare: true}` removes the tree's entry for this run only:
    a launched instance decommissions through the gate exactly as if its
    entry had left the YAML; the tree on disk is untouched."""
    root, make_run = prepared
    _seed_launched(root, "test2", "ami-dask-1", "aws-east2-runtime")
    overlay = tmp_path / "undeclare-test2.yaml"
    overlay.write_text("instances:\n  - name: test2\n    undeclare: true\nconfig:\n  apply_instances: [aws-east2-runtime]\n")
    run = make_run(str(overlay))
    assert not any(i.get_name() == "test2" for i in run.ctx.instances)
    assert any(i.get_name() == "test" for i in run.ctx.instances)          # the others stay
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.error
    ws = _by_workspace((run.generated / "instance-image" / "run-instance-image.sh").read_text())
    assert "--allow-destroy module.instance_test2" in str(ws[AWS_ROOT]["gate"])
    live = yaml.safe_load((root / "instances" / "instances.yaml").read_text())
    assert any(i["name"] == "test2" for i in live["instances"])            # the tree still declares it
