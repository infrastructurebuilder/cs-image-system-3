# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What the system says about the vendor's images.

The vendor's newest image moving under a base this tree has not baked is
named and is not the tree's drift: `config-drift` passes on it alone and
CI's guard (`runtime-unchanged`) passes a vendor move alone, fails a vendor
move beside a change of the runtime's, and never reads a diff cut short as
a move. A pinned GCE image that is not READY is refused. `validate` prints
the modification tests' stand-in per OS builder and WARNS when a query
plainly names another family than the declared one.

history: bundle VI item 2, XII item 27, XVII item 1, XX item 4.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import pytest
import yaml
from harness import copy_config, load_context, reset_singletons, stub_environment
from test_release_whole import _copy_of_committed, _generated_tree


def _gce_source(root: Path) -> Path:
    return next(p for p in (root / "generated" / "base-image").rglob("*.pkr.hcl")
                if "gce" in str(p.relative_to(root)) and "source_image =" in p.read_text())


def _move_the_vendor_image(root: Path) -> None:
    f = _gce_source(root)
    f.write_text(re.sub(r'source_image = "[^"]*"', 'source_image = "debian-11-v2"', f.read_text(), count=1))


# ------------------------------- a vendor move is named, and is not drift

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
    v2 = _generated_tree(tmp_path, monkeypatch)
    root = v2.config_root
    def vendor_moved(copy: Path) -> None:
        _copy_of_committed(v2)(copy)
        f = next(p for p in (copy / "generated" / "base-image").rglob("*.pkr.hcl") if "image-id" in p.read_text())
        f.write_text(re.sub(r'image-id = "ami-[0-9a-f]+"', 'image-id = "ami-0new000000000000"', f.read_text(), count=1))
    code, lines = config_drift(root, dry_run=vendor_moved)
    assert code == 0 and "vendor" in lines[0], lines
    assert any("-> image-id" in ln for ln in lines[1:]), lines


# ------------------------------- the guard passes a vendor move alone

def test_the_guard_passes_the_vendors_image_moving_under_an_unbaked_base(tmp_path, monkeypatch):
    from cs_image_system.base.commands.emission import runtime_unchanged
    v2 = _generated_tree(tmp_path, monkeypatch)
    os.chdir(v2.config_root)
    _move_the_vendor_image(v2.config_root)
    code, lines = runtime_unchanged(v2.ctx, "gcloud-east1", "HEAD")
    assert code == 0, lines
    assert "HEAD" in lines[0] and "vendor" in lines[0], lines
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
    code, lines = runtime_unchanged(v2.ctx, "gcloud-east1", "HEAD")
    assert code == 1 and "CHANGED" in lines[0], lines
    v2.restore_cwd()


# ----------------------------------- a diff cut short is never a move

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


# ----------------------------------- a vendor image that is not ready

def test_a_pinned_gce_image_that_is_not_ready_is_refused(tmp_path: Path, monkeypatch):
    from typing import Any, cast

    from cs_image_system.gcloud_runtime import gcp_runtime_builders as g
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    try:
        rtb = cast(Any, ctx.runtime_builders["gcloud-east1"])
        entry = next(e for e in ctx.os_builders["basic-rh-10"].get_configs_for_image_builders().values()
                     if e.get_image_builder() == "pckr-gce-ans")
        monkeypatch.setattr(g, "query_image", lambda **kw: {"name": "almalinux-10-x", "status": "PENDING",
                                                              "self_link": "https://x/projects/almalinux-cloud/global/images/almalinux-10-x"})
        with pytest.raises(ValueError, match="PENDING"):
            g.GCPCloudBuilder.query_provider_image_by_id(rtb, entry, "almalinux-10-x")
        monkeypatch.setattr(g, "query_image", lambda **kw: {"name": "almalinux-10-x", "status": "READY",
                                                              "self_link": "https://x/projects/almalinux-cloud/global/images/almalinux-10-x"})
        found = g.GCPCloudBuilder.query_provider_image_by_id(rtb, entry, "almalinux-10-x")
        assert found is not None and found[0] == "almalinux-10-x"
    finally:
        reset_singletons()


# ----------------------------------- validate: the stand-in, and the family a query names

def _edit_os_builders(root: Path, change) -> None:
    p = root / "cfg" / "os-builders.yml"
    doc = yaml.safe_load(p.read_text())
    change(doc["os_builders"])
    p.write_text(yaml.safe_dump(doc, sort_keys=False))


def test_validate_prints_the_stand_in_per_os_builder_and_warns_on_a_query_naming_another_family(tmp_path, monkeypatch, caplog):
    from cs_image_system.base.commands.validate import check_image_sources, family_named_by_query
    from cs_image_system.contract.image import ImageQuery
    assert family_named_by_query(ImageQuery(name="AlmaLinux OS 10*x86_64*")) == "alma-linux"
    assert family_named_by_query(ImageQuery(family="rhel-10")) == "rhel"
    assert family_named_by_query(ImageQuery(name="my-golden-*")) is None
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)

    def change(entries):
        # family rhel under an Alma query: the shape the warning is for
        rh = next(e for e in entries if e["name"] == "basic-rh-10")
        rh["family"] = "rhel"
        next(r for r in rh["runtimes"] if r["name"] == "aws-my-rhel8")["query"] = {
            "name": "AlmaLinux OS 10*x86_64", "publisher": ["764336703387"]}
    _edit_os_builders(root, change)
    ctx = load_context(root)
    try:
        with caplog.at_level(logging.INFO, logger="cs_image_system.base.commands.validate"):
            assert check_image_sources(ctx) == []
    finally:
        reset_singletons()
    messages = [r.getMessage() for r in caplog.records]
    stand_ins = [m for m in messages if m.startswith("mod-test stand-in:")]
    assert stand_ins and all(any(f"'{n}'" in m for n in ctx.os_builders) for m in stand_ins), stand_ins   # each names a declared builder
    assert any("'basic-rh-10'" in m and "almalinux:10" in m for m in stand_ins), stand_ins
    assert any("'my-deb-12'" in m and "debian:12" in m for m in stand_ins), stand_ins
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and "alma-linux" in r.getMessage()]
    assert len(warnings) == 1 and "'rhel'" in warnings[0], warnings


def test_a_family_that_says_what_the_image_is_draws_no_warning(tmp_path, monkeypatch, caplog):
    from cs_image_system.base.commands.validate import check_image_sources
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))                                  # the fixture: alma-linux, the catalog's query
    try:
        with caplog.at_level(logging.INFO, logger="cs_image_system.base.commands.validate"):
            assert check_image_sources(ctx) == []
    finally:
        reset_singletons()
    assert not [r for r in caplog.records if r.levelno == logging.WARNING and "names" in r.getMessage()]
