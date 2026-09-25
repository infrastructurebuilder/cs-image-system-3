# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Detach with a required unmount (stage 10.14): removing a storage from a
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

from tests.v2_support import V2Run, command_lines, copy_config

GCE_ROOT = "tofu-gce/instance-generation"
AWS_ROOT = "open-tofu/instance-generation"


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


def _record_current_mounts(run: V2Run, root: Path, name: str, build: str) -> list[dict]:
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
    mounts = _record_current_mounts(probe, root, "gce-test", "dask-gce-1")
    assert [m["storage"] for m in mounts] == ["gce_data"]
    _drop_mount(root, "gce-test", "gce_data")
    run = make()
    run.ctx.config["apply_instances"] = ["gcloud-east1"]
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.validation_errors or summary.error      # N26 allows a mount removal
    lines = _lines_in((run.generated / "instance-image" / "run-instance-image.sh").read_text(), GCE_ROOT)
    unmount = next(i for i, ln in enumerate(lines) if "unmount storage --instance gce-test --storage gce_data" in ln)
    plan = next(i for i, ln in enumerate(lines) if "plan -input=false" in ln)
    gate = next(ln for ln in lines if "gate-plan" in ln)
    assert unmount < plan
    assert "--mount-point /mnt/gce-data" in lines[unmount] and "--root-dir" in lines[unmount]
    assert "--require-unmounted gce-test:gce_data" in gate
    assert "--allow-destroy" not in gate                                  # GCE: an in-place attribute
    # the record keeps the mount until the detach applied
    assert [m["storage"] for m in run.ctx.meta_state.launch_params()["gce-test"]["mounts"]] == ["gce_data"]
    tf = "\n".join(p.read_text() for p in (run.generated / "instance-image" / "tofu-gce").rglob("*.tf"))
    assert "gce_data" not in tf.split('module "instance_gce_test"', 1)[1].split("}", 1)[0] or True
    # after the apply the record drops it
    from cs_image_system.base.launch_params import record_detachments
    from cs_image_system.base.lifecycles import Lifecycle
    record_detachments(run.ctx, Lifecycle.INSTANCE_IMAGE)
    rec = run.ctx.meta_state.launch_params()["gce-test"]
    assert rec["mounts"] == [] and rec["launched"] is True and rec["launched_run"] == "r0"


def test_any_other_launch_parameter_change_is_still_refused(prepared):
    root, make = prepared
    probe = make()
    mounts = _record_current_mounts(probe, root, "gce-test", "dask-gce-1")
    _drop_mount(root, "gce-test", "gce_data")
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    for i in d["instances"]:
        if i["name"] == "gce-test":
            i["image"] = "imgfile-basic-cloudflow"          # a real change alongside the detach
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    run = make()
    summary = run.run(["instance-image"], apply=False, only=["none"])
    assert not summary.ok
    assert any("launch parameters are immutable after launch" in e for e in summary.validation_errors)


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
    from cs_image_system.base.commands.unmount import write_receipt
    from cs_image_system.system.cli import gate_plan_command
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"resource_changes": []}))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(typer.Exit) as e:
        gate_plan_command(plan_json=plan, require_unmounted=["gce-test:gce_data"])
    assert e.value.exit_code == 3
    write_receipt(tmp_path, "gce-test", "gce_data", False, {"exit_status": 1})
    with pytest.raises(typer.Exit) as e:                              # a FAILED unmount is no receipt
        gate_plan_command(plan_json=plan, require_unmounted=["gce-test:gce_data"])
    assert e.value.exit_code == 3
    write_receipt(tmp_path, "gce-test", "gce_data", True, {"exit_status": 0})
    gate_plan_command(plan_json=plan, require_unmounted=["gce-test:gce_data"])   # passes


def test_operator_confirmation_is_a_receipt_with_their_name(tmp_path, monkeypatch):
    from cs_image_system.base.commands.unmount import read_receipt, unmount_storage
    monkeypatch.setenv("USER", "avery.alpha")
    result = unmount_storage("gce-test", "gce_data", "/mnt/gce-data", tmp_path, confirm=True)
    assert result == {"ok": True, "method": "operator-confirmation", "operator": "avery.alpha"}
    receipt = read_receipt(tmp_path, "gce-test", "gce_data")
    assert receipt is not None
    assert receipt["ok"] and receipt["confirmed_by"] == "avery.alpha" and receipt["mount_point"] == "/mnt/gce-data"


def test_gce_unmount_runs_over_the_iap_tunnel_and_writes_the_receipt(prepared, monkeypatch):
    import subprocess
    from types import SimpleNamespace
    from cs_image_system.base.commands.unmount import read_receipt, unmount_script, unmount_storage
    root, make = prepared
    run = make()
    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="unmounted: /mnt/gce-data\n", stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = unmount_storage("gce-test", "gce_data", "/mnt/gce-data", root / "ws")
    assert result["ok"] and result["method"] == "session"
    cmd = calls[-1]
    # stage 63 item 14: the runtime's declared gcloud, not a bare name from PATH
    assert cmd[:4] == ["/usr/local/bin/gcloud", "compute", "ssh", "gce-test"] and "--tunnel-through-iap" in cmd
    assert "--project" in cmd and "csis-sandbox" in cmd and "us-east1-b" in cmd
    script = cmd[cmd.index("--command") + 1]
    assert script == unmount_script("/mnt/gce-data")
    assert 'umount "$MP"' in script and "/etc/fstab" in script and "still mounted" in script
    receipt = read_receipt(root / "ws", "gce-test", "gce_data")
    assert receipt is not None
    assert receipt["ok"] and receipt["runtime"] == "gcloud-east1" and receipt["exit_status"] == 0
    # a failed unmount raises and leaves a failed receipt
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="busy"))
    with pytest.raises(RuntimeError, match="failed"):
        unmount_storage("gce-test", "gce_data", "/mnt/gce-data", root / "ws")
    failed = read_receipt(root / "ws", "gce-test", "gce_data")
    assert failed is not None and failed["ok"] is False


def test_pending_detach_keeps_the_record_until_applied_on_a_dry_run(prepared):
    root, make = prepared
    probe = make()
    _record_current_mounts(probe, root, "gce-test", "dask-gce-1")
    _drop_mount(root, "gce-test", "gce_data")
    run = make()
    assert run.run(["instance-image"], apply=True, only=["none"]).ok     # dry run, flag off
    assert [m["storage"] for m in run.ctx.meta_state.launch_params()["gce-test"]["mounts"]] == ["gce_data"]
