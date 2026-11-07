# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The provider lock file is the union of what both inits recorded.

Merging two lock files keeps every hash either init recorded, once; a new
provider version keeps only its own hashes; the merge is a fixed point.
Syncing the mirror back merges its lock file into the record and levels the
mirror with it.

history: bundle XII item 30.
"""
from __future__ import annotations

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
