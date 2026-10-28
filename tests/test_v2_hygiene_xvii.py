# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XVII (stage 100).

Item 1: CI's guard (`runtime-unchanged` on GUARD_RUNTIME) failed on any
change to the guarded runtime's emission, the vendor publishing a newer
image under a base with no build yet included -- a change nobody made,
which `config-drift` has excused since hygiene XII item 27. The guard now
passes a vendor move alone and names it; a diff cut short is never read as
one, in either command.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from test_v2_release_whole import _generated_tree


def _gce_source(root: Path) -> Path:
    return next(p for p in (root / "generated" / "base-image").rglob("*.pkr.hcl")
                if "gce" in str(p.relative_to(root)) and "source_image =" in p.read_text())


def _move_the_vendor_image(root: Path) -> None:
    f = _gce_source(root)
    f.write_text(re.sub(r'source_image = "[^"]*"', 'source_image = "debian-11-v2"', f.read_text(), count=1))


# ------------------------------- item 1: the guard passes a vendor move alone

def test_the_guard_passes_the_vendors_image_moving_under_an_unbaked_base(tmp_path, monkeypatch):
    from cs_image_system.base.commands.emission import runtime_unchanged
    v2 = _generated_tree(tmp_path, monkeypatch)
    os.chdir(v2.config_root)
    _move_the_vendor_image(v2.config_root)
    code, lines = runtime_unchanged("gcloud-east1", "HEAD")
    assert code == 0, lines
    assert "unchanged since HEAD" in lines[0] and "vendor's newest image moved" in lines[0], lines
    assert "nothing of yours changed" in lines[0], lines
    assert any('source_image = "debian-11-v1" -> source_image = "debian-11-v2"' in ln for ln in lines[1:]), lines
    v2.restore_cwd()


def test_the_guard_still_fails_a_vendor_move_beside_a_change_of_the_runtimes(tmp_path, monkeypatch):
    from cs_image_system.base.commands.emission import runtime_unchanged
    v2 = _generated_tree(tmp_path, monkeypatch)
    root = v2.config_root
    os.chdir(root)
    _move_the_vendor_image(root)
    f = _gce_source(root)
    f.write_text(f.read_text() + "# a declaration changed\n")
    code, lines = runtime_unchanged("gcloud-east1", "HEAD")
    assert code == 1 and "CHANGED since HEAD" in lines[0], lines
    v2.restore_cwd()


# ----------------------------------- item 1: a diff cut short is never a move

def test_a_diff_cut_short_is_never_read_as_a_vendor_move():
    from cs_image_system.base.commands.emission import vendor_image_moves
    gce = ["diff base-image/pckr-gce-ans/image-generation/block-000/source.pkr.hcl",
           '-  source_image = "almalinux-10-v20261023"', '+  source_image = "almalinux-10-v20261027"']
    assert len(vendor_image_moves(gce)) == 1
    # diff_trees ends a long diff with this line; what it left out may be anything
    assert vendor_image_moves([*gce, "... (40 more lines)"]) == []
    # nor is a file whose difference could not be shown
    assert vendor_image_moves([*gce, "diff base-image/pckr-gce-ans/image-generation/x.bin",
                               "(binary files differ)"]) == []


def test_a_change_past_the_cut_is_not_excused(tmp_path):
    from cs_image_system.base.commands.emission import diff_trees, vendor_image_moves
    a, b = tmp_path / "committed", tmp_path / "now"
    for side, image, size in ((a, "v1", "e2-micro"), (b, "v2", "e2-small")):
        d = side / "base-image" / "pckr-gce-ans" / "image-generation"
        d.mkdir(parents=True)
        (d / "a-source.pkr.hcl").write_text(f'source "x" "y" {{\n  source_image = "debian-11-{image}"\n}}\n')
        (d / "b-build.pkr.hcl").write_text(f'build {{\n  machine_type = "{size}"\n}}\n')
    whole = diff_trees(a, b)
    assert vendor_image_moves(whole) == [], whole
    # cut just after the first file's diff: what is shown is all vendor lines
    first = next(i for i, ln in enumerate(whole) if ln.startswith("diff ") and "b-build" in ln)
    cut = diff_trees(a, b, limit=first)
    assert cut[-1].startswith("... (") and all("b-build" not in ln for ln in cut), cut
    assert vendor_image_moves(cut) == [], cut
