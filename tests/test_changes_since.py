# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``init-config TREE --changes-since PREVIOUS_STARTERS``.

A tree takes a release by refreshing the files the release owns. This read-only
listing is what is read first, by a person or (``--porcelain``) by ``just take``:
which of those files the release changed, split into the ones the tree still holds
as the previous release wrote them (safe to refresh) and the ones the tree also
edited (read both), and which are new. A terraform module is one entry, judged by
its stamp. The previous release is stood in for by a copy of the packaged starters
with a few files made older; the tree is a whole starter written by ``init-config``.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from cs_image_system.base.modules import STAMP_FILE, Stamp, content_hash, installed_modules
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
    assert not report.clear and report.unchanged >= 5       # the other release-owned files, and every module the stamps call current


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


# ------------------------------------------------------------ the porcelain form, and the modules by their stamps

def _porcelain(tree: Path, previous: Path) -> tuple[int, list[tuple[str, str]]]:
    result = runner.invoke(app, ["init-config", str(tree), "--from", "standard-aws", "--changes-since", str(previous),
                                 "--porcelain"])
    entries = [tuple(line.split(" ", 1)) for line in result.output.splitlines() if line]
    return result.exit_code, [(e[0], e[1]) for e in entries]


def _a_module(tree: Path) -> tuple[str, Path]:
    """(the entry ``tfmodules/<name>/``, the copy) of the first installed module, as the tree holds it."""
    name = next(iter(installed_modules()))
    return f"{starters.MODULES_DIR}/{name}/", tree / starters.MODULES_DIR / name


def _as_another_release_wrote_it(copy: Path) -> None:
    """The copy's content made older and its stamp to match: what a previous release wrote, nobody's edit since."""
    tf = sorted(copy.glob("*.tf"))[0]
    tf.write_text(tf.read_text() + "# the previous release's line\n")
    old = Stamp.read(copy / STAMP_FILE)
    assert old is not None
    Stamp(plugin=old.plugin, release="0.0.1", hash=content_hash(copy)).write(copy / STAMP_FILE)


def test_porcelain_a_refresh_is_one_line_and_exits_0(tmp_path: Path):
    previous, tree = _world(tmp_path)
    (tree / "Justfile").write_text(_older(previous, "Justfile"))
    code, entries = _porcelain(tree, previous)
    assert code == 0 and entries == [(starters.CHANGE_REFRESH, "Justfile")]


def test_porcelain_an_edited_file_exits_1(tmp_path: Path):
    previous, tree = _world(tmp_path)
    (tree / "Justfile").write_text(_older(previous, "Justfile"))
    _older(previous, ".gitignore")
    (tree / ".gitignore").write_text("# a local edit\n" + (tree / ".gitignore").read_text())
    code, entries = _porcelain(tree, previous)
    assert code == 1
    assert entries == [(starters.CHANGE_REFRESH, "Justfile"), (starters.CHANGE_EDITED, ".gitignore")]


def test_porcelain_an_added_file_exits_0(tmp_path: Path):
    previous, tree = _world(tmp_path)
    (tree / "CI_SETUP.md").unlink()
    (previous / "standard-aws" / "CI_SETUP.md").write_text("an older guide\n")
    code, entries = _porcelain(tree, previous)
    assert code == 0 and entries == [(starters.CHANGE_ADDED, "CI_SETUP.md")]


def test_porcelain_a_clear_tree_prints_nothing_and_exits_0(tmp_path: Path):
    previous, tree = _world(tmp_path)
    assert _porcelain(tree, previous) == (0, [])


def test_porcelain_that_cannot_compare_exits_2(tmp_path: Path):
    previous, tree = _world(tmp_path)
    shutil.rmtree(previous / "standard-aws")
    assert _porcelain(tree, previous)[0] == 2
    alone = runner.invoke(app, ["init-config", str(tree), "--porcelain"])           # the form of --changes-since alone
    assert alone.exit_code == 2


def test_a_module_another_release_wrote_and_nobody_edited_is_one_refresh_entry(tmp_path: Path):
    previous, tree = _world(tmp_path)
    entry, copy = _a_module(tree)
    _as_another_release_wrote_it(copy)
    report = starters.changes_since(tree, previous, "standard-aws")
    assert report.refresh == [entry] and report.edited == []                      # per module, not per file
    code, entries = _porcelain(tree, previous)
    assert code == 0 and entries == [(starters.CHANGE_REFRESH, entry)]
    forced = runner.invoke(app, ["init-config", str(tree), "--from", "standard-aws", "--force"])
    assert forced.exit_code == 0, forced.output                                   # and --force takes it, as judged
    assert content_hash(copy) == content_hash(installed_modules()[copy.name].path)


def test_a_module_edited_since_its_stamp_is_edited_and_exits_1(tmp_path: Path):
    previous, tree = _world(tmp_path)
    entry, copy = _a_module(tree)
    tf = sorted(copy.glob("*.tf"))[0]
    tf.write_text(tf.read_text() + "# a local edit\n")                            # the stamp still names the release's hash
    code, entries = _porcelain(tree, previous)
    assert code == 1 and entries == [(starters.CHANGE_EDITED, entry)]


def test_a_module_the_tree_lacks_is_added_and_one_named_in_module_sources_is_not_judged(tmp_path: Path):
    previous, tree = _world(tmp_path)
    entry, copy = _a_module(tree)
    shutil.rmtree(copy)
    assert _porcelain(tree, previous) == (0, [(starters.CHANGE_ADDED, entry)])
    cfg = tree / "cfg" / "_config.yml"
    cfg.write_text(cfg.read_text().replace("config:\n", f"config:\n  module_sources:\n    {copy.name}: ../elsewhere\n", 1))
    assert _porcelain(tree, previous) == (0, [])


def test_an_unstamped_module_is_judged_by_content(tmp_path: Path):
    previous, tree = _world(tmp_path)
    entry, copy = _a_module(tree)
    (copy / STAMP_FILE).unlink()
    assert _porcelain(tree, previous) == (0, [])                                  # identical to the release's: adopted, unchanged
    tf = sorted(copy.glob("*.tf"))[0]
    tf.write_text(tf.read_text() + "# unknown origin\n")
    assert _porcelain(tree, previous) == (1, [(starters.CHANGE_EDITED, entry)])
    # a previous release of the older layout carried the module in its tree: the same content is that release's own
    held = previous / "standard-aws" / starters.MODULES_DIR / copy.name
    shutil.copytree(copy, held)
    assert _porcelain(tree, previous) == (0, [(starters.CHANGE_REFRESH, entry)])
