# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What an instance root is emitted with, and when it is emitted at all.

The security group carries the configuration's tag; a root with nothing
declared but state recorded is emitted empty and the gate may let its group
go (a root that never existed is not emitted); an ephemeral instance that
neither stands nor launches is absent from a plan-only root; the instance
root's `instances.auto.tfvars` is written by the instance-image lifecycle
alone, never under generated/release/ or generated/retention/.

history: bundle V item 5, XII items 31 and 32.
"""
from __future__ import annotations

from pathlib import Path

from harness import V2Run, command_lines, tree


def _aws_instance_builder(ctx):
    from cs_image_system.tf_ebs_instance_plugin.tf_instance_builder import TofuInstanceBuilder
    from cs_image_system.tf_gcp_plugin.tf_gce_instance_builder import TofuGceInstanceBuilder
    return next(b for b in ctx.instance_builders.values()
                if isinstance(b, TofuInstanceBuilder) and not isinstance(b, TofuGceInstanceBuilder))


def test_the_security_group_carries_the_configuration_tag(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["instance-image"], apply=False).ok
        gb = _aws_instance_builder(run.ctx)
        tf = tree(run.generated / "instance-image" / gb.name / "instance-generation")
        root = next(v for k, v in tf.items() if k.endswith("-instance-generation.tf"))
        assert 'csis_config = "cs-image-action-test"' in root
    finally:
        run.restore_cwd()


def test_a_root_with_nothing_declared_but_state_is_emitted_empty_and_lets_its_group_go(tmp_path, monkeypatch):
    """With `instances: []` after a decommission, no instance root was once
    emitted, and the security group stood in AWS and in the root's state with
    nothing to plan it."""
    probe = V2Run(tmp_path / "probe", monkeypatch)
    try:
        gb = _aws_instance_builder(probe.ctx)
        ws = gb.name
        mine = [i.get_name() for i in gb._instances]
    finally:
        probe.restore_cwd()
    run = V2Run(tmp_path / "run", monkeypatch, undeclare=[f"instance:{n}" for n in mine])
    try:
        ms = run.ctx.meta_state
        assert not _aws_instance_builder(run.ctx)._instances
        # no state recorded: a root that never existed is not emitted
        assert run.run(["instance-image"], apply=False).ok
        assert not (run.generated / "instance-image" / ws).exists()
        # the root's state is recorded: it is emitted, empty, and the gate may let the group go
        ms.record_state_locations({ws: {"backend": "local", "settings": {}}}, "r0")
        assert run.run(["instance-image"], apply=False).ok
        tf = tree(run.generated / "instance-image" / ws / "instance-generation")
        root = next(v for k, v in tf.items() if k.endswith("-instance-generation.tf"))
        assert 'resource "aws_security_group"' not in root
        assert not [k for k in tf if "instance-" in k and k.endswith(".tf") and "generation.tf" not in k]
        cmds = command_lines((run.generated / "instance-image" / "run-instance-image.sh").read_text())
        gate = next(c for c in cmds if "gate-plan" in c and f"{ws}/instance-generation" in c)
        assert "--allow-destroy aws_security_group.csis_instances" in gate, gate
    finally:
        run.restore_cwd()


def test_an_ephemeral_that_neither_stands_nor_launches_is_absent_from_a_plan_only_root(tmp_path, monkeypatch):
    from test_ephemeral import _declare_ephemeral
    from harness import copy_config
    root = copy_config(tmp_path)
    _declare_ephemeral(root, "gce-test")
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["instance-image"], apply=False).ok      # apply_instances false: the GCE root only plans
        tf = "\n".join(v for k, v in tree(run.generated / "instance-image" / "tofu-gce" / "instance-generation").items()
                       if "gce_test" in k or "gce-test" in k)
        assert "count = 0" in tf, tf[:600]
        assert "var.ephemeral_present ? 1 : 0" not in tf
        # launched by this run: the toggle is back
        run.ctx.config["apply_instances"] = ["gcloud-east1"]
        assert run.run(["instance-image"], apply=False, only=["none"]).ok
        tf2 = "\n".join(v for k, v in tree(run.generated / "instance-image" / "tofu-gce" / "instance-generation").items()
                        if "gce_test" in k or "gce-test" in k)
        assert "count = var.ephemeral_present ? 1 : 0" in tf2
    finally:
        run.restore_cwd()


def test_release_and_retention_never_write_an_instance_roots_tfvars(tmp_path: Path, monkeypatch):
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.contract.lifecycles import Lifecycle
    from cs_image_system.base.release import RELEASE_LIFECYCLE
    from cs_image_system.base.retention import RETENTION_LIFECYCLE
    from tests.test_lineage_pins import _fake_manifest
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["instance-image"], apply=False).ok
        ctx = run.ctx
        _fake_manifest(run, "instance-image", "block-000", {"imgfile-basic-dask": "ami-0dask0007"})
        ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
        ctx.image_builders["pckr-ebs-ans"].post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
        ib = ctx.instance_builders["open-tofu"]
        for lc in (RELEASE_LIFECYCLE, RETENTION_LIFECYCLE):
            ctx.current_lifecycle = lc
            ib.pre_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
            assert list((run.generated / lc.name).rglob("*.tfvars")) == [], f"{lc.name} wrote an instance root's tfvars"
        ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
        ib.pre_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
        tfvars = run.generated / "instance-image" / "open-tofu" / "instance-generation" / "instances.auto.tfvars"
        assert 'test2_ami_id = "ami-0dask0007"' in tfvars.read_text(), "the instance-image lifecycle still gets it"
    finally:
        ctx.current_lifecycle = None
        run.restore_cwd()
