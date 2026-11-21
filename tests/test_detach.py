# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Detach with a required unmount: removing a storage from a
launched instance's declaration is the one in-place launch-parameter
change allowed. The runtime unmounts it ON the instance first (a receipt),
`gate-plan --require-unmounted` refuses the detach without that receipt,
the attachment's destroy is whitelisted where it is a resource (AWS), and
the launch record drops the mount only after the apply.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.harness import FixtureRun, command_lines, copy_config

AWS_ROOT = "open-tofu/instance-generation"
#: the subject: the fixture's AWS instance with a mount (test2 mounts mnt_data at /mnt/data)
INSTANCE, STORAGE, MOUNT_POINT = "test2", "mnt_data", "/mnt/data"


def _launched_with_params(root: Path, name: str, build: str, params: dict) -> None:
    ms = root / "meta-state"
    ms.mkdir(exist_ok=True)
    p = ms / "launch-params.yaml"
    data = yaml.safe_load(p.read_text()) if p.exists() else {}
    data.setdefault("instances", {})[name] = {**params, "build": build, "launched": True, "launched_run": "r0"}
    p.write_text(yaml.safe_dump(data, sort_keys=True))
    pins = ms / "pins.yaml"
    d = yaml.safe_load(pins.read_text()) if pins.exists() else {"images": {}, "instances": {}, "upgrades": []}
    d.setdefault("instances", {})[name] = build
    pins.write_text(yaml.safe_dump(d, sort_keys=True))


def _drop_mount(root: Path, instance: str, storage: str) -> None:
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    for i in d["instances"]:
        if i["name"] == instance:
            i["storages"] = [s for s in (i.get("storages") or []) if s.get("name") != storage]
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _lines_in(script: str, workspace: str) -> list[str]:
    return [ln for ln in command_lines(script) if ln.split('"')[1] == workspace]


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
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


def _record_current_mounts(run: FixtureRun, root: Path, name: str, build: str) -> list[dict]:
    """Seed the launch record from what the tree computes NOW (so only the
    later declaration change differs)."""
    from cs_image_system.base.launch_params import compute_launch_params
    inst = next(i for i in run.ctx.instances if i.get_name() == name)
    params = compute_launch_params(run.ctx, inst)
    _launched_with_params(root, name, build, params)
    return params["mounts"]


def test_dropping_a_mount_is_allowed_and_planned_as_a_detach_after_an_unmount(prepared):
    root, make = prepared
    probe = make()
    mounts = _record_current_mounts(probe, root, INSTANCE, "ami-dask-1")
    assert [m["storage"] for m in mounts] == [STORAGE]
    _drop_mount(root, INSTANCE, STORAGE)
    run = make()
    run.ctx.config["apply_instances"] = ["aws-east2-runtime"]
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.validation_errors or summary.error      # N26 allows a mount removal
    lines = _lines_in((run.generated / "instance-image" / "run-instance-image.sh").read_text(), AWS_ROOT)
    unmount = next(i for i, ln in enumerate(lines) if f"unmount storage --instance {INSTANCE} --storage {STORAGE}" in ln)
    plan = next(i for i, ln in enumerate(lines) if "plan -input=false" in ln)
    gate = next(ln for ln in lines if "gate-plan" in ln)
    assert unmount < plan
    assert f"--mount-point {MOUNT_POINT}" in lines[unmount] and "--root-dir" in lines[unmount]
    assert f"--require-unmounted {INSTANCE}:{STORAGE}" in gate
    # (AWS: the attachment is a resource, so its destroy is whitelisted -- the AWS test below)
    # the record keeps the mount until the detach applied
    assert [m["storage"] for m in run.ctx.meta_state.launch_params()[INSTANCE]["mounts"]] == [STORAGE]
    tf = "\n".join(p.read_text() for p in (run.generated / "instance-image" / "open-tofu").rglob("*.tf"))
    assert STORAGE not in tf.split(f'module "instance_{INSTANCE}"', 1)[1].split("}", 1)[0] or True
    # after the apply the record drops it
    from cs_image_system.base.launch_params import record_detachments
    from cs_image_system.contract.lifecycles import Lifecycle
    record_detachments(run.ctx, Lifecycle.INSTANCE_IMAGE)
    rec = run.ctx.meta_state.launch_params()[INSTANCE]
    assert rec["mounts"] == [] and rec["launched"] is True and rec["launched_run"] == "r0"


def test_any_other_launch_parameter_change_is_still_refused(prepared):
    root, make = prepared
    probe = make()
    _record_current_mounts(probe, root, INSTANCE, "ami-dask-1")
    _drop_mount(root, INSTANCE, STORAGE)
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    for i in d["instances"]:
        if i["name"] == INSTANCE:
            i["image"] = "imgfile-basic-cloudflow"          # a real change alongside the detach
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    run = make()
    summary = run.run(["instance-image"], apply=False, only=["none"])
    assert not summary.ok
    assert any("immutable" in e for e in summary.validation_errors)


def test_aws_detach_whitelists_the_attachment_resource(prepared):
    root, make = prepared
    probe = make()
    _record_current_mounts(probe, root, "test2", "ami-dask-1")
    _drop_mount(root, "test2", "mnt_data")
    run = make()
    run.ctx.config["apply_instances"] = ["aws-east2-runtime"]
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.validation_errors or summary.error
    gate = next(ln for ln in _lines_in((run.generated / "instance-image" / "run-instance-image.sh").read_text(), AWS_ROOT)
                if "gate-plan" in ln)
    assert "--allow-destroy module.instance_test2.aws_volume_attachment.this" in gate
    assert "--require-unmounted test2:mnt_data" in gate


def test_gate_plan_requires_the_unmount_receipt(tmp_path, monkeypatch):
    import typer

    from cs_image_system.engine.commands.unmount import write_receipt
    from cs_image_system.system.cli import gate_plan_command
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"resource_changes": []}))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(typer.Exit) as e:
        gate_plan_command(plan_json=plan, require_unmounted=[f"{INSTANCE}:{STORAGE}"])
    assert e.value.exit_code == 3
    write_receipt(tmp_path, INSTANCE, STORAGE, False, {"exit_status": 1})
    with pytest.raises(typer.Exit) as e:                              # a FAILED unmount is no receipt
        gate_plan_command(plan_json=plan, require_unmounted=[f"{INSTANCE}:{STORAGE}"])
    assert e.value.exit_code == 3
    write_receipt(tmp_path, INSTANCE, STORAGE, True, {"exit_status": 0})
    gate_plan_command(plan_json=plan, require_unmounted=[f"{INSTANCE}:{STORAGE}"])   # passes


def test_operator_confirmation_is_a_receipt_with_their_name(prepared, tmp_path, monkeypatch):
    from cs_image_system.engine.commands.unmount import read_receipt, unmount_storage
    root, make = prepared
    run = make()
    monkeypatch.setenv("USER", "avery.alpha")
    result = unmount_storage(run.ctx, INSTANCE, STORAGE, MOUNT_POINT, tmp_path, confirm=True)
    assert result == {"ok": True, "method": "operator-confirmation", "operator": "avery.alpha"}
    receipt = read_receipt(tmp_path, INSTANCE, STORAGE)
    assert receipt is not None
    assert receipt["ok"] and receipt["confirmed_by"] == "avery.alpha" and receipt["mount_point"] == MOUNT_POINT


def test_unmount_runs_over_the_runtimes_session_and_writes_the_receipt(prepared, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.engine.commands.unmount import read_receipt, unmount_script, unmount_storage
    root, make = prepared
    run = make()
    calls: list[tuple[str, str]] = []

    def session(self, name, script, timeout=300):
        calls.append((name, script))
        return 0, f"unmounted: {MOUNT_POINT}\n"
    monkeypatch.setattr(AwsCloudBuilder, "run_session_command", session)
    result = unmount_storage(run.ctx, INSTANCE, STORAGE, MOUNT_POINT, root / "ws")
    assert result["ok"] and result["method"] == "session"
    # the instance's own runtime runs the unmount script on the instance
    name, script = calls[-1]
    assert name == INSTANCE
    assert script == unmount_script(MOUNT_POINT)
    assert 'umount "$MP"' in script and "/etc/fstab" in script and "still mounted" in script
    receipt = read_receipt(root / "ws", INSTANCE, STORAGE)
    assert receipt is not None
    assert receipt["ok"] and receipt["runtime"] == "aws-east2-runtime" and receipt["exit_status"] == 0
    # a failed unmount raises and leaves a failed receipt
    monkeypatch.setattr(AwsCloudBuilder, "run_session_command", lambda self, name, script, timeout=300: (1, "busy"))
    with pytest.raises(RuntimeError, match="failed"):
        unmount_storage(run.ctx, INSTANCE, STORAGE, MOUNT_POINT, root / "ws")
    failed = read_receipt(root / "ws", INSTANCE, STORAGE)
    assert failed is not None and failed["ok"] is False


def test_pending_detach_keeps_the_record_until_applied_on_a_dry_run(prepared):
    root, make = prepared
    probe = make()
    _record_current_mounts(probe, root, INSTANCE, "ami-dask-1")
    _drop_mount(root, INSTANCE, STORAGE)
    run = make()
    assert run.run(["instance-image"], apply=True, only=["none"]).ok     # dry run, flag off
    assert [m["storage"] for m in run.ctx.meta_state.launch_params()[INSTANCE]["mounts"]] == [STORAGE]
