# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XXI item 3: ``init-config TREE --changes-since PREVIOUS_STARTERS``.

A tree takes a release by refreshing the files the release owns, by hand. This
read-only listing is what the person reads first: which of those files the release
changed, split into the ones the tree still holds as the previous release wrote
them (safe to refresh) and the ones the tree also edited (read both), and which are
new. The previous release is stood in for by a copy of the packaged starters with a
few files made older; the tree is a whole starter written by ``init-config``.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from cs_image_system.system import starters
from cs_image_system.system.cli import app

runner = CliRunner()


def _world(tmp_path: Path) -> tuple[Path, Path]:
    """(the previous release's starters root, a tree written from the current standard-aws)."""
    previous = tmp_path / "previous"
    shutil.copytree(starters.starters_root(), previous, ignore=shutil.ignore_patterns("generated", "_private", "__pycache__"))
    tree = tmp_path / "tree"
    starters.init_config(tree, "standard-aws")
    return previous, tree


def _older(previous: Path, rel: str, extra: str = "# the previous release's line\n") -> str:
    """The previous release's text of REL made older: written into the
    starter's own directory, which the render lays over the skeleton."""
    path = previous / "standard-aws" / rel
    old = starters.render("standard-aws", previous)[rel].decode() + extra
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(old)
    return old


def test_a_file_the_release_changed_and_the_tree_still_has_as_the_old_release_wrote_it_is_listed_to_refresh(tmp_path: Path):
    previous, tree = _world(tmp_path)
    (tree / "Justfile").write_text(_older(previous, "Justfile"))
    report = starters.changes_since(tree, previous, "standard-aws")
    assert report.refresh == ["Justfile"] and report.edited == [] and report.added == []
    assert not report.clear and report.unchanged >= 5       # the other release-owned files; a previous root of this layout holds no module to count


def test_a_changed_file_the_tree_also_edited_is_listed_apart(tmp_path: Path):
    previous, tree = _world(tmp_path)
    _older(previous, ".gitignore")
    (tree / ".gitignore").write_text("# a local edit\n" + (tree / ".gitignore").read_text())
    report = starters.changes_since(tree, previous, "standard-aws")
    assert report.edited == [".gitignore"] and report.refresh == []


def test_a_workflow_with_the_teams_values_counts_as_the_old_release_text(tmp_path: Path):
    previous, tree = _world(tmp_path)
    wf = ".github/workflows/ci.yml"
    old = _older(previous, wf)
    marks = [i for i, line in enumerate(old.splitlines()) if starters._placeholder(line)]
    assert marks, "the starter's workflow carries a REPLACE-ME line for the team's values"
    lines = old.splitlines(keepends=True)
    for i in marks:
        lines[i] = lines[i].replace("REPLACE-ME", "my-value").replace("REPLACE_ME", "my-value")
    (tree / wf).write_text("".join(lines))
    report = starters.changes_since(tree, previous, "standard-aws")
    assert report.refresh == [wf] and report.edited == []


def test_a_file_new_in_the_release_is_listed_as_added(tmp_path: Path):
    previous, tree = _world(tmp_path)
    (tree / "CI_SETUP.md").unlink()
    (previous / "standard-aws" / "CI_SETUP.md").write_text("an older guide\n")
    report = starters.changes_since(tree, previous, "standard-aws")
    assert report.added == ["CI_SETUP.md"] and report.refresh == []


def test_a_tree_the_release_did_not_change_is_clear_and_the_command_exits_0(tmp_path: Path):
    previous, tree = _world(tmp_path)
    (tree / "README.md").write_text("the team's own words\n")      # not release-owned: never looked at
    report = starters.changes_since(tree, previous, "standard-aws")
    assert report.clear and "nothing the release owns changed" in "\n".join(report.lines())
    result = runner.invoke(app, ["init-config", str(tree), "--from", "standard-aws", "--changes-since", str(previous)])
    assert result.exit_code == 0, result.output


def test_the_command_lists_and_exits_1_and_writes_nothing(tmp_path: Path):
    previous, tree = _world(tmp_path)
    (tree / "Justfile").write_text(_older(previous, "Justfile"))
    before = {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()}
    result = runner.invoke(app, ["init-config", str(tree), "--changes-since", str(previous)])
    assert result.exit_code == 1, result.output
    assert "your copy is the previous release's own" in result.output and "init-config:   Justfile" in result.output
    assert {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()} == before


def test_a_previous_release_without_the_starter_is_refused_by_name(tmp_path: Path):
    previous, tree = _world(tmp_path)
    shutil.rmtree(previous / "standard-aws")
    result = runner.invoke(app, ["init-config", str(tree), "--from", "standard-aws", "--changes-since", str(previous)])
    assert result.exit_code == 2 and "hold no standard-aws" in result.output


def test_a_directory_that_is_not_a_configuration_is_refused(tmp_path: Path):
    previous, _ = _world(tmp_path)
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    result = runner.invoke(app, ["init-config", str(empty), "--changes-since", str(previous)])
    assert result.exit_code == 2 and "not a configuration repository" in result.output
