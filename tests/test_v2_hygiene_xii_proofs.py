# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XII, group F: the proofs (items 14 and 22).

- The workload probe says whether the token it was issued CARRIES the
  role, by resolving a standing machine of a managed group as the
  workload: `granted`, `not granted`, or `not judged` when none stands.
  Authenticating to the connection alone said `accepted` from any branch,
  pinned or not (the walk's F35).
- On GCE the verification's mount check reads each declared mount point's
  own line from the startup script, and fails when one is missing; the
  kernel's clean XFS mounts counted the image's own filesystems, so the
  check could not fail (the walk's F50).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from test_v2_ephemeral import prepared  # noqa: F401 - the fixture
from test_v2_release_whole import _job_env, _stub_minting
from v2_support import V2Run, copy_config, reset_singletons, stub_environment

runner = CliRunner()


# ------------------------------------------------------------ item 14: the role verdict

def test_the_role_verdict_comes_from_resolving_a_machine_as_the_workload():
    from cs_image_system.base.commands.workload_token import WorkloadNames, probe_role
    names = WorkloadNames("conn", "role", "team", "https://x.pam.okta.com")
    calls: list[tuple] = []

    def resolve(n, token, host):
        calls.append((n, token, host))
        return (0, "") if host == "ok.example.invalid" else (125, "error: no server found\n")
    assert probe_role(names, "tok", "ok.example.invalid", resolve=resolve) == (
        "granted", "sft resolve ok.example.invalid: exit 0 -- the role reaches the machine")
    verdict, detail = probe_role(names, "tok", "no.example.invalid", resolve=resolve)
    assert verdict == "not granted" and detail.startswith("sft resolve no.example.invalid: exit 125 -- error: no server found")
    assert "pinned to another branch" in detail
    assert calls[0] == (names, "tok", "ok.example.invalid")
    verdict, detail = probe_role(names, "tok", None, resolve=resolve)
    assert verdict == "not judged" and "no standing machine" in detail and len(calls) == 2


def test_the_probe_target_is_a_standing_machine_of_a_managed_group(tmp_path, monkeypatch):
    from cs_image_system.base.commands.login_proof import probe_target
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_models import OktaTfGroupBuilderModel
    run = V2Run(tmp_path, monkeypatch)
    try:
        ctx = run.ctx
        assert probe_target(ctx) is None                                  # nothing stands, and no workload names
        for gb in ctx.group_builders.values():
            if isinstance(gb, OktaTfGroupBuilder) and isinstance(gb.model, OktaTfGroupBuilderModel):
                object.__setattr__(gb.model, "workload_connection", "conn")
                object.__setattr__(gb.model, "workload_role", "role")
        assert probe_target(ctx) is None                                  # names, but nothing stands
        ctx.meta_state.record_launch_params("test2", {"launched": True, "hostname": "test2.example.invalid"})
        target = probe_target(ctx)
        assert target is not None and target[0] == "test2.example.invalid" and target[1]
    finally:
        run.restore_cwd()


def test_the_probe_command_prints_both_verdicts_and_exits_0(tmp_path, monkeypatch):
    from cs_image_system.system.cli import app
    from cs_image_system.base.commands import login_proof, workload_token as wt
    stub_environment(monkeypatch)
    reset_singletons()
    root = copy_config(tmp_path)
    _stub_minting(monkeypatch)
    _job_env(monkeypatch, OPA_WORKLOAD_CONNECTION="conn", OPA_WORKLOAD_ROLE="role", SFT_TEAM="team",
             OPA_ADDR="https://x.pam.okta.com")
    monkeypatch.setattr(login_proof, "probe_target", lambda ctx: ("h.example.invalid", "stofs"))
    resolves: list[str] = []
    monkeypatch.setattr(wt, "sft_resolve", lambda n, token, host: (resolves.append(host), (0, ""))[1])
    result = runner.invoke(app, ["--root-dir", str(root), "workload", "probe"])
    assert result.exit_code == 0, result.output
    assert "workload probe: connection conn: accepted this run's token and issued one (masked)" in result.stdout
    assert "workload probe: role role: granted -- sft resolve h.example.invalid: exit 0" in result.stdout
    assert "(group stofs)" in result.stdout and resolves == ["h.example.invalid"]
    assert "opa-token-value" not in result.stdout                        # the token is discarded, never printed
    monkeypatch.setattr(wt, "sft_resolve", lambda n, token, host: (125, "no server found"))
    reset_singletons()
    result = runner.invoke(app, ["--root-dir", str(root), "workload", "probe"])
    assert result.exit_code == 0 and "role role: not granted -- sft resolve h.example.invalid: exit 125" in result.stdout
    monkeypatch.setattr(login_proof, "probe_target", lambda ctx: None)
    reset_singletons()
    result = runner.invoke(app, ["--root-dir", str(root), "workload", "probe"])
    assert result.exit_code == 0 and "role role: not judged -- no standing machine" in result.stdout


def test_every_starter_recipe_and_guide_carry_the_two_verdicts():
    from v2_support import REPO
    for name in ("complete", "standard-aws", "standard-aws-posix", "standard-gce"):
        just = (REPO / "docs" / "examples" / name / "Justfile").read_text()
        assert "@{{cli}} workload probe" in just and "workload token)" not in just.split("opa-workload-probe:")[1].split("\n\n")[0]
        guide = (REPO / "docs" / "examples" / name / "CI_SETUP.md").read_text()
        assert "`role\n   <name>: granted`" in guide or "role <name>: granted" in guide.replace("\n   ", " ")
        assert "dispatch it from any other branch" in guide.replace("\n   ", " ")


# ------------------------------------------------------------ item 22: the mount check

KERNEL_ONLY = """
Sep  8 14:07:27 gce-test systemd[1]: Starting google-startup-scripts.service...
[   12.001059] XFS (sda2): Ending clean mount
[   12.101059] XFS (sda3): Ending clean mount
[   12.201059] XFS (sda4): Ending clean mount
[   47.164059] XFS (sdb): Ending clean mount
Sep  8 14:07:35 gce-test google_metadata_script_runner[1229]: Finished running startup scripts
"""
WITH_MARK = KERNEL_ONLY.replace("Finished running", "startup-script: csis-mount: /mnt/gce-data mounted\n"
                                "Sep  8 14:07:35 gce-test google_metadata_script_runner[1229]: Finished running")


def test_the_startup_script_reports_each_mount_point(tmp_path, monkeypatch):
    from cs_image_system.base.launch_params import compute_launch_params, mounted_points, user_data_template
    run = V2Run(tmp_path, monkeypatch)
    try:
        inst = next(i for i in run.ctx.instances if i.get_name() == "gce-test")
        params = compute_launch_params(run.ctx, inst)
        assert mounted_points(params) == ["/mnt/gce-data"]
        script = user_data_template(params)
        assert "csis-mount: /mnt/gce-data mounted" in script and "csis-mount: /mnt/gce-data NOT mounted" in script
        assert script.index("mount '/mnt/gce-data'") < script.index("csis-mount: /mnt/gce-data mounted")
    finally:
        run.restore_cwd()


def test_gce_mount_check_reads_the_declared_mount_points_lines_not_a_count(prepared, monkeypatch):  # noqa: F811
    from cs_image_system.base.commands.verify_instance import VerificationFailed, verify_instance
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok
    monkeypatch.setattr(GCPCloudBuilder, "query_instance_boot_image", lambda self, name: "dask-build-1")
    monkeypatch.setattr("time.sleep", lambda s: None)
    # four clean XFS mounts on the console, none of them the declared disk: the check FAILS now
    monkeypatch.setattr(GCPCloudBuilder, "serial_console", lambda self, name: KERNEL_ONLY)
    with pytest.raises(VerificationFailed, match="data disks mounted"):
        verify_instance("gce-test", expected_build="dask-build-1", timeout=1)
    rec = run.ctx.meta_state.verifications()[-1]
    check = next(c for c in rec["checks"] if c["name"] == "data disks mounted")
    assert not check["ok"] and "missing: /mnt/gce-data" in check["detail"] and "4 clean XFS" in check["detail"]
    # the script's own line for the mount point: the check passes
    monkeypatch.setattr(GCPCloudBuilder, "serial_console", lambda self, name: WITH_MARK)
    record = verify_instance("gce-test", expected_build="dask-build-1", timeout=1)
    assert record["ok"]
    check = next(c for c in record["checks"] if c["name"] == "data disks mounted")
    assert check["ok"] and "mounted: /mnt/gce-data; missing: none" in check["detail"]
    assert any("csis-mount" in ln for ln in record["evidence"])
    # a caller that names no mount points still gets the count
    rtb = run.ctx.runtime_builders["gcloud-east1"]
    monkeypatch.setattr(GCPCloudBuilder, "serial_console", lambda self, name: KERNEL_ONLY)
    result = rtb.verify_instance("gce-test", expected_build="dask-build-1", expect_mounts=1, timeout=1)
    assert next(c for c in result["checks"] if c["name"] == "data disks mounted")["ok"]
