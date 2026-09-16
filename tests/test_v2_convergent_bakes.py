# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Convergent bakes (stage 9): an image bakes only when its inputs changed,
its parent moved under `parent_policy: follow`, `update.refresh_days` is
due, or the operator forced it -- a second run on a converged tree bakes
nothing, and the bake plan says why for every image.

Cloud-free: the fixture copy gets a seeded lineage whose recorded
fingerprints are the ones the current tree computes (the converged
state), then one input at a time is changed.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, copy_config, load_context, stub_environment

GCE_RT = "gcloud-east1"
AWS_RT = "aws-east2-runtime"
BASE = "basic-rh-10"
DASK = "imgfile-basic-dask"


def _pkr_sources(run: V2Run) -> set[str]:
    """`<series>@<runtime>` for every emitted googlecompute/amazon source."""
    out: set[str] = set()
    for p in run.generated.rglob("*source-*.pkr.hcl"):
        rt = GCE_RT if "pckr-gce" in str(p) else AWS_RT
        name = p.name.split("-source-", 1)[1].rsplit("-block-", 1)[0]
        out.add(f"{name}@{rt}")
    return out


def _set_dask_parent_policy(root: Path, policy: str) -> None:
    p = root / "images" / "image1.yaml"
    d = yaml.safe_load(p.read_text())
    for img in d.get("images") or []:
        if img.get("name") == DASK:
            img["parent_policy"] = policy
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _set_refresh_days(root: Path, days: int) -> None:
    """Add `refresh_days` INSIDE the OS builder's existing `update:` block."""
    p = root / "cfg" / "os-builders.yml"
    text = p.read_text()
    start = text.index(f"  - name: {BASE}\n")
    end = text.find("\n  - name: ", start + 1)
    entry = text[start:end if end != -1 else len(text)]
    assert entry.count("    update:\n") == 1, "the fixture's basic-rh-10 entry declares one update: block"
    entry = entry.replace("    update:\n", f"    update:\n      refresh_days: {days}\n")
    p.write_text(text[:start] + entry + (text[end:] if end != -1 else ""))


def _seed_converged(root: Path, tmp_path: Path, monkeypatch, *, run_id: str = "2026_09_01t00_00_00_000000",
                    dask_policy: str | None = None) -> None:
    """Record a GCE base + dask chain whose fingerprints equal what the tree
    computes now, with the dask pin at the base: a converged state."""
    if dask_policy:
        _set_dask_parent_policy(root, dask_policy)
    stub_environment(monkeypatch)          # never the real clouds
    ctx = load_context(root)
    from cs_image_system.base.lineage import find_image, input_fingerprint
    ms = root / "meta-state"
    ms.mkdir(exist_ok=True)
    base_id, dask_id = f"{BASE}-{GCE_RT}-20260901-000000", f"{DASK}-pckr-gce-ans-20260901-000100"
    (ms / "pins.yaml").write_text(yaml.safe_dump({"images": {f"{DASK}@{GCE_RT}": base_id},
                                                  "instances": {}, "upgrades": []}, sort_keys=True))
    common = {"mods": [], "local_mods": False, "update": None, "tests": {"assertions": 0, "in_bake": True},
              "capabilities": {"identity_types": ["okta"], "storage_types": ["pd", "gcs"]}}

    def write(base_fp: str, dask_fp: str) -> None:
        (ms / "lineage.yaml").write_text(yaml.safe_dump({"builds": [
            {"build_id": base_id, "name": base_id, "series": BASE, "runtime": GCE_RT, "parent": "vendor",
             "run": run_id, "chain": [], "input_fingerprint": base_fp, **common},
            {"build_id": dask_id, "name": dask_id, "series": DASK, "runtime": GCE_RT, "parent": base_id,
             "run": run_id, "chain": [DASK], "input_fingerprint": dask_fp, **common},
        ]}, sort_keys=True))
    # two passes: the child's capability stamp is inherited from the RECORDED
    # parent build (N24), so the records must exist before fingerprinting
    write("", "")
    ctx = load_context(root)
    base_fp = input_fingerprint(ctx, find_image(ctx, BASE, GCE_RT), GCE_RT)
    dask_fp = input_fingerprint(ctx, find_image(ctx, DASK, GCE_RT), GCE_RT)
    write(base_fp, dask_fp)


@pytest.fixture
def converged(tmp_path: Path, monkeypatch):
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


def test_converged_tree_bakes_nothing_on_gce(converged, tmp_path, monkeypatch):
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch)
    run = make()
    summary = run.run(["base-image", "instance-image"], apply=True, only=[f"{BASE}@{GCE_RT}", f"{DASK}@{GCE_RT}"])
    assert summary.ok, summary.error
    assert _pkr_sources(run) == set()
    assert summary.bake_plan[f"{BASE}@{GCE_RT}"].startswith("skip: current (build ")
    assert summary.bake_plan[f"{DASK}@{GCE_RT}"].startswith("skip: current (build ")
    assert summary.bake_plan[f"{DASK}@{AWS_RT}"] == "skip: not selected (--only)"
    assert (run.generated / "run-summary.json").read_text().count("skip: current") >= 2


def test_first_build_and_forced_bakes(converged, tmp_path, monkeypatch):
    root, make = converged
    run = make()   # no lineage at all: everything is a first build
    summary = run.run(["base-image"], apply=True, only=[f"{BASE}@{GCE_RT}"])
    assert summary.ok, summary.error
    assert _pkr_sources(run) == {f"{BASE}@{GCE_RT}"}
    assert summary.bake_plan[f"{BASE}@{GCE_RT}"] == f"bake: no build of {BASE} on {GCE_RT} yet"
    _seed_converged(root, tmp_path, monkeypatch)
    run = make()
    summary = run.run(["base-image"], apply=True, only=[f"{BASE}@{GCE_RT}"])
    assert summary.ok and _pkr_sources(run) == set()          # --only is a pure filter
    run = make()
    summary = run.run(["base-image"], apply=True, only=[f"{BASE}@{GCE_RT}"], force_bake=[BASE])
    assert summary.ok and _pkr_sources(run) == {f"{BASE}@{GCE_RT}"}
    assert summary.bake_plan[f"{BASE}@{GCE_RT}"] == "bake: forced (--force-bake)"


def test_changed_mod_rebakes_only_the_image_that_carries_it(converged, tmp_path, monkeypatch):
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch)
    (root / "setup_dask.yml").write_text((root / "setup_dask.yml").read_text() + "\n# changed\n")
    run = make()
    summary = run.run(["base-image", "instance-image"], apply=True, only=[f"{BASE}@{GCE_RT}", f"{DASK}@{GCE_RT}"])
    assert summary.ok, summary.error
    assert _pkr_sources(run) == {f"{DASK}@{GCE_RT}"}
    assert summary.bake_plan[f"{DASK}@{GCE_RT}"].startswith("bake: inputs changed (")
    assert summary.bake_plan[f"{BASE}@{GCE_RT}"].startswith("skip: current")


def test_changed_base_under_pinned_bakes_the_base_alone_and_reports_stale(converged, tmp_path, monkeypatch):
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch, dask_policy="pinned")   # the fixture's dask follows
    # a new base build recorded AFTER the pin: the child stays on its pin (N17)
    ms = root / "meta-state"
    lineage = yaml.safe_load((ms / "lineage.yaml").read_text())
    newer = dict(lineage["builds"][0]); newer["build_id"] = newer["name"] = f"{BASE}-{GCE_RT}-20260902-000000"
    newer["run"] = "2026_09_02t00_00_00_000000"
    lineage["builds"].append(newer)
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))
    run = make()
    summary = run.run(["instance-image"], apply=True, only=[f"{DASK}@{GCE_RT}"])
    assert summary.ok, summary.error
    assert _pkr_sources(run) == set()                            # pinned: the child does not follow
    from cs_image_system.base.state_query import DRIFT_STALE, image_drift
    drift = image_drift(run.ctx, {GCE_RT: [{"image_id": b["build_id"], "tags": {}} for b in lineage["builds"]]})
    stale = [d for d in drift if d.drift == DRIFT_STALE]
    assert [d.name for d in stale] == [f"{DASK}@{GCE_RT}"] and not stale[0].hard
    assert "behind series head" in stale[0].detail


def test_follow_rebakes_the_child_from_the_new_base_and_moves_the_pin(converged, tmp_path, monkeypatch):
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch, dask_policy="follow")
    ms = root / "meta-state"
    lineage = yaml.safe_load((ms / "lineage.yaml").read_text())
    base_new = f"{BASE}-{GCE_RT}-20260902-000000"
    newer = dict(lineage["builds"][0]); newer["build_id"] = newer["name"] = base_new
    newer["run"] = "2026_09_02t00_00_00_000000"
    lineage["builds"].append(newer)
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))
    run = make()
    summary = run.run(["instance-image"], apply=True, only=[f"{DASK}@{GCE_RT}"])
    assert summary.ok, summary.error
    assert _pkr_sources(run) == {f"{DASK}@{GCE_RT}"}
    assert summary.bake_plan[f"{DASK}@{GCE_RT}"].startswith("bake: parent moved ")
    text = "\n".join(p.read_text() for p in run.generated.rglob(f"*source-{DASK}*.pkr.hcl"))
    assert f'source_image = "{base_new}"' in text or f'"{base_new}"' in text
    # a dry run moved nothing
    assert run.ctx.meta_state.image_pin(DASK, GCE_RT) == f"{BASE}-{GCE_RT}-20260901-000000"
    # the record of a successful bake moves the pin (op: follow)
    from cs_image_system.base.lineage import find_image, record_build
    record_build(run.ctx, find_image(run.ctx, DASK, GCE_RT), GCE_RT, f"{DASK}-pckr-gce-ans-20260902-000100",
                 None, lambda series: None)
    assert run.ctx.meta_state.image_pin(DASK, GCE_RT) == base_new
    ops = [(u["op"], u["from"], u["to"]) for u in run.ctx.meta_state._pins()["upgrades"]]
    assert ("follow", f"{BASE}-{GCE_RT}-20260901-000000", base_new) in ops


def test_refresh_days_rebakes_an_old_head(converged, tmp_path, monkeypatch):
    """`update.refresh_days`: package updates are invisible to the fingerprint,
    so an old-enough head bakes again by age alone."""
    root, make = converged
    _set_refresh_days(root, 30)
    _seed_converged(root, tmp_path, monkeypatch, run_id="2026_08_01t00_00_00_000000")   # ~5 weeks before "now"
    from cs_image_system.base import lineage

    class _Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 7, 12, 0, 0)
    monkeypatch.setattr(lineage, "datetime", _Now)
    run = make()
    summary = run.run(["base-image"], apply=True, only=[f"{BASE}@{GCE_RT}"])
    assert summary.ok, summary.error
    assert summary.bake_plan[f"{BASE}@{GCE_RT}"].startswith("bake: update policy: head ")
    assert _pkr_sources(run) == {f"{BASE}@{GCE_RT}"}
    # a young enough head is current
    _seed_converged(root, tmp_path, monkeypatch, run_id="2026_09_01t00_00_00_000000")
    run = make()
    summary = run.run(["base-image"], apply=True, only=[f"{BASE}@{GCE_RT}"])
    assert summary.ok and _pkr_sources(run) == set()


def test_policies_are_validated(converged, tmp_path, monkeypatch):
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch, dask_policy="sometimes")
    run = make()
    summary = run.run(["instance-image"], apply=False, only=["none"])
    assert not summary.ok
    assert any("parent_policy 'sometimes'" in e for e in summary.validation_errors)


def test_instance_follow_plans_a_replacement_and_moves_the_pin_after_apply(converged, tmp_path, monkeypatch):
    """§9.5: an instance with image_policy: follow is replaced when its
    image's head moves; the pin moves after the apply, not at generation."""
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch)
    ms_dir = root / "meta-state"
    lineage = yaml.safe_load((ms_dir / "lineage.yaml").read_text())
    old_dask = lineage["builds"][1]["build_id"]
    new_dask = f"{DASK}-pckr-gce-ans-20260902-000100"
    newer = dict(lineage["builds"][1]); newer["build_id"] = newer["name"] = new_dask
    newer["run"] = "2026_09_02t00_00_00_000000"
    lineage["builds"].append(newer)
    (ms_dir / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))
    pins = yaml.safe_load((ms_dir / "pins.yaml").read_text())
    pins["instances"]["gce-test"] = old_dask
    (ms_dir / "pins.yaml").write_text(yaml.safe_dump(pins, sort_keys=True))
    (ms_dir / "launch-params.yaml").write_text(yaml.safe_dump(
        {"instances": {"gce-test": {"build": old_dask, "launched": True, "launched_run": "r0", "hostname": "gce-test"}}}))
    inst = root / "instances" / "instances.yaml"
    d = yaml.safe_load(inst.read_text())
    for i in d["instances"]:
        if i["name"] == "gce-test":
            i["image_policy"] = "follow"
    inst.write_text(yaml.safe_dump(d, sort_keys=False))
    run = make()
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.error
    script = (run.generated / "instance-image" / "run-instance-image.sh").read_text()
    assert "-replace=module.instance_gce_test.google_compute_instance.this" in script
    tf = "\n".join(p.read_text() for p in (run.generated / "instance-image" / "tofu-gce").rglob("*.tf"))
    assert new_dask in tf and old_dask not in tf
    assert run.ctx.meta_state.instance_pin("gce-test") == old_dask     # nothing moved by generation
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    run.ctx.config["apply_instances"] = ["gcloud-east1"]
    run.ctx.instance_builders["tofu-gce"].post_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
    assert run.ctx.meta_state.instance_pin("gce-test") == new_dask
    ops = [(u["op"], u["name"]) for u in run.ctx.meta_state._pins()["upgrades"]]
    assert ("follow", "gce-test") in ops
    assert "gce-test" not in run.ctx.meta_state.pending_replacements()


def test_strict_state_query_reports_stale_but_does_not_fail_on_it(monkeypatch, capsys):
    """`stale` is a pin-policy state (upgrade image / follow), not a reality
    mismatch: `state query --strict` prints it and still exits 0; a real
    drift class still fails."""
    import typer
    from cs_image_system.base.state_query import DRIFT_MISSING, DRIFT_STALE, Drift, StateReport
    from cs_image_system.system import cli

    def fake_query(report_drift):
        r = StateReport(run="r")
        r.drift = report_drift
        return r
    monkeypatch.setattr(cli, "GlobalTypeContext", lambda: object(), raising=False)
    import cs_image_system.base.state_query as sq
    monkeypatch.setattr(sq, "query_state", lambda ctx: fake_query([Drift("image", "x@rt", DRIFT_STALE, "behind")]))
    monkeypatch.setattr(sq, "write_state_report", lambda ctx, r: "report.json")
    monkeypatch.setattr("cs_image_system.base.global_context.GlobalTypeContext", lambda: object())
    cli.state_query_command(strict=True, as_json=False)          # exits 0
    assert "stale" in capsys.readouterr().out
    monkeypatch.setattr(sq, "query_state", lambda ctx: fake_query([Drift("image", "y", DRIFT_MISSING, "gone")]))
    with pytest.raises(typer.Exit) as e:
        cli.state_query_command(strict=True, as_json=False)
    assert e.value.exit_code == 1
