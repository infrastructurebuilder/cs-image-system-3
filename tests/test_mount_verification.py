# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""On GCE the verification's mount check reads each declared mount point's own line.

The startup script reports each mount point by name; the check fails when
a declared mount point's line is missing, however many clean XFS mounts the
kernel reports (the image's own filesystems once made the check unable to
fail); a caller that names no mount points still gets the count.

history: bundle XII item 22 (walk finding F50).
"""
from __future__ import annotations

import pytest

from test_ephemeral import prepared  # noqa: F401 - the fixture
from harness import V2Run

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
        assert mounted_points(params, run.ctx) == ["/mnt/gce-data"]
        script = user_data_template(params, run.ctx)
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
        verify_instance(run.ctx, "gce-test", expected_build="dask-build-1", timeout=1)
    rec = run.ctx.meta_state.verifications()[-1]
    check = next(c for c in rec["checks"] if c["name"] == "data disks mounted")
    assert not check["ok"] and "/mnt/gce-data" in check["detail"] and "4" in check["detail"]
    # the script's own line for the mount point: the check passes
    monkeypatch.setattr(GCPCloudBuilder, "serial_console", lambda self, name: WITH_MARK)
    record = verify_instance(run.ctx, "gce-test", expected_build="dask-build-1", timeout=1)
    assert record["ok"]
    check = next(c for c in record["checks"] if c["name"] == "data disks mounted")
    assert check["ok"] and "/mnt/gce-data" in check["detail"]
    assert any("csis-mount" in ln for ln in record["evidence"])
    # a caller that names no mount points still gets the count
    rtb = run.ctx.runtime_builders["gcloud-east1"]
    monkeypatch.setattr(GCPCloudBuilder, "serial_console", lambda self, name: KERNEL_ONLY)
    result = rtb.verify_instance("gce-test", expected_build="dask-build-1", expect_mounts=1, timeout=1)
    assert next(c for c in result["checks"] if c["name"] == "data disks mounted")["ok"]
