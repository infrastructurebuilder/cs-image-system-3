# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Image retention and ephemeral runtimes (stage 10.3-6): the closing
`retention` lifecycle disposes of the builds the declared retention no
longer keeps -- beyond `retention.keep` per image / `retention_keep` per
runtime, or everything on an `ephemeral: true` runtime -- never a build an
instance is pinned to or was launched from (retention debt, reported).
Declared storages are never touched.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, command_lines, copy_config

GCE = "gcloud-east1"
AWS = "aws-east2-runtime"


def _seed_builds(root: Path, builds: list[tuple[str, str, str, str]]) -> None:
    """(build_id, series, runtime, run) -- run ids sort chronologically."""
    ms = root / "meta-state"
    ms.mkdir(exist_ok=True)
    common = {"parent": "vendor", "chain": [], "mods": [], "local_mods": False, "update": None,
              "input_fingerprint": "0" * 64, "tests": {"assertions": 0, "in_bake": True},
              "capabilities": {"identity_types": ["okta"], "storage_types": ["pd", "gcs"]}}
    (ms / "lineage.yaml").write_text(yaml.safe_dump({"builds": [
        {"build_id": b, "name": b, "series": s, "runtime": r, "run": run, **common} for b, s, r, run in builds
    ]}, sort_keys=True))


def _set_runtime(root: Path, name: str, **fields) -> None:
    p = root / "cfg" / "runtime-builders.yml"
    d = yaml.safe_load(p.read_text())
    for r in d["runtime_builders"]:
        if r["name"] == name:
            r.update(fields)
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _set_image(root: Path, name: str, **fields) -> None:
    for p in (root / "images").glob("*.y*ml"):
        d = yaml.safe_load(p.read_text())
        changed = False
        for img in d.get("images") or []:
            if img.get("name") == name:
                img.update(fields)
                changed = True
        if changed:
            p.write_text(yaml.safe_dump(d, sort_keys=False))


BUILDS = [
    ("dask-gce-1", "imgfile-basic-dask", GCE, "2026_09_01t00_00_00_000000"),
    ("dask-gce-2", "imgfile-basic-dask", GCE, "2026_09_02t00_00_00_000000"),
    ("dask-gce-3", "imgfile-basic-dask", GCE, "2026_09_03t00_00_00_000000"),
    ("base-gce-1", "basic-rh-10", GCE, "2026_09_01t00_00_00_000000"),
    ("ami-dask-1", "imgfile-basic-dask", AWS, "2026_09_01t00_00_00_000000"),
    ("ami-dask-2", "imgfile-basic-dask", AWS, "2026_09_02t00_00_00_000000"),
]


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


def test_retention_keeps_the_newest_n_and_reports_debt(prepared):
    from cs_image_system.base.commands.dispose import retention_plan
    root, make = prepared
    _seed_builds(root, BUILDS)
    _set_image(root, "imgfile-basic-dask", retention={"keep": 1})
    run = make()
    disposable, debt = retention_plan(run.ctx)
    # keep 1 per runtime: the two older GCE dask builds and the older AWS one
    assert [b["build_id"] for b in disposable] == ["ami-dask-1", "dask-gce-1", "dask-gce-2"]
    assert debt == []
    assert "base-gce-1" not in {b["build_id"] for b in disposable}      # no retention declared
    # a pinned build is debt, never disposed
    run.ctx.meta_state.bind_instance("gce-test", "dask-gce-1", run.ctx.run_id)
    disposable, debt = retention_plan(run.ctx)
    assert [b["build_id"] for b in disposable] == ["ami-dask-1", "dask-gce-2"]
    assert [(b["build_id"], why) for b, why in debt][0][0] == "dask-gce-1"


def test_an_ephemeral_runtime_keeps_nothing_and_the_other_runtime_is_untouched(prepared):
    from cs_image_system.base.commands.dispose import retention_plan
    root, make = prepared
    _seed_builds(root, BUILDS)
    _set_runtime(root, GCE, ephemeral=True)
    run = make()
    disposable, debt = retention_plan(run.ctx)
    assert {b["build_id"] for b in disposable} == {"dask-gce-1", "dask-gce-2", "dask-gce-3", "base-gce-1"}
    assert not any(b["runtime"] == AWS for b in disposable)
    # runtime-level default applies where the image declares none
    _set_runtime(root, GCE, ephemeral=False, retention_keep=2)
    run = make()
    disposable, _ = retention_plan(run.ctx, runtime=GCE)
    assert [b["build_id"] for b in disposable] == ["dask-gce-1"]


def test_the_closing_lifecycle_emits_the_disposal_after_release(prepared):
    root, make = prepared
    _seed_builds(root, BUILDS)
    _set_runtime(root, GCE, ephemeral=True)
    run = make()
    summary = run.run("all", apply=True, only=["none"])
    assert summary.ok, summary.error
    assert summary.requested[-2:] == ["release", "retention"]
    script = run.generated / "retention" / "run-retention.sh"
    assert script.exists()
    lines = command_lines(script.read_text())
    assert any("--no-dry-run dispose image --retention" in ln for ln in lines)
    assert summary.apply["retention"] == "dry-run"


def test_no_retention_declared_means_no_closing_script(prepared):
    root, make = prepared
    _seed_builds(root, BUILDS)
    run = make()
    summary = run.run("all", apply=True, only=["none"])
    assert summary.ok, summary.error
    assert summary.apply["retention"] == "no-script"


def test_retention_disposal_deletes_only_the_disposable_builds(prepared, monkeypatch):
    from cs_image_system.base.commands.dispose import dispose_images
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    deleted: list[str] = []
    monkeypatch.setattr(GCPCloudBuilder, "dispose_image", lambda self, b: deleted.append(b) or True)
    root, make = prepared
    _seed_builds(root, [b for b in BUILDS if b[2] == GCE])
    _set_image(root, "imgfile-basic-dask", retention={"keep": 1})
    run = make(dry_run=False)
    run.ctx.meta_state.bind_instance("gce-test", "dask-gce-1", run.ctx.run_id)
    results = dispose_images(retention=True)
    assert deleted == ["dask-gce-2"] and [r.build_id for r in results] == ["dask-gce-2"]
    assert {b["build_id"] for b in run.ctx.meta_state.builds()} == {"dask-gce-1", "dask-gce-3", "base-gce-1"}


def test_retention_values_are_validated(prepared):
    root, make = prepared
    _set_image(root, "imgfile-basic-dask", retention={"keep": -1})
    _set_runtime(root, GCE, retention_keep=-3)          # a non-int fails at structuring, before validation
    run = make()
    summary = run.run(["instance-image"], apply=False, only=["none"])
    assert not summary.ok
    errs = "\n".join(summary.validation_errors)
    assert "retention must be {keep: <non-negative int>}" in errs
    assert "retention_keep must be a non-negative int" in errs


def test_transient_storages_on_an_ephemeral_runtime_are_torn_down_by_the_closing_phase(tmp_path, monkeypatch):
    """stage 11.4: a storage declared by an overlay on an ephemeral runtime is
    destroyed by THIS run's closing phase -- a storage run without the
    declaring overlay -- not left for the next run."""
    root = copy_config(tmp_path)
    _set_runtime(root, GCE, ephemeral=True)
    overlay = root / "overlays" / "scratch.yaml"
    overlay.write_text("storages:\n  - name: scratch\n    type: gcp-pd\n    groups: [coops]\n"
                       "config:\n  apply_storage: [gcloud-east1]\n")
    knobs = root / "overlays" / "knobs.yaml"
    knobs.write_text("config:\n  apply_instances: [gcloud-east1]\n")
    run = V2Run(tmp_path, monkeypatch, config_root=root, overlays=[overlay, knobs])
    try:
        assert ("storages", "scratch") in run.ctx.overlay_declared
        summary = run.run("all", apply=True, only=["none"])
        assert summary.ok, summary.error
        lines = command_lines((run.generated / "retention" / "run-retention.sh").read_text())
        teardown = next(ln for ln in lines if "run storage --only none" in ln)
        assert '--overlay "$CSIS_ROOT/overlays/knobs.yaml"' in teardown         # config-only overlays carry over
        assert "scratch.yaml" not in teardown and str(root) not in teardown    # ...by reference (stage 38)
        assert "--no-state-query --no-commit" in teardown
        assert lines.index(teardown) > next(i for i, ln in enumerate(lines) if "dispose image --retention" in ln)
    finally:
        run.restore_cwd()
