# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0


"""Hygiene XII, group C: teardown correctness (items 9, 31, 32).

What the walk's teardown found: the last machine's decommission left the
instance root's security group with no run that would ever remove it; a
decommission on one cloud failed on another cloud's root after its destroy
and before its record; and a tree's first perform would fail planning an
instance root whose storage root has no state yet.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from v2_support import V2Run, command_lines, tree


def _aws_instance_builder(ctx):
    from cs_image_system.tf_ebs_instance_plugin.tf_instance_builder import TofuInstanceBuilder
    from cs_image_system.tf_gcp_plugin.tf_gce_instance_builder import TofuGceInstanceBuilder
    return next(b for b in ctx.instance_builders.values()
                if isinstance(b, TofuInstanceBuilder) and not isinstance(b, TofuGceInstanceBuilder))


# ------------------------------ item 31: the root lets its own group go

def test_the_security_group_carries_the_configuration_tag(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["instance-image"], apply=False).ok
        gb = _aws_instance_builder(run.ctx)
        tf = tree(run.generated / "instance-image" / gb.name / "instance-generation")
        root = next(v for k, v in tf.items() if k.endswith("-instance-generation.tf"))
        assert 'tags = { Name = "csis-instances", csis_config = "cs-image-action-test" }' in root
    finally:
        run.restore_cwd()


def test_a_root_with_nothing_declared_but_state_is_emitted_empty_and_lets_its_group_go(tmp_path, monkeypatch):
    """The walk: with `instances: []` after the decommission, no instance root
    was emitted, and the security group stood in AWS and in the root's state
    with nothing to plan it."""
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


# ---------------- item 32: a decommission on one cloud and the other's root

def test_apply_runtime_implies_the_scope_beside_only(tmp_path, monkeypatch):
    """The decommission recipe says `--only none --apply-runtime <rt>`; `--only`
    used to leave the scope unimplied, so the run planned every other
    runtime's instance root after applying this one."""
    from typing import Any, cast
    from cs_image_system.system import cli
    run = V2Run(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(cli, "_run", lambda lifecycles, **kw: None)
        rt = "aws-east2-runtime"
        cli.run_command(cast(Any, None), lifecycles=["instance-image"], only=["none"], apply_runtime=rt)
        assert run.ctx.only_runtime_scope == rt and run.ctx.implied_scope == rt
        from cs_image_system.base.commands.run_lifecycles import out_of_scope_builder_dirs
        assert "tofu-gce" in out_of_scope_builder_dirs(run.ctx), "the other cloud's root is out of the scoped run"
    finally:
        run.restore_cwd()


def test_an_ephemeral_that_neither_stands_nor_launches_is_absent_from_a_plan_only_root(tmp_path, monkeypatch):
    from test_v2_ephemeral import _declare_ephemeral
    from v2_support import copy_config
    root = copy_config(tmp_path)
    _declare_ephemeral(root, "gce-test")
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["instance-image"], apply=False).ok      # apply_instances false: the GCE root only plans
        tf = "\n".join(v for k, v in tree(run.generated / "instance-image" / "tofu-gce" / "instance-generation").items()
                       if "gce_test" in k or "gce-test" in k)
        assert "count = 0" in tf and "not standing, not launched by this run" in tf, tf[:600]
        assert "var.ephemeral_present ? 1 : 0" not in tf
        # launched by this run: the toggle is back
        run.ctx.config["apply_instances"] = ["gcloud-east1"]
        assert run.run(["instance-image"], apply=False, only=["none"]).ok
        tf2 = "\n".join(v for k, v in tree(run.generated / "instance-image" / "tofu-gce" / "instance-generation").items()
                        if "gce_test" in k or "gce-test" in k)
        assert "count = var.ephemeral_present ? 1 : 0" in tf2
    finally:
        run.restore_cwd()


def test_the_after_apply_hooks_run_after_a_failed_apply_so_what_applied_is_recorded(tmp_path, monkeypatch):
    from cs_image_system.base.commands import run_lifecycles as rl
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        seen: list[str] = []
        monkeypatch.setattr(rl, "_execute_in_process", lambda ctx, lc: False)
        monkeypatch.setattr(rl, "_AFTER_APPLY", [lambda ctx, lc: seen.append(lc.value)])
        summary = run.run(["identity"], apply=True)
        assert not summary.ok and summary.apply.get("identity") == "failed"
        assert seen == ["identity"], "the hooks ran once, after the failed apply"
    finally:
        run.restore_cwd()


# ------------------- item 9: the storage root with no state is said first

def test_the_state_query_notes_an_instance_whose_storage_root_has_no_state_yet(tmp_path, monkeypatch):
    from cs_image_system.base import state_query as sq
    run = V2Run(tmp_path, monkeypatch)
    try:
        report = sq.query_state(run.ctx)
        notes = [n for n in report.notes if "whose root has no state yet" in n]
        assert notes, report.notes
        assert any("instances/test:" in n and "'mnt_data'" in n for n in notes) or any("mnt_data" in n for n in notes), notes
    finally:
        run.restore_cwd()
