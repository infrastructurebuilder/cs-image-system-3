# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What the system says about the vendor's images.

The vendor's newest image moving under a base this tree has not baked is
named and is not the tree's drift: `config-drift` passes on it alone and
CI's guard (`runtime-unchanged`) passes a vendor move alone, fails a vendor
move beside a change of the runtime's, and never reads a diff cut short as
a move -- on the fixture's AWS runtime, whose vendor line is the base
source's `image-id` filter. `validate` prints
the modification tests' stand-in per OS builder and WARNS when a query
plainly names another family than the declared one.

history: bundle VI item 2, XII item 27, XVII item 1, XX item 4.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import yaml
from harness import VENDOR_AMI, copy_config, load_context, stub_environment
from test_release_whole import _copy_of_committed, _generated_tree

AWS = "aws-east2-runtime"
MOVED_AMI = "ami-0feedfacecafe0002"


def _aws_source(root: Path) -> Path:
    """The AWS base's packer source that names the vendor's AMI (basic-rh-10 on pckr-ebs-ans)."""
    return next(p for p in (root / "generated" / "base-image" / "pckr-ebs-ans").rglob("*source-basic-rh-10-*.pkr.hcl")
                if "image-id =" in p.read_text())


def _move_the_vendor_image(root: Path) -> None:
    f = _aws_source(root)
    f.write_text(f.read_text().replace(f'image-id = "{VENDOR_AMI}"', f'image-id = "{MOVED_AMI}"', 1))


# ------------------------------- a vendor move is named, and is not drift

def test_the_vendors_image_moving_under_an_unbaked_base_is_named_and_not_behind():
    from cs_image_system.engine.commands.emission import vendor_image_moves
    moved = ["diff base-image/packer-ebs/image-generation/block-000/source-el10.pkr.hcl",
             "--- committed/x", "+++ now/x", "@@ -2,5 +2,5 @@", "   filters = {",
             '-    image-id = "ami-0426928e75e7093d4",', '+    image-id = "ami-0281f4b4279b17b5b",', "   }"]
    assert vendor_image_moves(moved) == [
        "base-image/packer-ebs/image-generation/block-000/source-el10.pkr.hcl: "
        'image-id = "ami-0426928e75e7093d4" -> image-id = "ami-0281f4b4279b17b5b"']
    # the core reads a `source_image` line (a builder that names its vendor image so) the same way
    named = ["diff base-image/some-builder/image-generation/block-000/source.pkr.hcl",
             '-  source_image = "vendor-10-v20261005"', '+  source_image = "vendor-10-v20261013"']
    assert len(vendor_image_moves(named)) == 1
    assert vendor_image_moves(moved + ["diff instance-image/x.tf", "-a = 1", "+a = 2"]) == []
    assert vendor_image_moves(["diff base-image/x/image-generation/y.pkr.hcl", '-  ami_name = "a"', '+  ami_name = "b"']) == []
    assert vendor_image_moves(["Only in now/base-image: z"]) == []


def test_config_drift_passes_on_a_vendor_image_move_alone(tmp_path, monkeypatch):
    from cs_image_system.engine.commands.emission import config_drift
    fixture_run = _generated_tree(tmp_path, monkeypatch)
    root = fixture_run.config_root
    def vendor_moved(copy: Path) -> None:
        _copy_of_committed(fixture_run)(copy)
        f = next(p for p in (copy / "generated" / "base-image").rglob("*.pkr.hcl") if "image-id" in p.read_text())
        f.write_text(re.sub(r'image-id = "ami-[0-9a-f]+"', 'image-id = "ami-0new000000000000"', f.read_text(), count=1))
    code, lines = config_drift(root, dry_run=vendor_moved)
    assert code == 0 and "vendor" in lines[0], lines
    assert any("-> image-id" in ln for ln in lines[1:]), lines


# ------------------------------- the guard passes a vendor move alone

def test_the_guard_passes_the_vendors_image_moving_under_an_unbaked_base(tmp_path, monkeypatch):
    from cs_image_system.engine.commands.emission import runtime_unchanged
    fixture_run = _generated_tree(tmp_path, monkeypatch)
    os.chdir(fixture_run.config_root)
    _move_the_vendor_image(fixture_run.config_root)
    code, lines = runtime_unchanged(fixture_run.ctx, AWS, "HEAD")
    assert code == 0, lines
    assert "HEAD" in lines[0] and "vendor" in lines[0], lines
    assert any(f'image-id = "{VENDOR_AMI}" -> image-id = "{MOVED_AMI}"' in ln for ln in lines[1:]), lines
    fixture_run.restore_cwd()


def test_the_guard_still_fails_a_vendor_move_beside_a_change_of_the_runtimes(tmp_path, monkeypatch):
    from cs_image_system.engine.commands.emission import runtime_unchanged
    fixture_run = _generated_tree(tmp_path, monkeypatch)
    root = fixture_run.config_root
    os.chdir(root)
    _move_the_vendor_image(root)
    f = _aws_source(root)
    f.write_text(f.read_text() + "# a declaration changed\n")
    code, lines = runtime_unchanged(fixture_run.ctx, AWS, "HEAD")
    assert code == 1 and "CHANGED" in lines[0], lines
    fixture_run.restore_cwd()


# ----------------------------------- a diff cut short is never a move

def test_a_diff_cut_short_is_never_read_as_a_vendor_move():
    from cs_image_system.engine.commands.emission import vendor_image_moves
    aws = ["diff base-image/pckr-ebs-ans/image-generation/block-000/source.pkr.hcl",
           '-        image-id = "ami-0426928e75e7093d4",', '+        image-id = "ami-0281f4b4279b17b5b",']
    assert len(vendor_image_moves(aws)) == 1
    # diff_trees ends a long diff with this line; what it left out may be anything
    assert vendor_image_moves([*aws, "... (40 more lines)"]) == []
    # nor is a file whose difference could not be shown
    assert vendor_image_moves([*aws, "diff base-image/pckr-ebs-ans/image-generation/x.bin",
                               "(binary files differ)"]) == []


def test_a_change_past_the_cut_is_not_excused(tmp_path):
    from cs_image_system.engine.commands.emission import diff_trees, vendor_image_moves
    a, b = tmp_path / "committed", tmp_path / "now"
    for side, image, size in ((a, "0001", "t3.micro"), (b, "0002", "t3.small")):
        d = side / "base-image" / "pckr-ebs-ans" / "image-generation"
        d.mkdir(parents=True)
        (d / "a-source.pkr.hcl").write_text(f'data "amazon-ami" "y" {{\n  filters = {{\n    image-id = "ami-0vendor{image}",\n  }}\n}}\n')
        (d / "b-build.pkr.hcl").write_text(f'source "amazon-ebs" "y" {{\n  instance_type = "{size}"\n}}\n')
    whole = diff_trees(a, b)
    assert vendor_image_moves(whole) == [], whole
    # cut just after the first file's diff: what is shown is all vendor lines
    first = next(i for i, ln in enumerate(whole) if ln.startswith("diff ") and "b-build" in ln)
    cut = diff_trees(a, b, limit=first)
    assert cut[-1].startswith("... (") and all("b-build" not in ln for ln in cut), cut
    assert vendor_image_moves(cut) == [], cut


# ----------------------------------- validate: the stand-in, and the family a query names

def _edit_os_builders(root: Path, change) -> None:
    p = root / "cfg" / "os-builders.yml"
    doc = yaml.safe_load(p.read_text())
    change(doc["os_builders"])
    p.write_text(yaml.safe_dump(doc, sort_keys=False))


def test_validate_prints_the_stand_in_per_os_builder_and_warns_on_a_query_naming_another_family(tmp_path, monkeypatch, caplog):
    from cs_image_system.contract.image import ImageQuery
    from cs_image_system.engine.commands.validate import check_image_sources, family_named_by_query
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
    with caplog.at_level(logging.INFO, logger="cs_image_system.engine.commands.validate"):
        assert check_image_sources(ctx) == []
    messages = [r.getMessage() for r in caplog.records]
    stand_ins = [m for m in messages if m.startswith("mod-test stand-in:")]
    assert stand_ins and all(any(f"'{n}'" in m for n in ctx.os_builders) for m in stand_ins), stand_ins   # each names a declared builder
    assert any("'basic-rh-10'" in m and "almalinux:10" in m for m in stand_ins), stand_ins
    assert any("'my-deb-12'" in m and "debian:12" in m for m in stand_ins), stand_ins
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and "alma-linux" in r.getMessage()]
    assert len(warnings) == 1 and "'rhel'" in warnings[0], warnings


def test_a_family_that_says_what_the_image_is_draws_no_warning(tmp_path, monkeypatch, caplog):
    from cs_image_system.engine.commands.validate import check_image_sources
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))                                  # the fixture: alma-linux, the catalog's query
    with caplog.at_level(logging.INFO, logger="cs_image_system.engine.commands.validate"):
        assert check_image_sources(ctx) == []
    assert not [r for r in caplog.records if r.levelno == logging.WARNING and "names" in r.getMessage()]
