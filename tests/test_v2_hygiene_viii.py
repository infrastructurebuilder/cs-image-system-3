# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene bundle VIII (stage 71).

Item 2: the machine type is a launch parameter, and the one that may change
in place. A launched instance whose declaration names another type is not
refused (N26 compares everything else); the record keeps the type the
machine RUNS on until the apply resized it, and then the record, the open
generation's snapshot and a ``resized`` history event carry the new one.
A record from before the key existed adopts it. Any other change riding
along with the type is still refused. The GCE builder honours a declared
``machine_type`` (it used to take the runtime's default regardless).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, copy_config

from cs_image_system.base import launch_params as lp
from cs_image_system.base.lifecycles import Lifecycle

A = {"instance_id": "i-aaaa0000aaaa0000a", "provider_hostname": "ip-10-0-0-1.us-east-2.compute.internal"}
AWS = "aws-east2-runtime"


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


def _declare(root: Path, instance: str, **fields) -> None:
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    for i in d["instances"]:
        if i["name"] == instance:
            i.update(fields)
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _launched_now(run: V2Run, name: str, build: str, *, drop: tuple[str, ...] = ()) -> dict:
    """Seed the launch record (and pin) from what the tree computes NOW, so
    only the later declaration change differs; ``drop`` removes keys, as a
    record written before they existed would lack them."""
    inst = next(i for i in run.ctx.instances if i.get_name() == name)
    params = {k: v for k, v in lp.compute_launch_params(run.ctx, inst).items() if k not in drop}
    ms = run.ctx.meta_state
    ms.record_launch_params(name, {**params, "build": build, "launched": True, "launched_run": "r0"})
    pins = ms.read("pins.yaml")
    pins.setdefault("instances", {})[name] = build
    ms.write("pins.yaml", pins)
    return params


def _aws_tf(run: V2Run) -> str:
    return "\n".join(p.read_text() for p in (run.generated / "instance-image" / "open-tofu").rglob("*.tf"))


# --------------------------------------------------------- the snapshot key

def test_the_machine_type_is_a_launch_parameter(prepared):
    root, make = prepared
    run = make()
    by_name = {i.get_name(): i for i in run.ctx.instances}
    assert lp.compute_launch_params(run.ctx, by_name["test"])["machine_type"] == "t3.medium"     # declared
    gce = lp.compute_launch_params(run.ctx, by_name["gce-test"])
    assert gce["machine_type"] == run.ctx.runtime_builders["gcloud-east1"].get_default_machine_type()   # the default


def test_a_bare_type_change_on_a_launched_instance_is_a_resize_not_a_refusal(prepared):
    root, make = prepared
    probe = make()
    before = _launched_now(probe, "test", "ami-000")
    assert before["machine_type"] == "t3.medium"
    probe.ctx.meta_state.open_generation("test", kind="durable", run_id="r0", how="observed",
                                         launch_params=before, identity=A)
    _declare(root, "test", machine_type="t3.large")
    run = make()
    run.ctx.config["apply_instances"] = [AWS]
    summary = run.run(["instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.validation_errors or summary.error          # N26 lets the type move
    assert lp.resize_of(run.ctx, next(i for i in run.ctx.instances if i.get_name() == "test")) == ("t3.medium", "t3.large")
    # the emission carries the new type; the record keeps the one the machine runs on until the apply
    assert re.search(r'instance_type\s*=\s*"t3.large"', _aws_tf(run))
    rec = run.ctx.meta_state.launch_params()["test"]
    assert rec["machine_type"] == "t3.medium" and rec["launched"] is True
    # after the apply: the record, the open generation's snapshot and the history move together
    lp.record_resizes(run.ctx, Lifecycle.INSTANCE_IMAGE)
    rec = run.ctx.meta_state.launch_params()["test"]
    assert rec["machine_type"] == "t3.large" and rec["launched"] is True and rec["launched_run"] == "r0"
    ms = run.ctx.meta_state
    cur = ms.current_generation("test")
    assert cur and cur["number"] == 1 and cur["instance_id"] == A["instance_id"]        # the same machine
    assert cur["launch_params"]["machine_type"] == "t3.large"
    event = ms.instance_states()["test"]["history"][-1]
    assert event["event"] == "resized" and (event["from"], event["to"]) == ("t3.medium", "t3.large")
    assert event["run"] == run.ctx.run_id and event["number"] == 1 and event["kind"] == "durable"
    # idempotent: nothing left to record
    lp.record_resizes(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert len(ms.instance_states()["test"]["history"]) == 1


def test_any_other_change_riding_along_with_the_type_is_refused(prepared):
    root, make = prepared
    probe = make()
    _launched_now(probe, "test", "ami-000")
    _declare(root, "test", machine_type="t3.large", image="imgfile-basic-dask")   # a real change beside the resize
    run = make()
    summary = run.run(["instance-image"], apply=False, only=["none"])
    assert not summary.ok
    err = next(e for e in summary.validation_errors if "launch parameters are immutable after launch" in e)
    assert "image" in err and "machine_type" not in err


def test_a_record_from_before_the_key_existed_adopts_it(prepared):
    root, make = prepared
    probe = make()
    _launched_now(probe, "test", "ami-000", drop=("machine_type",))
    assert "machine_type" not in probe.ctx.meta_state.launch_params()["test"]
    run = make()
    inst = next(i for i in run.ctx.instances if i.get_name() == "test")
    assert lp.resize_of(run.ctx, inst) is None                              # adopted, not resized
    summary = run.run(["instance-image"], apply=False, only=["none"])
    assert summary.ok, summary.validation_errors or summary.error
    rec = run.ctx.meta_state.launch_params()["test"]
    assert rec["machine_type"] == "t3.medium" and rec["launched"] is True
    run.ctx.config["apply_instances"] = [AWS]
    lp.record_resizes(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert "test" not in run.ctx.meta_state.instance_states()              # no event without a resize


def test_the_gce_builder_honours_a_declared_machine_type(prepared):
    root, make = prepared
    _declare(root, "gce-test", machine_type="e2-small")
    run = make()
    summary = run.run(["instance-image"], apply=False, only=["none"])
    assert summary.ok, summary.validation_errors or summary.error
    tf = "\n".join(p.read_text() for p in (run.generated / "instance-image" / "tofu-gce").rglob("*.tf"))
    assert '"e2-small"' in tf and '"e2-micro"' not in tf.split('module "instance_gce_test"', 1)[1].split("\n}", 1)[0]
    by_name = {i.get_name(): i for i in run.ctx.instances}
    assert lp.compute_launch_params(run.ctx, by_name["gce-test"])["machine_type"] == "e2-small"


# ------------------------------------------------- item 3: the runner says what a command said

def test_a_command_the_process_ran_has_its_output_logged(caplog):
    import logging
    from cs_image_system.base.models.executable import ExecutableModel
    script = 'printf "x\\n\\033[1mPlan:\\033[0m 0 to add, 1 to change, 0 to destroy.\\n"; echo "a warning" >&2'
    e = ExecutableModel(name="sh", binary="/bin/sh", args=["-c", script])
    with caplog.at_level(logging.INFO):
        res = e.execute()
    assert res.returncode == 0
    assert "Plan: 0 to add, 1 to change, 0 to destroy." in caplog.text        # the summary line reaches INFO
    assert "\x1b[" not in caplog.text                                            # colour codes stripped
    assert "a warning" in caplog.text                                            # stderr too
    caplog.clear()
    long = ExecutableModel(name="sh", binary="/bin/sh", args=["-c", "seq 1 50"])
    with caplog.at_level(logging.INFO):
        long.execute()
    assert "(last 40 of 50 lines; all at DEBUG)" in caplog.text
    assert "\n50" in caplog.text and "\n5\n" not in caplog.text.split("all at DEBUG")[1]


# --------------------------------------- item 4: the applying script is not drift

def test_config_drift_ignores_the_lines_only_an_applying_run_emits(tmp_path):
    from cs_image_system.base.commands.emission import diff_trees, normalise_emission
    resting = tmp_path / "resting"; applying = tmp_path / "applying"; other = tmp_path / "other"
    common = ['( cd "open-tofu/instance-generation" && rm -f tfplan )',
              '( cd "open-tofu/instance-generation" && /usr/local/bin/tofu plan -input=false -out=tfplan )',
              '( cd "open-tofu/instance-generation" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )']
    apply_only = ['( cd "open-tofu/instance-generation" && cs-image-system apply-check --lifecycle instances --root open-tofu --root-alias aws-east2-runtime --apply-runtime aws-east2-runtime )',
                  '( cd "open-tofu/instance-generation" && /usr/local/bin/tofu apply -input=false tfplan )']
    for root, lines in ((resting, common), (applying, common + apply_only),
                        (other, common[:1] + ['( cd "x" && /usr/local/bin/tofu plan -input=false -out=other )'] + common[2:])):
        (root / "instance-image").mkdir(parents=True)
        (root / "instance-image" / "run-instance-image.sh").write_text("#!/usr/bin/env bash\n" + "\n".join(lines) + "\n")
        (root / "instance-image" / "notes.sh").write_text("\n".join(apply_only) + "\n")   # not a runner script: untouched
        normalise_emission(root)
    assert diff_trees(resting, applying) == []                                  # the apply lines are not drift
    assert any("plan" in ln for ln in diff_trees(resting, other))               # a real difference still is
    assert "apply-check" in (applying / "instance-image" / "notes.sh").read_text()


# ------------------------------------ item 5: a draw for a machine that never was goes back

def test_an_aborted_run_gives_its_alias_draw_back(tmp_path: Path, monkeypatch, caplog):
    import logging
    import subprocess
    from cs_image_system.base import alias_pool as ap
    from cs_image_system.base.models.executable import ExecutableModel
    ap._DRAWN.clear()
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        run.ctx.config["apply_instances"] = True
        pool = ap.pool_path(run.config_root)
        pool.parent.mkdir(parents=True, exist_ok=True)
        pool.write_text("gar\nkoi\n")
        # the apply dies after generation (where the draw happened), as tofu init did on 2026-10-01
        def dying(self, *args, skips=False):
            cmd = [self.binary or self.name] + list(self.args or []) + list(args)
            if "tfplan" in " ".join(cmd) or "init" in cmd:
                raise subprocess.CalledProcessError(1, cmd, "", "Failed to install provider")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        monkeypatch.setattr(ExecutableModel, "execute", dying)
        with caplog.at_level(logging.INFO):
            summary = run.run(["instance-image"], apply=True, only=["none"])
        assert not summary.ok
        assert "took alias 'gar'" in caplog.text                                 # it WAS drawn at generation
        assert "alias 'gar' drawn this run goes back to the pool" in caplog.text
        assert ap.free_names(pool) == ["gar", "koi"]                             # and it is free again
        assert not [k for k in ap._DRAWN if k[0] == str(run.ctx.run_id)]
    finally:
        run.restore_cwd()


def test_a_draw_the_launch_gave_a_machine_stays_spent(tmp_path: Path, monkeypatch):
    from cs_image_system.base import alias_pool as ap
    ap._DRAWN.clear()
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        run.ctx.config["apply_instances"] = True
        pool = ap.pool_path(run.config_root)
        pool.parent.mkdir(parents=True, exist_ok=True)
        pool.write_text("gar\nkoi\n")
        summary = run.run(["instance-image"], apply=True, only=["none"])
        assert summary.ok, summary.validation_errors or summary.error
        rec = run.ctx.meta_state.launch_params()["test"]
        assert rec["launched"] and rec["alias"] == "gar"
        assert "gar" not in ap.free_names(pool)                                  # given, so spent
        assert ap.undraw(pool, name="gar", run_id="some-other-run") is False     # another run cannot give it back
    finally:
        run.restore_cwd()
