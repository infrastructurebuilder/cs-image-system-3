# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XII, group B: the records' noise (items 8, 13, 19, 24, 27, 30).

Each is a thing the walk of the daily driver found in what a run writes or
shows: a verdict line cut from the log's tail, a never-launched machine filed
as a cloud that could not answer, a cancelled run journalled as a success, a
runner step's list landing in the committed emission, the vendor's image
moving under an unbaked base reported as the tree's drift, and a provider
lock file that changed with whoever made the record.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from v2_support import V2Run


# ------------------------------------------- item 8: the verdict is always shown

def test_a_verdict_line_cut_by_the_tail_is_shown_ahead_of_it(caplog):
    from cs_image_system.base.models.executable import _log_captured
    outputs = "\n".join(f"output_{i} = \"v\"" for i in range(45))
    stdout = "Apply complete! Resources: 1 added, 0 changed, 0 destroyed.\n\nOutputs:\n\n" + outputs + "\n"
    with caplog.at_level(logging.INFO):
        _log_captured(["tofu", "apply"], subprocess.CompletedProcess(["tofu", "apply"], 0, stdout, ""))
    assert "verdict lines before the tail" in caplog.text
    assert "1: Apply complete! Resources: 1 added, 0 changed, 0 destroyed." in caplog.text
    assert "(last 40 of 49 lines; all at DEBUG)" in caplog.text
    caplog.clear()
    short = "Plan: 0 to add, 0 to change, 1 to destroy.\nx\n"
    with caplog.at_level(logging.INFO):
        _log_captured(["tofu", "plan"], subprocess.CompletedProcess(["tofu", "plan"], 0, short, ""))
    assert "verdict lines before the tail" not in caplog.text, "a verdict inside the tail is shown once, with it"


# ----------------------------- item 13: declared and not launched is a note

def test_a_pinned_instance_never_launched_is_a_note_and_the_cloud_is_not_asked(tmp_path, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.base import state_query as sq
    run = V2Run(tmp_path, monkeypatch)
    try:
        ctx = run.ctx
        rt = sorted(n for n, b in ctx.runtime_builders.items() if isinstance(b, AwsCloudBuilder))[0]
        ctx.meta_state.add_build({"build_id": "ami-fresh", "series": "imgfile-coops-model", "runtime": rt,
                                  "name": "n", "parent": "external", "input_fingerprint": "f", "run": "r",
                                  "capabilities": {}, "mods": [], "chain": []})
        ctx.meta_state.bind_instance("test", "ami-fresh", "run-x")      # a bake binds the pin; nothing launched

        def asked(self, name):
            raise AssertionError(f"the cloud was asked about {name}")
        monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", asked)
        report = sq.query_state(ctx)
        assert not [u for u in report.unavailable if "instances/test" in u]
        note = [n for n in report.notes if "instances/test" in n]
        assert note and "not launched yet" in note[0] and "ami-fresh" in note[0], report.notes
    finally:
        run.restore_cwd()


# --------------------------------- item 19: an interrupted run says so

def test_an_interrupted_run_is_journalled_as_interrupted_and_not_ok(tmp_path, monkeypatch):
    from cs_image_system.base.commands import run_lifecycles as rl
    run = V2Run(tmp_path, monkeypatch)
    try:
        def ctrl_c(ctx, summary):
            raise KeyboardInterrupt
        monkeypatch.setattr(rl, "apply_lifecycles", ctrl_c)
        with pytest.raises(KeyboardInterrupt):
            run.run(["identity"], apply=True)
        entries = yaml.safe_load((run.meta_state / "runs.yaml").read_text())["runs"]
        last = entries[-1]
        assert last["ok"] is False and "interrupted (KeyboardInterrupt)" in last["error"], last
        summary = (run.generated / "run-summary.json").read_text()
        assert '"ok": false' in summary and "interrupted" in summary
    finally:
        run.restore_cwd()


# ------------------------- item 24: the sanction list is never the emission's

def test_the_sanction_list_is_ignored_by_the_emission_and_is_not_drift(tmp_path, monkeypatch):
    from cs_image_system.base.commands.emission import normalise_emission
    from cs_image_system.base.constants import DEFAULT_GITIGNORE_ENTRIES
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    name = OktaTfGroupBuilder.SANCTIONED_REMOVALS
    assert name in DEFAULT_GITIGNORE_ENTRIES
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["identity"], apply=False).ok
        ignore = (run.generated / ".gitignore").read_text()
        assert name in ignore.splitlines()
        stray = run.generated / "identity" / "x" / name
        stray.parent.mkdir(parents=True)
        stray.write_text("module.group_g.oktapam_user_group_attachment.members[\"someone\"]\n")
        normalise_emission(run.generated)
        assert not stray.exists(), "a copy under generated/ is residue to the comparison"
    finally:
        run.restore_cwd()


# ------------------- item 27: the vendor's image moving is not the tree's drift

def test_the_vendors_image_moving_under_an_unbaked_base_is_named_and_not_behind():
    from cs_image_system.base.commands.emission import vendor_image_moves
    moved = ["diff base-image/packer-ebs/image-generation/block-000/source-el10.pkr.hcl",
             "--- committed/x", "+++ now/x", "@@ -2,5 +2,5 @@", "   filters = {",
             '-    image-id = "ami-0426928e75e7093d4",', '+    image-id = "ami-0281f4b4279b17b5b",', "   }"]
    assert vendor_image_moves(moved) == [
        "base-image/packer-ebs/image-generation/block-000/source-el10.pkr.hcl: "
        'image-id = "ami-0426928e75e7093d4" -> image-id = "ami-0281f4b4279b17b5b"']
    gce = ["diff base-image/pckr-gce-ans/image-generation/block-000/source.pkr.hcl",
           '-  source_image = "almalinux-10-v20261005"', '+  source_image = "almalinux-10-v20261013"']
    assert len(vendor_image_moves(gce)) == 1
    assert vendor_image_moves(moved + ["diff instance-image/x.tf", "-a = 1", "+a = 2"]) == []
    assert vendor_image_moves(["diff base-image/x/image-generation/y.pkr.hcl", '-  ami_name = "a"', '+  ami_name = "b"']) == []
    assert vendor_image_moves(["Only in now/base-image: z"]) == []


def test_config_drift_passes_on_a_vendor_image_move_alone(tmp_path, monkeypatch):
    from cs_image_system.base.commands.emission import config_drift
    from test_v2_release_whole import _copy_of_committed, _generated_tree
    v2 = _generated_tree(tmp_path, monkeypatch)
    root = v2.config_root
    def vendor_moved(copy: Path) -> None:
        _copy_of_committed(v2)(copy)
        f = next(p for p in (copy / "generated" / "base-image").rglob("*.pkr.hcl") if "image-id" in p.read_text())
        f.write_text(re.sub(r'image-id = "ami-[0-9a-f]+"', 'image-id = "ami-0new000000000000"', f.read_text(), count=1))
    code, lines = config_drift(root, dry_run=vendor_moved)
    assert code == 0 and "vendor's newest image moved" in lines[0] and "`just record` takes it" in lines[0], lines
    assert any("-> image-id" in ln for ln in lines[1:]), lines


# --------------------- item 30: the lock file is the union of what both saw

LOCK_A = '''# This file is maintained automatically by "tofu init".
# Manual edits may be lost in future updates.

provider "registry.opentofu.org/hashicorp/aws" {
  version     = "6.67.0"
  constraints = ">= 5.81.0"
  hashes = [
    "h1:aaa=",
    "zh:111=",
  ]
}
'''
LOCK_B = '''# This file is maintained automatically by "tofu init".
# Manual edits may be lost in future updates.

provider "registry.opentofu.org/hashicorp/aws" {
  version     = "6.67.0"
  constraints = ">= 5.81.0"
  hashes = [
    "h1:bbb=",
    "zh:111=",
  ]
}
'''


def test_merging_lock_files_keeps_every_hash_either_init_recorded():
    from cs_image_system.base.materialize import merge_lock_files
    merged = merge_lock_files(LOCK_A, LOCK_B)
    assert '"h1:aaa=",' in merged and '"h1:bbb=",' in merged and merged.count('"zh:111=",') == 1
    assert merge_lock_files(merged, LOCK_B) == merged == merge_lock_files(merged, LOCK_A), "a fixed point"
    newer = LOCK_B.replace('"6.67.0"', '"6.68.0"')
    bumped = merge_lock_files(LOCK_A, newer)
    assert '"6.68.0"' in bumped and '"h1:aaa=",' not in bumped, "a new version keeps only its own hashes"


def test_sync_back_merges_the_lock_file_and_levels_the_mirror(tmp_path):
    from cs_image_system.base.materialize import materialize, mirror_path, sync_back
    src = tmp_path / "generated" / "ws"
    src.mkdir(parents=True)
    (src / "main.tf").write_text('x = "1"\n')
    (src / ".terraform.lock.hcl").write_text(LOCK_A)
    dst = mirror_path(tmp_path, src)
    materialize(src, dst)
    (dst / ".terraform.lock.hcl").write_text(LOCK_B)
    assert sync_back(src, dst) == [".terraform.lock.hcl"]
    committed = (src / ".terraform.lock.hcl").read_text()
    assert '"h1:aaa=",' in committed and '"h1:bbb=",' in committed
    assert (dst / ".terraform.lock.hcl").read_text() == committed, "the mirror is level with the record"
    assert sync_back(src, dst) == []
