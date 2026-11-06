# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The starters are one skeleton plus an overlay each, and their terraform
modules are the installed plugins' (stage 126 items 4 and 5).

``docs/examples/_skeleton/`` holds exactly the files every starter shares;
each starter's directory is its overlay and repeats none of them;
``starters.render`` lays the overlay over the skeleton, and
``starters.write_starter`` writes that tree with the plugins' modules
materialised into its ``module_source_base`` directory, each copy stamped.
``init-config`` writes the same tree into an empty directory, and into an
existing tree refreshes the modules by their stamps: an unmodified copy of
another release is replaced, an unstamped identical copy is adopted, an
edited copy is refused by name with or without ``--force``, and a module
the tree sources elsewhere (``config: module_sources``) is skipped.
``init-config --changes-since`` reads a previous release's starters in
either layout. The published template tree carries the modules too.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cs_image_system.base.modules import STAMP_FILE, Stamp, content_hash, installed_modules
from cs_image_system.system import starters
from cs_image_system.system.cli import app

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "docs" / "examples"
SKELETON = EXAMPLES / "_skeleton"
SHAPE = ("README.md", "Justfile", "CI_SETUP.md", ".gitignore", ".githooks/pre-commit", ".github/workflows/ci.yml",
         ".age-identity", ".age-recipient", "cfg/_config.yml", "groups", "storages", "images", "instances",
         "base_images/README.md", "overlays")


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and p.name != ".DS_Store"}


def _invoke(*args: str):
    return CliRunner().invoke(app, ["init-config", *args])


# ------------------------------------------------------------ the skeleton

def test_the_skeleton_holds_exactly_what_every_starter_shares_and_no_overlay_repeats_it():
    skeleton = _files(SKELETON)
    assert skeleton, "the skeleton is empty"
    overlays = {name: _files(EXAMPLES / name) for name in starters.STARTERS}
    for name, files in overlays.items():
        repeated = sorted(set(files) & set(skeleton))
        assert repeated == [], f"{name} repeats skeleton files: {repeated}"
    rendered = {name: starters.render(name) for name in starters.STARTERS}
    shared = {rel for rel in set.intersection(*(set(r) for r in rendered.values()))
              if len({r[rel] for r in rendered.values()}) == 1}
    assert shared == set(skeleton), {"shared but not in the skeleton": sorted(shared - set(skeleton)),
                                     "in the skeleton but not shared": sorted(set(skeleton) - shared)}
    for rel, data in skeleton.items():
        for name, r in rendered.items():
            assert r[rel] == data, f"{name}/{rel} is not the skeleton's"


def test_the_skeleton_is_not_a_starter_and_nothing_else_beside_the_starters_starts_with_an_underscore():
    assert "_skeleton" not in starters.STARTERS and not (SKELETON / "cfg").exists()
    assert starters.starters() == starters.STARTERS
    assert sorted(starters.STARTERS) == ["complete", "standard-aws", "standard-aws-posix", "standard-docker", "standard-gce"]
    for entry in EXAMPLES.iterdir():
        assert not entry.name.startswith("_") or entry.name == "_skeleton", entry.name
    assert not any((EXAMPLES / name / "tfmodules").exists() for name in starters.STARTERS), "a starter carries a module copy"
    with pytest.raises(ValueError, match="no starter named '_skeleton'"):
        starters.render("_skeleton")


def test_every_rendered_starter_has_the_whole_repository_shape():
    for name in starters.STARTERS:
        rendered = starters.render(name)
        for rel in SHAPE:
            assert rel in rendered or any(r.startswith(rel + "/") for r in rendered), f"{name} lacks {rel}"
        assert not any(r.startswith("tfmodules/") for r in rendered), f"{name}: the modules are not part of the render"
        assert starters.render_sources(name)[".githooks/pre-commit"] == SKELETON / ".githooks" / "pre-commit"
        assert starters.render_sources(name)["README.md"] == EXAMPLES / name / "README.md"


def test_a_root_of_the_older_layout_renders_each_tree_as_it_is(tmp_path: Path):
    """A previous release's wheel holds whole trees, ``tfmodules/`` inside and
    no ``_skeleton``; ``render`` reads them as they are."""
    old = _old_layout_root(tmp_path / "old")
    rendered = starters.render("standard-aws", old)
    assert "Justfile" in rendered and "tfmodules/aws_instance/main.tf" in rendered
    assert rendered["Justfile"] == starters.render("standard-aws")["Justfile"]
    assert STAMP_FILE not in {Path(r).name for r in rendered}


def _old_layout_root(into: Path) -> Path:
    """A starters directory as an earlier release's wheel carries it: the
    DEFAULT marker and each starter as a whole tree with its own module
    copies (no stamps), no skeleton."""
    into.mkdir(parents=True)
    shutil.copy2(EXAMPLES / "DEFAULT", into / "DEFAULT")
    for name in starters.STARTERS:
        for rel, src in starters.render_sources(name).items():
            (into / name / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, into / name / rel)
        for rel, src in starters.installed_module_files("tfmodules").items():
            (into / name / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, into / name / rel)
    return into


# --------------------------------------------------------- write_starter

def test_write_starter_writes_the_modules_with_stamps_into_the_declared_base(tmp_path: Path):
    dest = tmp_path / "tree"
    written = starters.write_starter("standard-gce", dest, version="9.9.9")
    assert written == sorted(written) and ".csis-version" in written and "Justfile" in written
    assert (dest / ".csis-version").read_text() == "9.9.9\n"
    assert "module_source_base: tfmodules" in (dest / "cfg" / "_config.yml").read_text()
    modules = installed_modules()
    assert len(modules) >= 14
    for name, module in modules.items():
        copy = dest / "tfmodules" / name
        stamp = Stamp.read(copy / STAMP_FILE)
        assert stamp is not None and stamp.plugin == module.namespace and stamp.release == module.version, name
        assert stamp.hash == content_hash(copy) == content_hash(module.path), name
        assert f"tfmodules/{name}/{STAMP_FILE}" in written
    # the links that leave the starter name the version
    assert "/blob/v9.9.9/docs/CONFIGURATION.md" in (dest / "README.md").read_text()


def test_write_starter_follows_a_module_source_base_inside_the_tree_and_writes_none_for_one_outside(tmp_path: Path):
    assert starters.module_base_of("config:\n  module_source_base: tfmodules\n") == "tfmodules"
    assert starters.module_base_of("config:\n  module_source_base: ./tools/modules/\n") == "tools/modules"
    assert starters.module_base_of("config: {}\n") == "tfmodules"             # the starters' convention
    assert starters.module_base_of(None) == "tfmodules"
    for outside in ("../cs-image-system-3/tfmodules", "/opt/modules", "git::https://example.invalid/m.git", "."):
        assert starters.module_base_of(f"config:\n  module_source_base: {outside}\n") is None, outside


def test_init_config_into_an_empty_directory_is_write_starter(tmp_path: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    starters.write_starter("standard-aws-posix", a, version=starters.release_version())
    result = _invoke(str(b), "--from", "standard-aws-posix")
    assert result.exit_code == 0, result.output
    assert _files(a) == _files(b)
    assert (b / ".githooks" / "pre-commit").stat().st_mode == (a / ".githooks" / "pre-commit").stat().st_mode


# ------------------------------------------- init-config refreshes the modules

def _tree(tmp_path: Path, name: str = "standard-aws") -> Path:
    tree = tmp_path / "tree"
    assert _invoke(str(tree), "--from", name).exit_code == 0
    return tree


def test_init_config_refreshes_an_unmodified_copy_of_another_release(tmp_path: Path):
    tree = _tree(tmp_path)
    copy = tree / "tfmodules" / "aws_instance"
    main = copy / "main.tf"
    main.write_text(main.read_text() + "\n# the previous release's line\n")
    Stamp(plugin="aws-runtime", release="0.0.1", hash=content_hash(copy)).write(copy / STAMP_FILE)   # unmodified since written
    result = _invoke(str(tree))
    assert result.exit_code == 0, result.output
    assert "aws_instance: refreshed" in result.output and ": 1 written, " in result.output   # counted as written
    assert main.read_bytes() == (installed_modules()["aws_instance"].path / "main.tf").read_bytes()
    assert Stamp.read(copy / STAMP_FILE).release == installed_modules()["aws_instance"].version   # type: ignore[union-attr]


def test_init_config_adopts_an_unstamped_identical_copy(tmp_path: Path):
    tree = _tree(tmp_path)
    (tree / "tfmodules" / "okta_opa_module" / STAMP_FILE).unlink()
    result = _invoke(str(tree))
    assert result.exit_code == 0, result.output
    assert "okta_opa_module: adopted" in result.output
    assert (tree / "tfmodules" / "okta_opa_module" / STAMP_FILE).is_file()


def test_init_config_refuses_an_edited_copy_by_name_even_with_force(tmp_path: Path):
    tree = _tree(tmp_path)
    main = tree / "tfmodules" / "aws_storage_ebs" / "main.tf"
    edited = main.read_text() + "\n# our change\n"
    main.write_text(edited)
    for args in ((str(tree),), (str(tree), "--force")):
        result = _invoke(*args)
        assert result.exit_code == 1, (args, result.output)
        assert "REFUSED aws_storage_ebs" in result.output and "edited after it was written" in result.output, args
        assert "module_sources (aws_storage_ebs:" in result.output, "the report says how to keep it"
        assert main.read_text() == edited                                     # left alone
    assert (tree / "Justfile").is_file()                                      # the rest was refreshed as usual


def test_init_config_skips_a_module_named_in_module_sources(tmp_path: Path):
    tree = _tree(tmp_path)
    cfg = tree / "cfg" / "_config.yml"
    cfg.write_text(cfg.read_text().replace("  module_source_base: tfmodules",
                                           "  module_sources:\n    aws_instance: ../our-modules/aws_instance\n"
                                           "  module_source_base: tfmodules", 1))
    main = tree / "tfmodules" / "aws_instance" / "main.tf"
    main.write_text("# ours, kept\n")                                          # an edit that would be refused otherwise
    result = _invoke(str(tree))
    assert result.exit_code == 0, result.output
    assert "aws_instance: skipped -- config: module_sources names it" in result.output
    assert main.read_text() == "# ours, kept\n"


def test_init_config_writes_no_module_when_the_base_is_outside_the_tree(tmp_path: Path):
    tree = tmp_path / "tree"
    (tree / "cfg").mkdir(parents=True)
    (tree / "cfg" / "_config.yml").write_text("config:\n  module_source_base: ../cs-image-system-3/tfmodules\n")
    result = _invoke(str(tree))
    assert result.exit_code == 0, result.output
    assert "no terraform module written" in result.output and not (tree / "tfmodules").exists()


# ------------------------------------------------------- changes-since

def test_changes_since_an_older_layout_lists_nothing_when_nothing_changed_and_a_changed_module_file(tmp_path: Path):
    previous = _old_layout_root(tmp_path / "previous")
    tree = _tree(tmp_path)
    report = starters.changes_since(tree, previous, "standard-aws")
    assert report.clear, report.lines()
    assert report.unchanged > 20                                            # the release-owned files and every module file
    # the previous release's module differed, and the tree still holds that release's copy: refresh
    old_main = previous / "standard-aws" / "tfmodules" / "gce_instance" / "main.tf"
    old_main.write_text(old_main.read_text() + "\n# older\n")
    (tree / "tfmodules" / "gce_instance" / "main.tf").write_bytes(old_main.read_bytes())
    report = starters.changes_since(tree, previous, "standard-aws")
    assert report.refresh == ["tfmodules/gce_instance/main.tf"] and report.edited == [] and report.added == []
    # the tree's copy differs from both: edited
    (tree / "tfmodules" / "gce_instance" / "main.tf").write_text("# ours\n")
    assert starters.changes_since(tree, previous, "standard-aws").edited == ["tfmodules/gce_instance/main.tf"]


def test_changes_since_a_current_layout_previous_root_compares_no_module_it_lacks(tmp_path: Path):
    previous = tmp_path / "previous"
    shutil.copytree(starters.starters_root(), previous, ignore=shutil.ignore_patterns("generated", "_private", "__pycache__"))
    tree = _tree(tmp_path)
    report = starters.changes_since(tree, previous, "standard-aws")
    assert report.clear, report.lines()
    with_modules = report.unchanged
    (tree / "tfmodules" / "gce_instance" / "main.tf").write_text("# ours\n")
    report = starters.changes_since(tree, previous, "standard-aws")
    assert report.edited == ["tfmodules/gce_instance/main.tf"] and report.unchanged == with_modules
    shutil.rmtree(tree / "tfmodules" / "docker_volume")
    assert "tfmodules/docker_volume/main.tf" in starters.changes_since(tree, previous, "standard-aws").added


# ------------------------------------------------------ the published tree

def test_the_published_template_tree_carries_the_modules_with_their_stamps(tmp_path: Path):
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("starter_tree", str(REPO / "scripts" / "starter-tree"))
    spec = importlib.util.spec_from_loader("starter_tree", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    files = m.build("standard-docker", "0.1.2", tmp_path / "t")
    for name in installed_modules():
        assert f"tfmodules/{name}/{STAMP_FILE}" in files and f"tfmodules/{name}/main.tf" in files, name
    assert (tmp_path / "t" / "README.md").read_text().startswith(m.HEADER_MARK)
