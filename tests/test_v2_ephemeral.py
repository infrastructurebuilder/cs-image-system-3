# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Declared ephemerality (stage 10.1-2): an instance with `ephemeral: true`
is launched through the gate, verified through its runtime, and torn down
by the same root in the same run; a failed verification stops the runner
with the instance standing (operator decision), and the state query says
so afterwards.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, command_lines, copy_config

GCE_ROOT = "tofu-gce/instance-generation"


def _declare_ephemeral(root: Path, name: str) -> None:
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    for i in d["instances"]:
        if i["name"] == name:
            i["ephemeral"] = True
    p.write_text(yaml.safe_dump(d, sort_keys=False))


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _declare_ephemeral(root, "gce-test")
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


def _lines_in(script: str, workspace: str) -> list[str]:
    return [ln for ln in command_lines(script) if ln.split('"')[1] == workspace]


def test_ephemeral_root_launches_verifies_and_tears_down_in_one_sequence(prepared):
    root, make = prepared
    run = make()
    run.ctx.config["apply_instances"] = ["gcloud-east1"]
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.error
    tf = "\n".join(p.read_text() for p in (run.generated / "instance-image" / "tofu-gce").rglob("*.tf"))
    assert 'variable "ephemeral_present"' in tf
    assert "count = var.ephemeral_present ? 1 : 0" in tf
    lines = _lines_in((run.generated / "instance-image" / "run-instance-image.sh").read_text(), GCE_ROOT)
    joined = "\n".join(lines)
    launch_apply = next(i for i, ln in enumerate(lines) if "apply -input=false tfplan" in ln)
    verify = next(i for i, ln in enumerate(lines) if "verify instance gce-test" in ln)
    teardown_plan = next(i for i, ln in enumerate(lines) if "-var=ephemeral_present=false" in ln)
    assert launch_apply < verify < teardown_plan
    assert "--allow-destroy module.instance_gce_test" in joined
    assert joined.count("apply -input=false tfplan") == 2          # launch, then teardown
    assert joined.count("apply-check --lifecycle instances --root tofu-gce") == 2
    # launch parameters know the instance is ephemeral
    assert run.ctx.meta_state.launch_params()["gce-test"]["ephemeral"] is True


def test_ephemeral_sequence_is_absent_when_the_root_may_not_apply(prepared):
    root, make = prepared
    run = make()                                          # apply_instances false
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.error
    script = (run.generated / "instance-image" / "run-instance-image.sh").read_text()
    assert "verify instance" not in script and "ephemeral_present=false" not in script


def test_forget_ephemerals_drops_the_records_after_a_real_apply(prepared):
    from cs_image_system.base.launch_params import forget_ephemerals
    from cs_image_system.base.lifecycles import Lifecycle
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=True, only=["none"]).ok
    ms = run.ctx.meta_state
    ms.bind_instance("gce-test", "some-build", run.ctx.run_id)
    assert "gce-test" in ms.launch_params()
    run.ctx.config["apply_instances"] = ["aws-east2-runtime"]        # the GCE root only planned
    forget_ephemerals(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert "gce-test" in ms.launch_params() and ms.instance_pin("gce-test") == "some-build"
    run.ctx.config["apply_instances"] = ["gcloud-east1"]
    forget_ephemerals(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert "gce-test" not in ms.launch_params() and ms.instance_pin("gce-test") is None
    assert [u["op"] for u in ms._pins()["upgrades"]][-1] == "ephemeral"
    assert "test" in ms.launch_params()                              # non-ephemerals untouched


CONSOLE_OK = """
Sep  8 14:07:27 gce-test systemd[1]: Starting google-startup-scripts.service...
[   47.164059] XFS (sdb): Ending clean mount
Sep  8 14:07:35 gce-test google_metadata_script_runner[1229]: Finished running startup scripts
"""
CONSOLE_FAIL = "Sep  8 14:07:35 gce-test google_metadata_script_runner[1229]: startup-script exit status 1\n"


def test_gce_verification_reads_the_serial_console_and_records_the_verdict(prepared, monkeypatch):
    from cs_image_system.base.commands.verify_instance import VerificationFailed, verify_instance
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok
    monkeypatch.setattr(GCPCloudBuilder, "serial_console", lambda self, name: CONSOLE_OK)
    monkeypatch.setattr(GCPCloudBuilder, "query_instance_boot_image", lambda self, name: "dask-build-1")
    monkeypatch.setattr("time.sleep", lambda s: None)
    record = verify_instance("gce-test", expected_build="dask-build-1", timeout=1)
    assert record["ok"] and record["ephemeral"] is True
    names = {c["name"]: c["ok"] for c in record["checks"]}
    assert names == {"startup scripts": True, "booted image": True, "data disks mounted": True,
                     "declared tests": True}          # stage 14: the dask image declares post-bake tests
    assert run.ctx.meta_state.verifications()[-1]["instance"] == "gce-test"
    # an explicit failure line fails fast, and the record says which check
    monkeypatch.setattr(GCPCloudBuilder, "serial_console", lambda self, name: CONSOLE_FAIL)
    with pytest.raises(VerificationFailed, match="startup scripts: an explicit failure line"):
        verify_instance("gce-test", expected_build="dask-build-1", timeout=1)
    assert run.ctx.meta_state.verifications()[-1]["ok"] is False
    # a wrong booted image fails too
    monkeypatch.setattr(GCPCloudBuilder, "serial_console", lambda self, name: CONSOLE_OK)
    with pytest.raises(VerificationFailed, match="booted image"):
        verify_instance("gce-test", expected_build="dask-build-2", timeout=1)
    # no completion within the timeout
    monkeypatch.setattr(GCPCloudBuilder, "serial_console", lambda self, name: "booting...\n")
    with pytest.raises(VerificationFailed, match="no completion"):
        verify_instance("gce-test", expected_build="dask-build-1", timeout=0)


def test_a_runtime_without_verification_refuses(prepared, monkeypatch):
    """A runtime that does not implement the hook refuses cleanly (AWS
    implements it since stage 11.1, so the base behaviour is stubbed back)."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
    from cs_image_system.base.commands.verify_instance import verify_instance
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok
    monkeypatch.setattr(AwsCloudBuilder, "verify_instance", RuntimeBuilderBase.verify_instance)
    with pytest.raises(NotImplementedError, match="cannot verify"):
        verify_instance("test")


def test_state_query_reports_a_standing_ephemeral(prepared, monkeypatch):
    from cs_image_system.base.state_query import DRIFT_CHANGED, StateReport, standing_ephemeral_drift
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok   # records gce-test (ephemeral)
    monkeypatch.setattr(GCPCloudBuilder, "query_instance_boot_image", lambda self, name: "dask-build-1")
    drift = standing_ephemeral_drift(run.ctx, StateReport(run="r"))
    assert [(d.kind, d.name, d.drift, d.hard) for d in drift] == [("instance", "gce-test", DRIFT_CHANGED, False)]
    assert "STANDING" in drift[0].detail
    monkeypatch.setattr(GCPCloudBuilder, "query_instance_boot_image", lambda self, name: None)
    assert standing_ephemeral_drift(run.ctx, StateReport(run="r")) == []


def test_verification_without_a_pin_accepts_a_recorded_build_of_the_series(prepared, monkeypatch):
    """Found live: an instance whose image was baked in the same run has no
    pin and a launch record saying `unbound`; the booted image must then be
    a recorded build of its image's series, never compared with 'unbound'."""
    from cs_image_system.base.commands.verify_instance import VerificationFailed, verify_instance
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok
    ms = run.ctx.meta_state
    assert ms.launch_params()["gce-test"]["build"] == "unbound" and ms.instance_pin("gce-test") is None
    ms.add_build({"build_id": "dask-gce-9", "series": "imgfile-basic-dask", "runtime": "gcloud-east1",
                  "name": "dask-gce-9", "parent": "vendor", "run": "r9"})
    monkeypatch.setattr(GCPCloudBuilder, "serial_console", lambda self, name: CONSOLE_OK)
    monkeypatch.setattr(GCPCloudBuilder, "query_instance_boot_image", lambda self, name: "dask-gce-9")
    monkeypatch.setattr("time.sleep", lambda s: None)
    record = verify_instance("gce-test", timeout=1)
    assert record["ok"] and record["build"] == "dask-gce-9"
    assert "a recorded build of imgfile-basic-dask" in next(c["detail"] for c in record["checks"] if c["name"] == "booted image")
    monkeypatch.setattr(GCPCloudBuilder, "query_instance_boot_image", lambda self, name: "someone-elses-image")
    with pytest.raises(VerificationFailed, match="lineage does not record"):
        verify_instance("gce-test", timeout=1)


# --------------------------------------------- failure policy (stage 11.3)

def _set_instance(root: Path, name: str, **fields) -> None:
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    for i in d["instances"]:
        if i["name"] == name:
            i.update(fields)
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _set_runtime(root: Path, name: str, **fields) -> None:
    p = root / "cfg" / "runtime-builders.yml"
    d = yaml.safe_load(p.read_text())
    for r in d["runtime_builders"]:
        if r["name"] == name:
            r.update(fields)
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _record_failed_verification(run: V2Run, name: str, when: str) -> None:
    run.ctx.meta_state.record_verification({"instance": name, "run": "r0", "ok": False, "time": when,
                                            "checks": [{"name": "booted image", "ok": False, "detail": "x"}]})


def test_teardown_policy_records_the_verdict_tears_down_and_fails_afterwards(prepared):
    root, make = prepared
    _set_instance(root, "gce-test", on_failure="teardown")
    run = make()
    run.ctx.config["apply_instances"] = ["gcloud-east1"]
    assert run.run(["instance-image"], apply=True, only=["none"]).ok
    lines = _lines_in((run.generated / "instance-image" / "run-instance-image.sh").read_text(), GCE_ROOT)
    verify = next(i for i, ln in enumerate(lines) if "verify instance gce-test --record-only" in ln)
    teardown_apply = [i for i, ln in enumerate(lines) if "apply -input=false tfplan" in ln][-1]
    assert verify < teardown_apply
    # ledger 68: the failed verdict fails the run from the after-apply hook
    # (after the records are forgotten), never from the script's last step
    assert not any("verify assert" in ln for ln in lines)


def test_teardown_policy_forgets_the_record_before_failing_the_run(prepared):
    """Live 2026-09-09: a `verify assert` as the runner's last step failed the
    script before the after-apply hook ran, so a torn-down ephemeral kept its
    launch record. Now the hook forgets first, then raises the verdict."""
    from cs_image_system.base.commands.verify_instance import VerificationFailed
    from cs_image_system.base.launch_params import forget_ephemerals
    from cs_image_system.base.lifecycles import Lifecycle
    root, make = prepared
    _set_instance(root, "gce-test", on_failure="teardown")
    run = make()
    run.ctx.config["apply_instances"] = ["gcloud-east1"]
    ms = run.ctx.meta_state
    ms.record_launch_params("gce-test", {"image": "imgfile-basic-dask", "build": "b1", "mounts": [], "ephemeral": True,
                                         "hostname": "gce-test", "launched_run": "r0"})
    _record_failed_verification(run, "gce-test", "2026-09-09T14:37:44+00:00")
    with pytest.raises(VerificationFailed, match="gce-test failed verification: booted image: x"):
        forget_ephemerals(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert "gce-test" not in ms.launch_params()                       # forgotten before the raise
    assert not any(v.get("ok") for v in ms.verifications())            # the verdict stays recorded
    # under `keep` (the default) the hook never sees a failed verdict: the script stopped first
    _set_instance(root, "gce-test", on_failure="keep")
    run = make()
    run.ctx.config["apply_instances"] = ["gcloud-east1"]
    run.ctx.meta_state.record_launch_params("gce-test", {"image": "imgfile-basic-dask", "build": "b1", "mounts": [],
                                                         "ephemeral": True, "hostname": "gce-test", "launched_run": "r0"})
    forget_ephemerals(run.ctx, Lifecycle.INSTANCE_IMAGE)              # a passed run: no raise


def test_runtime_default_policy_and_instance_precedence(prepared):
    from cs_image_system.base.commands.verify_instance import failure_policy
    root, make = prepared
    _set_runtime(root, "gcloud-east1", on_failure="teardown", teardown_after="2h")
    run = make()
    inst = next(i for i in run.ctx.instances if i.get_name() == "gce-test")
    assert failure_policy(run.ctx, inst) == ("teardown", 7200)
    _set_instance(root, "gce-test", on_failure="keep", teardown_after="30m")
    run = make()
    inst = next(i for i in run.ctx.instances if i.get_name() == "gce-test")
    assert failure_policy(run.ctx, inst) == ("keep", 1800)


def test_teardown_after_tears_down_a_standing_instance_once_due(prepared):
    from cs_image_system.base.commands.verify_instance import teardown_due
    root, make = prepared
    _set_instance(root, "gce-test", teardown_after="1h")
    run = make()
    run.ctx.config["apply_instances"] = ["gcloud-east1"]
    assert run.run(["instance-image"], apply=True, only=["none"]).ok          # records the launch params
    inst = next(i for i in run.ctx.instances if i.get_name() == "gce-test")
    _record_failed_verification(run, "gce-test", "2026-09-08T10:00:00+00:00")
    from datetime import datetime, timezone
    assert not teardown_due(run.ctx, inst, now=datetime(2026, 9, 8, 10, 30, tzinfo=timezone.utc))
    assert teardown_due(run.ctx, inst, now=datetime(2026, 9, 8, 11, 30, tzinfo=timezone.utc))
    # once due, the sequence tears down without re-verifying
    import cs_image_system.base.commands.verify_instance as vi
    run2 = make()
    run2.ctx.config["apply_instances"] = ["gcloud-east1"]
    real_due = vi.teardown_due
    vi.teardown_due = lambda ctx, instance, now=None: real_due(ctx, instance, datetime(2026, 9, 9, tzinfo=timezone.utc))
    try:
        assert run2.run(["instance-image"], apply=True, only=["none"]).ok
    finally:
        vi.teardown_due = real_due
    lines = _lines_in((run2.generated / "instance-image" / "run-instance-image.sh").read_text(), GCE_ROOT)
    assert not any("verify instance" in ln for ln in lines)
    assert any("-var=ephemeral_present=false" in ln for ln in lines)


def test_failure_policy_values_are_validated(prepared):
    root, make = prepared
    _set_instance(root, "gce-test", on_failure="ignore", teardown_after="soon")
    run = make()
    summary = run.run(["instance-image"], apply=False, only=["none"])
    assert not summary.ok
    errs = "\n".join(summary.validation_errors)
    assert "on_failure 'ignore' is not one of" in errs and "teardown_after: duration 'soon'" in errs


def test_assert_last_verification(prepared):
    from cs_image_system.base.commands.verify_instance import VerificationFailed, assert_last_verification
    root, make = prepared
    run = make()
    with pytest.raises(VerificationFailed, match="no verification record"):
        assert_last_verification("gce-test")
    _record_failed_verification(run, "gce-test", "2026-09-08T10:00:00+00:00")
    with pytest.raises(VerificationFailed, match="booted image"):
        assert_last_verification("gce-test")
    run.ctx.meta_state.record_verification({"instance": "gce-test", "run": "r1", "ok": True, "time": "t", "checks": []})
    assert assert_last_verification("gce-test")["ok"]


def test_standing_report_states_the_policy(prepared, monkeypatch):
    from cs_image_system.base.state_query import StateReport, standing_ephemeral_drift
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    root, make = prepared
    _set_instance(root, "gce-test", teardown_after="1h")
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok
    _record_failed_verification(run, "gce-test", "2026-09-08T10:00:00+00:00")
    monkeypatch.setattr(GCPCloudBuilder, "query_instance_boot_image", lambda self, name: "dask-build-1")
    detail = standing_ephemeral_drift(run.ctx, StateReport(run="r"))[0].detail
    assert "verification failed at 2026-09-08T10:00:00+00:00" in detail
    assert "teardown_after has elapsed" in detail or "policy keep for 1h" in detail
