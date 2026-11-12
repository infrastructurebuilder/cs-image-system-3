# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A committing run, and a committing restamp, is made by the release the
tree pins, or says so.

* a tree pins its release in ``.csis-version``; a run with ``--commit``
  over such a tree is refused, before anything is generated or committed,
  when the version running is not the pin and when any distribution of
  the system was installed from somewhere other than an index -- a source
  checkout whose version string equals the pin is still not the release;
* a tree without the file is not checked (the frozen fixture has none),
  and neither is a run that does not commit;
* ``--allow-unpinned``, or ``CSIS_ALLOW_UNPINNED`` in the environment,
  lets the run go on, and it says in one line what it was allowed past;
* ``lineage restamp --commit`` under ``--no-dry-run`` is held the same
  way, under its own name, before it computes or writes anything; its dry
  form is not, and neither is ``dispose image --commit``;
* what is installed is read from the distributions' own records: a
  ``direct_url.json`` in a dist-info means "not from an index".

history: hygiene XXV item 6.
"""
from __future__ import annotations

import json
import os
import subprocess
from importlib import metadata
from pathlib import Path

import pytest
from harness import copy_config, load_context, stub_environment, tree
from typer.testing import CliRunner

from cs_image_system.base import pinned_release
from cs_image_system.base.pinned_release import (
    ALLOW_ENVVAR,
    ALLOW_FLAG,
    ALLOWED,
    ARCHIVE,
    DIRECTORY,
    PIN_FILE,
    REFUSED,
    REPOSITORY,
    RESTAMP,
    RUN,
    Installed,
    SourceInstall,
    hold_to_pin,
    installed_release,
    read_pin,
    same_release,
    source_install,
)
from cs_image_system.system import starters

PINNED = "0.1.7.dev2"
OTHER = "0.1.6"
CHECKOUT = "/work/checkouts/the-system"

FROM_INDEX = Installed(PINNED)
CHECKOUT_AT_THE_PIN = Installed(PINNED, (SourceInstall("cs-image-system", f"file://{CHECKOUT}"),))

runner = CliRunner()


def _pin(root: Path, version: str = PINNED) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / PIN_FILE).write_text(version + "\n")
    return root


# ------------------------------------------------ the verdict, over given facts

def test_a_tree_without_a_pin_is_not_checked(tmp_path):
    verdict = hold_to_pin(tmp_path, commit=True, installed=CHECKOUT_AT_THE_PIN)
    assert verdict.pinned is None and not verdict.unpinned and not verdict.refused and verdict.lines() == []


def test_a_pin_file_that_names_nothing_is_no_pin(tmp_path):
    (tmp_path / PIN_FILE).write_text("\n")
    assert read_pin(tmp_path) is None
    assert not hold_to_pin(tmp_path, commit=True, installed=CHECKOUT_AT_THE_PIN).unpinned


def test_the_pinned_release_from_an_index_passes_and_says_nothing(tmp_path):
    verdict = hold_to_pin(_pin(tmp_path), commit=True, installed=FROM_INDEX)
    assert verdict.pinned == PINNED and not verdict.unpinned and not verdict.refused and verdict.lines() == []


def test_another_version_is_refused_and_the_refusal_names_both_and_both_remedies(tmp_path):
    verdict = hold_to_pin(_pin(tmp_path), commit=True, installed=Installed(OTHER))
    assert verdict.refused and verdict.version_differs and verdict.sources == ()
    said = "\n".join(verdict.lines())
    assert REFUSED in verdict.lines()[0] and ALLOWED not in said
    assert PINNED in said and OTHER in said and PIN_FILE in said
    assert "just record" in said and "just take" in said            # the pinned release, or the tree moves
    assert ALLOW_FLAG in said and ALLOW_ENVVAR in said               # or the operator's word


def test_a_checkout_whose_version_equals_the_pin_is_refused_and_named(tmp_path):
    verdict = hold_to_pin(_pin(tmp_path), commit=True, installed=CHECKOUT_AT_THE_PIN)
    assert verdict.refused and not verdict.version_differs
    said = "\n".join(verdict.lines())
    assert REFUSED in said and CHECKOUT in said and PINNED in said


def test_one_part_from_a_path_under_an_umbrella_from_an_index_is_refused(tmp_path):
    part = SourceInstall("cs-image-system-base", f"file://{CHECKOUT}/packages/base")
    verdict = hold_to_pin(_pin(tmp_path), commit=True, installed=Installed(PINNED, (part,)))
    assert verdict.refused and "cs-image-system-base" in "\n".join(verdict.lines())


def test_no_installed_version_at_all_is_refused(tmp_path):
    assert hold_to_pin(_pin(tmp_path), commit=True, installed=Installed(None)).refused


@pytest.mark.parametrize("installed", [Installed(OTHER), CHECKOUT_AT_THE_PIN])
def test_the_operators_word_lets_it_go_on_and_one_line_says_so(tmp_path, installed):
    verdict = hold_to_pin(_pin(tmp_path), commit=True, allow=True, installed=installed)
    assert verdict.unpinned and not verdict.refused
    lines = verdict.lines()
    assert len(lines) == 1 and ALLOWED in lines[0] and REFUSED not in lines[0] and PINNED in lines[0]


def test_the_operators_word_over_the_pinned_release_says_nothing(tmp_path):
    assert hold_to_pin(_pin(tmp_path), commit=True, allow=True, installed=FROM_INDEX).lines() == []


def test_a_run_that_does_not_commit_is_not_checked(tmp_path):
    verdict = hold_to_pin(_pin(tmp_path, OTHER), commit=False, installed=CHECKOUT_AT_THE_PIN)
    assert verdict.pinned is None and not verdict.refused and verdict.lines() == []


@pytest.mark.parametrize("held", [RUN, RESTAMP])
def test_each_held_command_speaks_under_its_own_name_and_names_its_own_recipe(tmp_path, held):
    refused = hold_to_pin(_pin(tmp_path), commit=True, installed=CHECKOUT_AT_THE_PIN).lines(held)
    allowed = hold_to_pin(_pin(tmp_path), commit=True, allow=True, installed=CHECKOUT_AT_THE_PIN).lines(held)
    assert refused[0].startswith(f"{held.name}: {REFUSED}") and held.recipe in "\n".join(refused)
    assert len(allowed) == 1 and allowed[0].startswith(f"{held.name}: {ALLOWED}")
    assert RUN.name != RESTAMP.name and RUN.recipe != RESTAMP.recipe


def test_two_spellings_of_one_version_are_one_release():
    assert same_release("0.1.7.dev2", "0.1.7dev2") and same_release("0.1.7", "0.1.7")
    assert not same_release("0.1.7", "0.1.7.dev2") and not same_release("0.1.7", None)
    assert same_release("not a version", "not a version") and not same_release("not a version", "0.1.7")


def test_the_pin_file_is_the_one_the_starters_write():
    assert starters.VERSION_FILE == PIN_FILE


# ------------------------------------------------ the facts, from the distributions' own records

def _dist_info(site: Path, name: str, version: str, direct_url: dict | str | None = None) -> None:
    info = site / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n")
    if direct_url is not None:
        (info / "direct_url.json").write_text(direct_url if isinstance(direct_url, str) else json.dumps(direct_url))


def _installed_under(site: Path) -> Installed:
    return installed_release(metadata.distributions(path=[str(site)]))


def test_an_index_install_carries_no_record_and_is_the_release(tmp_path):
    for name in ("cs-image-system", "cs-image-system-system", "cs-image-system-base"):
        _dist_info(tmp_path, name, PINNED)
    _dist_info(tmp_path, "cs-image-system-contract", "0.4.0")              # a part with a version of its own
    _dist_info(tmp_path, "something-else", "9.9", {"url": "file:///elsewhere", "dir_info": {"editable": True}})
    assert _installed_under(tmp_path) == Installed(PINNED)                 # another project's install says nothing


def test_an_editable_workspace_is_a_checkout_in_every_part(tmp_path):
    _dist_info(tmp_path, "cs-image-system", PINNED, {"url": f"file://{CHECKOUT}", "dir_info": {"editable": True}})
    _dist_info(tmp_path, "cs_image_system_base", PINNED,
               {"url": f"file://{CHECKOUT}/packages/base", "dir_info": {"editable": True}})
    found = _installed_under(tmp_path)
    assert found.version == PINNED
    assert [(s.distribution, s.kind, s.path) for s in found.sources] == [
        ("cs-image-system", DIRECTORY, CHECKOUT), ("cs-image-system-base", DIRECTORY, f"{CHECKOUT}/packages/base")]


def test_a_part_from_a_path_under_an_index_umbrella_is_found(tmp_path):
    _dist_info(tmp_path, "cs-image-system", PINNED)
    _dist_info(tmp_path, "cs-image-system-base", PINNED, {"url": f"file://{CHECKOUT}/packages/base", "dir_info": {}})
    found = _installed_under(tmp_path)
    assert found.version == PINNED and [s.distribution for s in found.sources] == ["cs-image-system-base"]


def test_the_system_distribution_gives_the_version_when_no_umbrella_is_installed(tmp_path):
    _dist_info(tmp_path, "cs-image-system-system", OTHER)
    assert _installed_under(tmp_path) == Installed(OTHER)
    assert installed_release([]) == Installed(None)


@pytest.mark.parametrize("record, kind", [
    ({"url": "https://example.invalid/the-system.git", "vcs_info": {"vcs": "git", "commit_id": "0" * 40}}, REPOSITORY),
    ({"url": "file:///work/dist/the-system.whl", "archive_info": {}}, ARCHIVE),
    ("{ not json", ARCHIVE),
])
def test_any_record_at_all_means_not_from_an_index(record, kind):
    found = source_install("cs-image-system", record if isinstance(record, str) else json.dumps(record))
    assert found is not None and found.kind == kind
    assert source_install("cs-image-system", None) is None


def test_the_running_environment_answers_with_its_own_version():
    assert installed_release().version == metadata.version("cs-image-system")


# ------------------------------------------------ through the command

def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def recorded_tree(tmp_path, monkeypatch):
    """A copy of the frozen fixture as a git repository with one commit,
    and the environment's word to go on taken away."""
    stub_environment(monkeypatch)
    monkeypatch.delenv(ALLOW_ENVVAR, raising=False)
    root = copy_config(tmp_path)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "recorder@example.invalid")
    _git(root, "config", "user.name", "recorder")
    return root


def _committed(root: Path) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "config")
    return _git(root, "rev-parse", "HEAD")


def _invoke(root: Path, *args: str, env: dict[str, str] | None = None):
    from cs_image_system.system.cli import app
    return runner.invoke(app, ["--root-dir", str(root), *args], catch_exceptions=False, input="", env=env)


def _installed_is(monkeypatch, facts: Installed) -> None:
    monkeypatch.setattr(pinned_release, "installed_release", lambda: facts)


@pytest.mark.parametrize("facts", [Installed(OTHER), CHECKOUT_AT_THE_PIN])
def test_the_refusal_comes_before_anything_is_generated_or_committed(recorded_tree, monkeypatch, facts):
    root = _pin(recorded_tree)
    head = _committed(root)
    before = tree(root, ignore_parts=(".git",))
    _installed_is(monkeypatch, facts)
    result = _invoke(root, "run", "--all", "--commit")
    assert result.exit_code == 2, result.output
    assert REFUSED in result.output and ALLOWED not in result.output
    assert tree(root, ignore_parts=(".git",)) == before and not (root / "generated").exists()
    assert _git(root, "rev-parse", "HEAD") == head and _git(root, "status", "--porcelain") == ""


def test_the_flag_goes_on_says_so_and_the_run_commits(recorded_tree, monkeypatch):
    root = _pin(recorded_tree)
    head = _committed(root)
    _installed_is(monkeypatch, CHECKOUT_AT_THE_PIN)
    result = _invoke(root, "run", "identity", "--commit", ALLOW_FLAG)
    assert result.exit_code == 0, result.output
    assert ALLOWED in result.output and REFUSED not in result.output
    assert _git(root, "rev-parse", "HEAD") != head


def test_the_environment_variable_goes_on_as_the_flag_does(recorded_tree, monkeypatch):
    root = _pin(recorded_tree)
    head = _committed(root)
    _installed_is(monkeypatch, Installed(OTHER))
    result = _invoke(root, "run", "identity", "--commit", env={ALLOW_ENVVAR: "1"})
    assert result.exit_code == 0, result.output
    assert ALLOWED in result.output and REFUSED not in result.output
    assert _git(root, "rev-parse", "HEAD") != head


def test_the_pinned_release_commits_and_says_nothing_of_the_pin(recorded_tree, monkeypatch):
    root = _pin(recorded_tree)
    head = _committed(root)
    _installed_is(monkeypatch, FROM_INDEX)
    result = _invoke(root, "run", "identity", "--commit")
    assert result.exit_code == 0, result.output
    assert ALLOWED not in result.output and REFUSED not in result.output
    assert _git(root, "rev-parse", "HEAD") != head


def test_a_run_without_commit_over_a_pinned_tree_is_not_checked(recorded_tree, monkeypatch):
    root = _pin(recorded_tree, OTHER)
    _installed_is(monkeypatch, CHECKOUT_AT_THE_PIN)
    result = _invoke(root, "run", "identity")
    assert result.exit_code == 0, result.output
    assert ALLOWED not in result.output and REFUSED not in result.output


def test_a_tree_without_a_pin_commits_from_any_install(recorded_tree):
    """The frozen fixture has no pin, so the suite's committing runs, made
    by whatever this environment is, are never held."""
    assert not (recorded_tree / PIN_FILE).exists()
    head = _committed(recorded_tree)
    result = _invoke(recorded_tree, "run", "identity", "--commit")
    assert result.exit_code == 0, result.output
    assert ALLOWED not in result.output and REFUSED not in result.output
    assert _git(recorded_tree, "rev-parse", "HEAD") != head


@pytest.mark.parametrize("command", [("run",), ("lineage", "restamp")])
def test_the_help_of_each_held_command_names_the_flag_and_its_variable(monkeypatch, command):
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr("sys.argv", ["cs-image-system", *command, "--help"])
    from cs_image_system.system.cli import app
    result = runner.invoke(app, [*command, "--help"], catch_exceptions=False)
    assert result.exit_code == 0 and ALLOW_FLAG in result.output and ALLOW_ENVVAR in result.output


def test_the_help_of_a_disposal_offers_no_such_flag(monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr("sys.argv", ["cs-image-system", "dispose", "image", "--help"])
    from cs_image_system.system.cli import app
    result = runner.invoke(app, ["dispose", "image", "--help"], catch_exceptions=False)
    assert result.exit_code == 0 and ALLOW_FLAG not in result.output and ALLOW_ENVVAR not in result.output


# ------------------------------------------------ a restamp of lineage, and a disposal

RUNTIME = "aws-east2-runtime"
SERIES = "basic-rh-10"
HEAD_BUILD = "build-with-an-older-fingerprint"
OLDER_FINGERPRINT = "0" * 64


def _recorded_head(root: Path) -> None:
    """One recorded build, the head of its series, whose fingerprint is not
    the one the tree computes now: what a restamp re-records."""
    here = os.getcwd()
    try:
        load_context(root).meta_state.add_build({
            "build_id": HEAD_BUILD, "series": SERIES, "runtime": RUNTIME, "name": "n",
            "run": "2026_09_02t00_00_00_000000", "parent": "vendor", "input_fingerprint": OLDER_FINGERPRINT})
    finally:
        os.chdir(here)


def _recorded_fingerprint(root: Path) -> str | None:
    here = os.getcwd()
    try:
        build = load_context(root).meta_state.build(HEAD_BUILD)
    finally:
        os.chdir(here)
    return None if build is None else build["input_fingerprint"]


def _restamp(root: Path, *args: str, env: dict[str, str] | None = None):
    return _invoke(root, *args, "lineage", "restamp", "--runtime", RUNTIME, "--commit", env=env)


def test_a_committing_restamp_is_refused_before_it_computes_or_writes(recorded_tree, monkeypatch):
    from cs_image_system.system import cli
    root = _pin(recorded_tree)
    _recorded_head(root)
    head = _committed(root)
    before = tree(root, ignore_parts=(".git",))
    asked: list[str] = []
    monkeypatch.setattr(cli, "restamp", lambda ctx, runtime, series: asked.append(runtime) or [])
    _installed_is(monkeypatch, CHECKOUT_AT_THE_PIN)
    result = _restamp(root, "--no-dry-run")
    assert result.exit_code == 2, result.output
    assert f"{RESTAMP.name}: {REFUSED}" in result.output and ALLOWED not in result.output
    assert asked == [] and tree(root, ignore_parts=(".git",)) == before
    assert _git(root, "rev-parse", "HEAD") == head and _git(root, "status", "--porcelain") == ""


@pytest.mark.parametrize("word", ["flag", "variable"])
def test_the_operators_word_lets_a_committing_restamp_go_on(recorded_tree, monkeypatch, word):
    root = _pin(recorded_tree)
    _recorded_head(root)
    head = _committed(root)
    _installed_is(monkeypatch, CHECKOUT_AT_THE_PIN)
    if word == "flag":
        result = _invoke(root, "--no-dry-run", "lineage", "restamp", "--runtime", RUNTIME, "--commit", ALLOW_FLAG)
    else:
        result = _restamp(root, "--no-dry-run", env={ALLOW_ENVVAR: "1"})
    assert result.exit_code == 0, result.output
    assert f"{RESTAMP.name}: {ALLOWED}" in result.output and REFUSED not in result.output
    assert _git(root, "rev-parse", "HEAD") != head
    assert _recorded_fingerprint(root) not in (None, OLDER_FINGERPRINT)


def test_a_dry_restamp_over_a_pinned_tree_is_not_checked(recorded_tree, monkeypatch):
    root = _pin(recorded_tree)
    _recorded_head(root)
    _installed_is(monkeypatch, CHECKOUT_AT_THE_PIN)
    result = _restamp(root)                                   # the global dry run: the plan, nothing written
    assert result.exit_code == 0, result.output
    assert ALLOWED not in result.output and REFUSED not in result.output
    assert _recorded_fingerprint(root) == OLDER_FINGERPRINT


def test_a_committing_disposal_is_not_held_to_the_pin(recorded_tree, monkeypatch):
    """A disposal records what was removed, whatever code removed it."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    root = _pin(recorded_tree)
    _recorded_head(root)
    head = _committed(root)
    removed: list[str] = []
    monkeypatch.setattr(AwsCloudBuilder, "dispose_image", lambda self, build_id: removed.append(build_id) or True)
    _installed_is(monkeypatch, CHECKOUT_AT_THE_PIN)
    result = _invoke(root, "--no-dry-run", "dispose", "image", HEAD_BUILD, "--commit")
    assert result.exit_code == 0, result.output
    assert ALLOWED not in result.output and REFUSED not in result.output
    assert removed == [HEAD_BUILD] and _git(root, "rev-parse", "HEAD") != head
    assert _recorded_fingerprint(root) is None
