# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Post-bake image tests and a release that means "known correct" (stage 14).

* `tests.post_bake` (the in-bake vocabulary plus `mounts`) is validated at
  generation and run ON the launched instance by `verify instance` over the
  runtime's session command, as one more check ("declared tests");
* the result is recorded per BUILD in meta-state/image-tests.yaml;
* `release` refuses a build whose image declares post-bake tests but has no
  passing record (config.require_image_tests, default on);
* released builds are exempt from retention and an ephemeral runtime's
  disposal (kept, reported as debt), and `empty --runtime` treats them as
  declared -- the operator's §14.4 decision.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.v2_support import V2Run, copy_config

GCE = "gcloud-east1"
DASK = "imgfile-basic-dask"
BUILD = "imgfile-basic-dask-pckr-gce-ans-20260910-000000"
BASE = "basic-rh-10-gcloud-east1-20260910-000000"


def _seed_gce_chain(run: V2Run) -> None:
    ms = run.ctx.meta_state
    common = {"chain": [], "mods": [], "local_mods": False, "update": None,
              "tests": {"assertions": 3, "in_bake": True},
              "capabilities": {"identity_types": ["okta"], "storage_types": ["pd", "gcs"]}, "runtime": GCE}
    ms.add_build({**common, "build_id": BASE, "series": "basic-rh-10", "name": BASE, "parent": "vendor",
                  "run": "2026_09_10t00_00_00_000000", "input_fingerprint": "0" * 64})
    ms.add_build({**common, "build_id": BUILD, "series": DASK, "name": BUILD, "parent": BASE,
                  "run": "2026_09_10t00_01_00_000000", "input_fingerprint": "1" * 64})
    ms.bind_instance("gce-test", BUILD, "r0")
    ms.record_launch_params("gce-test", {"image": DASK, "build": BUILD, "mounts": [{"storage": "gce_data"}],
                                         "ephemeral": True, "hostname": "gce-test", "launched_run": "r0"})


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path), dry_run=False)
    try:
        yield r
    finally:
        r.restore_cwd()


def test_post_bake_spec_is_validated_and_compiles_to_reportable_assertions(run):
    from cs_image_system.base.image_tests import (parse_post_bake_output, post_bake_assertions,
                                                  post_bake_script, post_bake_spec, validate_tests_spec)
    dask = run.ctx.images_map[DASK]
    spec = post_bake_spec(dask)
    assert spec["mounts"] == ["/mnt/gce-data"] and spec["commands"][0]["run"] == "python3 -c 'import dask'"
    labels = [lbl for lbl, _ in post_bake_assertions(spec)]
    assert labels[-1] == "mount /mnt/gce-data" and len(labels) == 3
    script = post_bake_script(spec)
    assert script.startswith("set +e") and script.count("CSIS_TEST") == 6 and "findmnt -n /mnt/gce-data" in script
    checks = parse_post_bake_output(spec, "CSIS_TEST 0 PASS\nCSIS_TEST 1 PASS\nCSIS_TEST 2 FAIL\n")
    assert [c["ok"] for c in checks] == [True, True, False] and checks[2]["detail"] == "FAIL"
    checks = parse_post_bake_output(spec, "CSIS_TEST 0 PASS\n")            # the session died after one
    assert [c["ok"] for c in checks] == [True, False, False] and "session ended early" in checks[1]["detail"]
    assert validate_tests_spec({"post_bake": {"mounts": ["relative"]}}, "x") == [
        "x.post_bake: every mounts entry is an absolute mount point"]
    assert validate_tests_spec({"post_bake": {"nope": 1}}, "x")[0].startswith("x: unknown tests.post_bake keys ['nope']")
    assert validate_tests_spec({"post_bake": []}, "x") == ["x: tests.post_bake must be a map"]
    assert validate_tests_spec({"files": [{"path": "/a"}], "post_bake": {"users": ["u"]}}, "x") == []


def test_verify_runs_the_suite_on_the_instance_and_records_it_per_build(run, monkeypatch):
    from cs_image_system.base.commands.verify_instance import VerificationFailed, verify_instance
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    _seed_gce_chain(run)
    scripts: list[str] = []
    monkeypatch.setattr(GCPCloudBuilder, "verify_instance", lambda self, name, expected_build=None,
                        expect_mounts=0, timeout=600: {"ok": True, "checks": [
                            {"name": "startup scripts", "ok": True, "detail": "finished"},
                            {"name": "booted image", "ok": True, "detail": f"booted {BUILD}, expected {BUILD}"},
                            {"name": "data disks mounted", "ok": True, "detail": "1 clean"}], "evidence": []})
    monkeypatch.setattr(GCPCloudBuilder, "run_session_command",
                        lambda self, name, script, timeout=300: (scripts.append(script) or
                                                                  (0, "CSIS_TEST 0 PASS\nCSIS_TEST 1 PASS\nCSIS_TEST 2 PASS\n")))
    record = verify_instance("gce-test")
    assert record["ok"] and record["checks"][-1] == {"name": "declared tests", "ok": True,
                                                     "detail": "3 assertion(s) passed"}
    assert scripts and "import dask" in scripts[0]
    result = run.ctx.meta_state.image_tests()[BUILD]
    assert result["ok"] and result["image"] == DASK and result["instance"] == "gce-test"
    assert [c["ok"] for c in result["checks"]] == [True, True, True]
    # a failing assertion fails the verification and records the failure per build
    monkeypatch.setattr(GCPCloudBuilder, "run_session_command",
                        lambda self, name, script, timeout=300: (0, "CSIS_TEST 0 PASS\nCSIS_TEST 1 FAIL\nCSIS_TEST 2 PASS\n"))
    with pytest.raises(VerificationFailed, match="declared tests: 1 of 3 failed"):
        verify_instance("gce-test")
    assert run.ctx.meta_state.image_tests()[BUILD]["ok"] is False


def test_an_image_without_post_bake_tests_verifies_as_before(run, monkeypatch):
    from cs_image_system.base.commands.verify_instance import verify_instance
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    _seed_gce_chain(run)
    run.ctx.images_map[DASK].tests = {}
    monkeypatch.setattr(GCPCloudBuilder, "verify_instance", lambda self, name, **kw: {
        "ok": True, "checks": [{"name": "booted image", "ok": True, "detail": f"booted {BUILD}, expected {BUILD}"}],
        "evidence": []})
    monkeypatch.setattr(GCPCloudBuilder, "run_session_command",
                        lambda self, *a, **k: (_ for _ in ()).throw(AssertionError("no session expected")))
    record = verify_instance("gce-test")
    assert record["ok"] and [c["name"] for c in record["checks"]] == ["booted image"]
    assert run.ctx.meta_state.image_tests() == {}


def test_release_requires_a_passing_post_bake_record_where_declared(run):
    from cs_image_system.base.release import ReleaseError, release
    _seed_gce_chain(run)
    ms = run.ctx.meta_state
    with pytest.raises(ReleaseError, match="has no post-bake test record while 'imgfile-basic-dask' declares"):
        release(run.ctx, DASK, BUILD)
    ms.record_image_test(BUILD, {"ok": False, "run": "r1", "instance": "gce-test", "runtime": GCE, "image": DASK,
                                 "time": "t", "checks": [{"name": "mount /mnt/gce-data", "ok": False, "detail": "FAIL"}]})
    with pytest.raises(ReleaseError, match="failed its post-bake tests in run r1: mount /mnt/gce-data"):
        release(run.ctx, DASK, BUILD)
    ms.record_image_test(BUILD, {"ok": True, "run": "r2", "instance": "gce-test", "runtime": GCE, "image": DASK,
                                 "time": "t", "checks": []})
    entry = release(run.ctx, DASK, BUILD)
    assert entry["build_id"] == BUILD
    # the knob turns the requirement off; a base image (no post-bake tests) is unaffected either way
    run.ctx.config["require_image_tests"] = False
    ms.record_image_test(BUILD, {"ok": False, "run": "r3", "checks": []})
    assert release(run.ctx, DASK, BUILD, model="other")["model"] == "other"
    assert release(run.ctx, "basic-rh-10", BASE)["build_id"] == BASE


def test_released_builds_survive_retention_and_count_as_declared(run, monkeypatch):
    from cs_image_system.base.commands.dispose import retention_plan
    from cs_image_system.base.commands.runtime_facts import emptiness, released_ids
    from cs_image_system.base.release import release
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    _seed_gce_chain(run)
    ms = run.ctx.meta_state
    ms.remove_launch_params("gce-test")
    ms.remove_instance_pin("gce-test", "r1", op="ephemeral")
    run.ctx.runtime_builders[GCE].model.ephemeral = True                  # the runtime keeps nothing...
    disposable, debt = retention_plan(run.ctx, GCE)
    assert {b["build_id"] for b in disposable} == {BASE, BUILD} and debt == []
    ms.record_image_test(BUILD, {"ok": True, "run": "r2", "checks": []})
    release(run.ctx, DASK, BUILD)                                         # ...except a released build
    disposable, debt = retention_plan(run.ctx, GCE)
    assert {b["build_id"] for b in disposable} == {BASE}
    assert [(b["build_id"], why) for b, why in debt] == [(BUILD, "it is a RELEASED build (kept by decision; dispose it explicitly)")]
    assert released_ids(run.ctx, GCE) == {BUILD}
    monkeypatch.setattr(GCPCloudBuilder, "inventory", lambda self: {
        "instances": [], "images": [BUILD], "disks": ["gce-data"], "buckets": ["csis-sandbox-86233086783-default-bucket"]})
    result = emptiness(GCE)
    assert result["empty"] and result["leftovers"]["images"] == []       # a kept release is not a leftover
    monkeypatch.setattr(GCPCloudBuilder, "inventory", lambda self: {
        "instances": [], "images": [BUILD, BASE], "disks": ["gce-data"], "buckets": ["csis-sandbox-86233086783-default-bucket"]})
    assert emptiness(GCE)["leftovers"]["images"] == [BASE]


# ---------------------------------------------- declared releases (ledger 71)

def test_declared_release_targets_the_verified_head_only(run):
    """`release: {model}` on an image: the release lifecycle releases each
    runtime's series head that has a PASSING post-bake record and is not
    already current -- found live: on an ephemeral runtime the operator's
    explicit `release` has no moment between the verification and the
    closing retention, which disposed the verified build first."""
    from cs_image_system.base.release import declared_release_targets, releases
    _seed_gce_chain(run)
    ms = run.ctx.meta_state
    assert run.ctx.images_map[DASK].release == {"model": "default"}
    assert declared_release_targets(run.ctx) == []                        # no passing record yet
    ms.record_image_test(BUILD, {"ok": False, "run": "r1", "checks": []})
    assert declared_release_targets(run.ctx) == []                        # a failed one does not count
    ms.record_image_test(BUILD, {"ok": True, "run": "r2", "checks": []})
    assert declared_release_targets(run.ctx) == [(DASK, GCE, BUILD, "default")]
    summary = run.run(["release"], apply=True, only=["none"])
    assert summary.ok, summary.error
    script = (run.generated / "release" / "run-release.sh").read_text()
    assert "release --declared" in script and "--no-dry-run" in script
    # the deferred step, executed: released, then nothing more to do
    from cs_image_system.base.release import release
    for name, rt, build_id, model in declared_release_targets(run.ctx):
        release(run.ctx, name, build_id, model=model)
    assert releases(ms)["current"]["default"][DASK] == BUILD
    assert declared_release_targets(run.ctx) == []


def test_release_cli_picks_the_runtimes_head(run):
    """`release <image> --runtime <rt>` releases that runtime's series head
    (the head without a runtime is runtime-blind: the most recent record)."""
    from typing import Any, cast

    import typer
    from cs_image_system.system.cli import release_command
    _seed_gce_chain(run)
    ms = run.ctx.meta_state
    ms.record_image_test(BUILD, {"ok": True, "run": "r2", "checks": []})
    release_command(ctx=cast(Any, None), image=DASK, build="", model="default", note="", runtime=GCE, declared=False)
    from cs_image_system.base.release import releases
    assert releases(ms)["current"]["default"][DASK] == BUILD
    with pytest.raises(typer.Exit) as e:
        release_command(ctx=cast(Any, None), image=None, build="", model="default", note="", runtime=None, declared=False)
    assert e.value.exit_code == 2


def test_release_declaration_is_validated(tmp_path, monkeypatch):
    import yaml
    root = copy_config(tmp_path)
    p = root / "images" / "image1.yaml"
    d = yaml.safe_load(p.read_text())
    for img in d["images"]:
        if img["name"] == DASK:
            img["release"] = {"nope": 1}
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["release"], apply=False, only=["none"])
        assert not summary.ok and any("release must be {model: <name>}" in e for e in summary.validation_errors)
    finally:
        run.restore_cwd()
