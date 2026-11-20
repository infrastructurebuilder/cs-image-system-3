# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Declared ephemerality: an instance with `ephemeral: true`
is launched through the gate, verified through its runtime, and torn down
by the same root in the same run; a failed verification stops the runner
with the instance standing (operator decision), and the state query says
so afterwards.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cs_image_system.system.testing import passing_session
from tests.harness import FixtureRun, command_lines, copy_config

#: the ephemeral subject: the fixture's AWS instance that mounts a storage
#: (test2 mounts mnt_data), on the default AWS runtime's instance root
EPHEMERAL = "test2"
AWS = "aws-east2-runtime"
AWS_ROOT = "open-tofu/instance-generation"
#: a runtime other than the ephemeral's: listing it alone lets the AWS root only plan
ELSEWHERE = "docker-fixture"


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
    _declare_ephemeral(root, EPHEMERAL)
    runs: list[FixtureRun] = []

    def make(**kw) -> FixtureRun:
        run = FixtureRun(tmp_path, monkeypatch, config_root=root, **kw)
        runs.append(run)
        return run
    try:
        yield root, make
    finally:
        for r in runs:
            r.restore_cwd()


def _lines_in(script: str, workspace: str) -> list[str]:
    return [ln for ln in command_lines(script) if ln.split('"')[1] == workspace]


def _session(monkeypatch, output: str, rc: int = 0) -> None:
    """The AWS runtime's SSM session, answered: the verification's own
    script gets ``(rc, output)``; the image's post-bake suite passes. The
    machine reads as running, so verification never tries to start it."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.contract import power_state
    monkeypatch.setattr(AwsCloudBuilder, "run_session_command",
                        passing_session(lambda self, name, script, timeout=300: (rc, output)))
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_power_state", lambda self, name: power_state.RUNNING)
    monkeypatch.setattr("time.sleep", lambda s: None)


#: what the verification's SSM script prints on a launched test2: the
#: completion marker, then the count of mounts under /mnt (mnt_data)
SESSION_OK = "LAUNCH_APPLIED\n1\n"


def test_ephemeral_root_launches_verifies_and_tears_down_in_one_sequence(prepared):
    root, make = prepared
    run = make()
    run.ctx.config["apply_instances"] = [AWS]
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.error
    tf = "\n".join(p.read_text() for p in (run.generated / "instance-image" / "open-tofu").rglob("*.tf"))
    assert 'variable "ephemeral_present"' in tf
    assert "count = var.ephemeral_present ? 1 : 0" in tf
    lines = _lines_in((run.generated / "instance-image" / "run-instance-image.sh").read_text(), AWS_ROOT)
    joined = "\n".join(lines)
    launch_apply = next(i for i, ln in enumerate(lines) if "apply -input=false tfplan" in ln)
    verify = next(i for i, ln in enumerate(lines) if f"verify instance {EPHEMERAL}" in ln)
    teardown_plan = next(i for i, ln in enumerate(lines) if "-var=ephemeral_present=false" in ln)
    assert launch_apply < verify < teardown_plan
    assert f"--allow-destroy module.instance_{EPHEMERAL}" in joined
    assert joined.count("apply -input=false tfplan") == 2          # launch, then teardown
    assert joined.count("apply-check --lifecycle instances --root open-tofu") == 2
    # launch parameters know the instance is ephemeral
    assert run.ctx.meta_state.launch_params()[EPHEMERAL]["ephemeral"] is True


def test_ephemeral_sequence_is_absent_when_the_root_may_not_apply(prepared):
    root, make = prepared
    run = make()                                          # apply_instances false
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.error
    script = (run.generated / "instance-image" / "run-instance-image.sh").read_text()
    assert "verify instance" not in script and "ephemeral_present=false" not in script


def test_forget_ephemerals_drops_the_records_after_a_real_apply(prepared):
    from cs_image_system.base.launch_params import forget_ephemerals
    from cs_image_system.contract.lifecycles import Lifecycle
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=True, only=["none"]).ok
    ms = run.ctx.meta_state
    ms.bind_instance(EPHEMERAL, "some-build", run.ctx.run_id)
    assert EPHEMERAL in ms.launch_params()
    run.ctx.config["apply_instances"] = [ELSEWHERE]                  # the AWS root only planned
    forget_ephemerals(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert EPHEMERAL in ms.launch_params() and ms.instance_pin(EPHEMERAL) == "some-build"
    run.ctx.config["apply_instances"] = [AWS]
    forget_ephemerals(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert EPHEMERAL not in ms.launch_params() and ms.instance_pin(EPHEMERAL) is None
    assert [u["op"] for u in ms._pins()["upgrades"]][-1] == "ephemeral"
    assert "test" in ms.launch_params()                              # non-ephemerals untouched


def test_verification_runs_through_the_runtime_and_records_the_verdict(prepared, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.base.commands.verify_instance import VerificationFailed, verify_instance
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok
    _session(monkeypatch, SESSION_OK)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", lambda self, name: "ami-dask-build-1")
    record = verify_instance(run.ctx, EPHEMERAL, expected_build="ami-dask-build-1", timeout=1)
    assert record["ok"] and record["ephemeral"] is True
    names = {c["name"]: c["ok"] for c in record["checks"]}
    assert names == {"startup scripts": True, "booted image": True, "data disks mounted": True,
                     "declared tests": True}          # the dask image declares post-bake tests
    assert run.ctx.meta_state.verifications()[-1]["instance"] == EPHEMERAL
    # a wrong booted image fails, and the record says which check
    with pytest.raises(VerificationFailed, match="booted image"):
        verify_instance(run.ctx, EPHEMERAL, expected_build="ami-dask-build-2", timeout=1)
    assert run.ctx.meta_state.verifications()[-1]["ok"] is False
    # no completion within the timeout
    _session(monkeypatch, "TargetNotConnected", rc=1)
    with pytest.raises(VerificationFailed, match="no completion"):
        verify_instance(run.ctx, EPHEMERAL, expected_build="ami-dask-build-1", timeout=0)


def test_a_runtime_without_verification_refuses(prepared, monkeypatch):
    """A runtime that does not implement the hook refuses cleanly (AWS
    implements it, so the base behaviour is stubbed back)."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
    from cs_image_system.base.commands.verify_instance import verify_instance
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok
    monkeypatch.setattr(AwsCloudBuilder, "verify_instance", RuntimeBuilderBase.verify_instance)
    with pytest.raises(NotImplementedError, match="cannot verify"):
        verify_instance(run.ctx, "test")


def test_state_query_reports_a_standing_ephemeral(prepared, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.engine.state_query import DRIFT_CHANGED, StateReport, standing_ephemeral_drift
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok   # records test2 (ephemeral)
    _session(monkeypatch, SESSION_OK)                                   # running, so only the boot image decides
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", lambda self, name: "ami-dask-build-1")
    drift = standing_ephemeral_drift(run.ctx, StateReport(run="r"))
    assert [(d.kind, d.name, d.drift, d.hard) for d in drift] == [("instance", EPHEMERAL, DRIFT_CHANGED, False)]
    assert "STANDING" in drift[0].detail
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", lambda self, name: None)
    assert standing_ephemeral_drift(run.ctx, StateReport(run="r")) == []


def test_verification_without_a_pin_accepts_a_recorded_build_of_the_series(prepared, monkeypatch):
    """Found live: an instance whose image was baked in the same run has no
    pin and a launch record saying `unbound`; the booted image must then be
    a recorded build of its image's series, never compared with 'unbound'."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.base.commands.verify_instance import VerificationFailed, verify_instance
    root, make = prepared
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok
    ms = run.ctx.meta_state
    assert ms.launch_params()[EPHEMERAL]["build"] == "unbound" and ms.instance_pin(EPHEMERAL) is None
    ms.add_build({"build_id": "ami-dask-9", "series": "imgfile-basic-dask", "runtime": AWS,
                  "name": "dask-aws-9", "parent": "vendor", "run": "r9"})
    _session(monkeypatch, SESSION_OK)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", lambda self, name: "ami-dask-9")
    record = verify_instance(run.ctx, EPHEMERAL, timeout=1)
    assert record["ok"] and record["build"] == "ami-dask-9"
    assert "a recorded build of imgfile-basic-dask" in next(c["detail"] for c in record["checks"] if c["name"] == "booted image")
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", lambda self, name: "ami-someone-elses")
    with pytest.raises(VerificationFailed, match="lineage does not record"):
        verify_instance(run.ctx, EPHEMERAL, timeout=1)


# ----------------------------------------------------------- failure policy

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


def _record_failed_verification(run: FixtureRun, name: str, when: str) -> None:
    run.ctx.meta_state.record_verification({"instance": name, "run": "r0", "ok": False, "time": when,
                                            "checks": [{"name": "booted image", "ok": False, "detail": "x"}]})


def test_teardown_policy_records_the_verdict_tears_down_and_fails_afterwards(prepared):
    root, make = prepared
    _set_instance(root, EPHEMERAL, on_failure="teardown")
    run = make()
    run.ctx.config["apply_instances"] = [AWS]
    assert run.run(["instance-image"], apply=True, only=["none"]).ok
    lines = _lines_in((run.generated / "instance-image" / "run-instance-image.sh").read_text(), AWS_ROOT)
    verify = next(i for i, ln in enumerate(lines) if f"verify instance {EPHEMERAL} --record-only" in ln)
    teardown_apply = [i for i, ln in enumerate(lines) if "apply -input=false tfplan" in ln][-1]
    assert verify < teardown_apply
    # the failed verdict fails the run from the after-apply hook
    # (after the records are forgotten), never from the script's last step
    assert not any("verify assert" in ln for ln in lines)


def test_teardown_policy_forgets_the_record_before_failing_the_run(prepared):
    """Seen live: a `verify assert` as the runner's last step failed the
    script before the after-apply hook ran, so a torn-down ephemeral kept its
    launch record. Now the hook forgets first, then raises the verdict."""
    from cs_image_system.base.commands.verify_instance import VerificationFailed
    from cs_image_system.base.launch_params import forget_ephemerals
    from cs_image_system.contract.lifecycles import Lifecycle
    root, make = prepared
    _set_instance(root, EPHEMERAL, on_failure="teardown")
    run = make()
    run.ctx.config["apply_instances"] = [AWS]
    ms = run.ctx.meta_state
    ms.record_launch_params(EPHEMERAL, {"image": "imgfile-basic-dask", "build": "b1", "mounts": [], "ephemeral": True,
                                          "hostname": EPHEMERAL, "launched_run": "r0"})
    _record_failed_verification(run, EPHEMERAL, "2026-09-09T14:37:44+00:00")
    with pytest.raises(VerificationFailed, match=f"{EPHEMERAL} failed verification: booted image: x"):
        forget_ephemerals(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert EPHEMERAL not in ms.launch_params()                       # forgotten before the raise
    assert not any(v.get("ok") for v in ms.verifications())            # the verdict stays recorded
    # under `keep` (the default) the hook never sees a failed verdict: the script stopped first
    _set_instance(root, EPHEMERAL, on_failure="keep")
    run = make()
    run.ctx.config["apply_instances"] = [AWS]
    run.ctx.meta_state.record_launch_params(EPHEMERAL, {"image": "imgfile-basic-dask", "build": "b1", "mounts": [],
                                                          "ephemeral": True, "hostname": EPHEMERAL, "launched_run": "r0"})
    forget_ephemerals(run.ctx, Lifecycle.INSTANCE_IMAGE)              # a passed run: no raise


def test_runtime_default_policy_and_instance_precedence(prepared):
    from cs_image_system.base.commands.verify_instance import failure_policy
    root, make = prepared
    _set_runtime(root, AWS, on_failure="teardown", teardown_after="2h")
    run = make()
    inst = next(i for i in run.ctx.instances if i.get_name() == EPHEMERAL)
    assert failure_policy(run.ctx, inst) == ("teardown", 7200)
    _set_instance(root, EPHEMERAL, on_failure="keep", teardown_after="30m")
    run = make()
    inst = next(i for i in run.ctx.instances if i.get_name() == EPHEMERAL)
    assert failure_policy(run.ctx, inst) == ("keep", 1800)


def test_teardown_after_tears_down_a_standing_instance_once_due(prepared):
    from cs_image_system.base.commands.verify_instance import teardown_due
    root, make = prepared
    _set_instance(root, EPHEMERAL, teardown_after="1h")
    run = make()
    run.ctx.config["apply_instances"] = [AWS]
    assert run.run(["instance-image"], apply=True, only=["none"]).ok          # records the launch params
    inst = next(i for i in run.ctx.instances if i.get_name() == EPHEMERAL)
    _record_failed_verification(run, EPHEMERAL, "2026-09-08T10:00:00+00:00")
    from datetime import datetime, timezone
    assert not teardown_due(run.ctx, inst, now=datetime(2026, 9, 8, 10, 30, tzinfo=timezone.utc))
    assert teardown_due(run.ctx, inst, now=datetime(2026, 9, 8, 11, 30, tzinfo=timezone.utc))
    # once due, the sequence tears down without re-verifying (the instance
    # root asks ``ctx.services.launch``, which reads the policy module)
    import cs_image_system.base.ephemeral_policy as ep
    run2 = make()
    run2.ctx.config["apply_instances"] = [AWS]
    real_due = ep.teardown_due
    ep.teardown_due = lambda ctx, instance, now=None: real_due(ctx, instance, datetime(2026, 9, 9, tzinfo=timezone.utc))
    try:
        assert run2.run(["instance-image"], apply=True, only=["none"]).ok
    finally:
        ep.teardown_due = real_due
    lines = _lines_in((run2.generated / "instance-image" / "run-instance-image.sh").read_text(), AWS_ROOT)
    assert not any("verify instance" in ln for ln in lines)
    assert any("-var=ephemeral_present=false" in ln for ln in lines)


def test_failure_policy_values_are_validated(prepared):
    root, make = prepared
    _set_instance(root, EPHEMERAL, on_failure="ignore", teardown_after="soon")
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
        assert_last_verification(run.ctx, EPHEMERAL)
    _record_failed_verification(run, EPHEMERAL, "2026-09-08T10:00:00+00:00")
    with pytest.raises(VerificationFailed, match="booted image"):
        assert_last_verification(run.ctx, EPHEMERAL)
    run.ctx.meta_state.record_verification({"instance": EPHEMERAL, "run": "r1", "ok": True, "time": "t", "checks": []})
    assert assert_last_verification(run.ctx, EPHEMERAL)["ok"]


def test_standing_report_states_the_policy(prepared, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.engine.state_query import StateReport, standing_ephemeral_drift
    root, make = prepared
    _set_instance(root, EPHEMERAL, teardown_after="1h")
    run = make()
    assert run.run(["instance-image"], apply=False, only=["none"]).ok
    _record_failed_verification(run, EPHEMERAL, "2026-09-08T10:00:00+00:00")
    _session(monkeypatch, SESSION_OK)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", lambda self, name: "ami-dask-build-1")
    detail = standing_ephemeral_drift(run.ctx, StateReport(run="r"))[0].detail
    assert "verification failed at 2026-09-08T10:00:00+00:00" in detail
    assert "teardown_after has elapsed" in detail or "policy keep for 1h" in detail
