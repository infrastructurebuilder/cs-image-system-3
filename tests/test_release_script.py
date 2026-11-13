# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The release family is scripts/release.py, run by four one-line recipes.

Against a fake shell that answers every command the family runs (uv,
bump-my-version, just, the probe scripts) and lets git through to a
temporary repository whose ``origin`` is a scratch bare repository (so the
pushes are real and local): the probes in their order and their one-line
verdicts; the dry form that prints every move and push it would make and
touches no ref and no file; the real form's order (the index, the move to
main from develop, the resync, the bar, the index again, the bump, the
lock, the upload, the commit, the tag, the pushes, develop's fast-forward,
the resync) and its closing line, from develop, main and a maintenance
branch; the return to the starting branch on a refusal before the bump;
what a failed upload says about the uncommitted bump and where it leaves
it; a failed push named with what is left; ``release-finish``'s guards and
its ending; ``release-take``'s release, then the take in the live
configuration, and what it says when either stops; ``publish``'s own
order; the release's row in docs/CHANGES.md; the fetch probe, which refuses before anything changes when origin holds
commits a branch the ending pushes lacks; and the one reader of the
sibling repository's working tree.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "release.py"
CHANGES_HEAD = """# Changes

| Stage | Landed | Released in | Squash subject |
| --- | --- | --- | --- |
"""


def _load():
    loader = importlib.machinery.SourceFileLoader("release_script", str(SCRIPT))
    spec = importlib.util.spec_from_loader("release_script", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    sys.modules["release_script"] = m          # the dataclasses resolve their annotations through the module
    loader.exec_module(m)
    return m


R = _load()


@pytest.fixture(autouse=True)
def _a_git_identity(monkeypatch):
    """The script's own commits and tags reach the scratch repositories as real
    git calls; a machine with no configured identity (a CI runner) refuses them,
    so every test commits as a synthetic one."""
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "t")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "t@example.invalid")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


class FakeShell:
    """Answers each command by the first needle found in its text (a Done, or a callable that
    makes one), lets git through to the real repositories, and records every call."""

    def __init__(self, answers: list[tuple[str, object]] | None = None):
        self.answers = list(answers or [])
        self.calls: list[list[str]] = []
        self.cwds: list[Path | None] = []

    def __call__(self, cmd: list[str], *, cwd: Path | None = None, capture: bool = True, env=None):
        self.calls.append(list(cmd))
        self.cwds.append(cwd)
        text = " ".join(cmd)
        if cmd[0] == "git":
            return R.run(cmd, cwd=cwd, capture=True, env=env)
        for needle, answer in self.answers:
            if needle in text:
                return answer(cmd) if callable(answer) else answer
        return R.Done(0)

    def texts(self) -> list[str]:
        return [" ".join(c) for c in self.calls]

    def first(self, needle: str) -> int:
        return next(i for i, t in enumerate(self.texts()) if needle in t)

    def count(self, needle: str) -> int:
        return sum(needle in t for t in self.texts())


def _system_repo(tmp_path: Path, *, branch: str = "main", develop_ahead: bool = False, remote: bool = True) -> Path:
    """A system checkout: pyproject, two members (one private), the lock and the CHANGES page,
    committed on develop, with ``main`` and ``branch`` cut at that commit (``develop_ahead``: develop
    one commit further) and ``branch`` checked out. With ``remote`` its ``origin`` is a scratch bare
    repository holding every branch, so the release's pushes are real and local."""
    root = tmp_path / "system"
    (root / "packages" / "one").mkdir(parents=True)
    (root / "packages" / "two").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n')
    (root / "packages" / "one" / "pyproject.toml").write_text('[project]\nname = "x-one"\nversion = "0.1.0"\n')
    (root / "packages" / "two" / "pyproject.toml").write_text(
        '[project]\nname = "x-two"\nversion = "0.1.0"\nclassifiers = ["Private :: Do Not Upload"]\n')
    (root / "uv.lock").write_text("lock 0.1.0\n")
    (root / "docs" / "CHANGES.md").write_text(
        CHANGES_HEAD + '| <a id="s2"></a>§2 | 2000-01-02 | not yet | Stage 2: two |\n'
        + '| <a id="r0-1-0"></a>release 0.1.0 | 2000-01-01 | 0.1.0 | release 0.1.0 |\n'
        + '| <a id="s1"></a>§1 | 2000-01-01 | 0.1.0 | Stage 1: one |\n')
    _git(root, "init", "-q", "-b", "develop")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "one")
    for name in sorted({"main", branch} - {"develop"}):
        _git(root, "branch", name)
    if develop_ahead:
        (root / "a").write_text("2\n")
        _git(root, "add", "a")
        _git(root, "commit", "-q", "-m", "two")
    if remote:
        bare = tmp_path / "remote.git"
        _git(tmp_path, "init", "-q", "--bare", str(bare))
        (bare / "hooks").mkdir(exist_ok=True)
        _git(bare, "config", "core.hooksPath", str(bare / "hooks"))     # a hook a test plants is the one that runs
        _git(root, "remote", "add", "origin", str(bare))
        _git(root, "push", "-q", "origin", "--all")
    _git(root, "checkout", "-q", branch)
    return root


def _remote(root: Path) -> Path:
    return root.parent / "remote.git"


def _refs(repo: Path) -> str:
    """Every branch and tag of a repository and the object each names: what the dry form must leave as it
    was. The remote-tracking refs are left out: the fetch probe moves them, and that is all it may move."""
    return _git(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/tags")


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def _refuse_pushes_to(root: Path, ref: str) -> None:
    """A pre-receive hook in the scratch remote that refuses one ref: a push of it fails as a real one would."""
    hook = _remote(root) / "hooks" / "pre-receive"
    hook.write_text(f'#!/bin/sh\nwhile read old new ref; do [ "$ref" = "{ref}" ] && exit 1; done\nexit 0\n')
    hook.chmod(0o755)


def _sibling_repo(tmp_path: Path, *, configured: bool = True, evidence: bool = True) -> Path:
    root = tmp_path / "config"
    (root / "cfg").mkdir(parents=True)
    (root / "meta-state").mkdir()
    if configured:
        (root / "cfg" / "_config.yml").write_text("name: x\n")
    (root / "meta-state" / "lineage.yaml").write_text("{}\n")
    _git(root, "init", "-q", "-b", "develop")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "one")
    _git(root, "tag", "-a", "v0.1.0-before", "-m", "before")
    if evidence:
        (root / "meta-state" / "mod-tests.yaml").write_text("results: {}\n")
    return root


def _bump_writer(root: Path, new: str) -> Callable[[list[str]], object]:
    """A bump-my-version stand-in: every version line and the lock take the new version."""
    def bump(cmd: list[str]):
        for p in [root / "pyproject.toml", *root.glob("packages/*/pyproject.toml")]:
            p.write_text(p.read_text().replace('version = "0.1.0"', f'version = "{new}"'))
        (root / "uv.lock").write_text(f"lock {new}\n")
        return R.Done(0)
    return bump


def _summary_writer(held: int, total: int, rc: int) -> Callable[[list[str]], object]:
    def publish_dist(cmd: list[str]):
        if "--summary" in cmd:
            Path(cmd[cmd.index("--summary") + 1]).write_text(f"held {held}\ntotal {total}\nstatus {rc}\n")
        return R.Done(rc)
    return publish_dist


def _family(root: Path, shell: FakeShell, sibling: Path | None = None, *, env: dict[str, str] | None = None,
            said: list[str] | None = None):
    tree = R.read_sibling(sibling or root / "no-config", run=shell)
    return R.Family(root=root, sibling=tree, run=shell, env=env if env is not None else {"TEST_PYPI_TOKEN": "t"},
                    say=(said if said is not None else []).append, today=lambda: "2001-02-03")


def _current(root: Path) -> Callable[[list[str]], object]:
    """`bump-my-version show current_version`: the version line of the tree as it is now."""
    def show(cmd: list[str]):
        m = re.search(r'^version = "(.*)"$', (root / "pyproject.toml").read_text(), re.M)
        assert m
        return R.Done(0, m.group(1) + "\n")
    return show


def _answers(root: Path, *, new: str = "0.1.1.dev1", ready: int = 0, held: int = 0, total: int = 2, upload: int = 0):
    return [
        ("bump-my-version show current_version", _current(root)),
        ("bump-my-version show --increment", R.Done(0, f"{new}\n")),
        ("bump-my-version bump", _bump_writer(root, new)),
        ("publish-target-ready", R.Done(ready)),
        ("publish-dist", _summary_writer(held, total, upload)),
    ]


SYNC = ["uv", "sync", "--all-extras"]
MOVE = [["git", "checkout", "main"], ["git", "merge", "--ff-only", "develop"]]
ENDING_MAIN = [["git", "push", "--follow-tags", "origin", "main"], ["git", "checkout", "develop"],
               ["git", "merge", "--ff-only", "main"], ["git", "push", "origin", "develop"], SYNC]
ENDING_MAINT = [["git", "push", "--follow-tags", "origin", "release/0.1"], SYNC]
BACK = f"release: {R.BACK.format(branch='develop', cut='main')}"


def _moves(shell: FakeShell) -> list[list[str]]:
    """The branch moves, pushes and resyncs the shell saw, in order; every read and every other command left out."""
    keep = [*MOVE, *ENDING_MAIN, *ENDING_MAINT]
    return [c for c in shell.calls if c in keep]


def _would(cmds: list[list[str]]) -> list[str]:
    return [f"release: {R.WOULD.format(command=' '.join(c))}" for c in cmds]


def _would_lines(said: list[str]) -> list[str]:
    head = f"release: {R.WOULD.format(command='')}"
    return [line for line in said if line.startswith(head)]


def _dry_plan(said: list[str]) -> str:
    """The dry form's line that says what the release would do between the probes and the pushes."""
    return next(line for line in said if line.startswith("release: dry -- on "))


def _files(root: Path) -> dict[Path, str]:
    return {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}


# ------------------------------------------------------------ the sibling

def test_the_sibling_working_tree_is_read_through_one_function(tmp_path: Path, monkeypatch):
    root = _sibling_repo(tmp_path)
    (root / "cfg" / "image-builders.yml").write_text("x: 1\n")
    tree = R.read_sibling(root)
    assert tree.path == root and tree.configured and tree.branch == "develop" and tree.tags == ("v0.1.0-before",)
    assert tree.dirty == ("?? cfg/image-builders.yml", "?? meta-state/mod-tests.yaml")
    assert tree.dirty_apart_from("meta-state/mod-tests.yaml") == ("?? cfg/image-builders.yml",)
    assert tree.has("meta-state/mod-tests.yaml") and not tree.has("meta-state/releases.yaml")
    # the path: the argument, else CSIS_CONFIG_ROOT, else the reference configuration beside the repository
    monkeypatch.setenv("CSIS_CONFIG_ROOT", str(root))
    assert R.read_sibling().path == root
    monkeypatch.delenv("CSIS_CONFIG_ROOT")
    assert R.read_sibling().path == REPO.parent / "cs-image-system-testconfig"
    # not a git checkout, not configured: read without an error
    plain = tmp_path / "plain"
    plain.mkdir()
    bare = R.read_sibling(plain)
    assert bare.branch is None and not bare.configured and bare.dirty == () and bare.tags == ()
    assert R.read_sibling(tmp_path / "absent").branch is None


def test_the_evidence_commit_is_the_one_write_to_the_sibling(tmp_path: Path):
    root = _sibling_repo(tmp_path)
    R.commit_evidence(R.read_sibling(root), "0.1.1")
    assert _git(root, "log", "-1", "--format=%s") == "release 0.1.1: modification-test evidence"
    assert R.read_sibling(root).dirty == ()
    R.commit_evidence(R.read_sibling(root), "0.1.1")                       # nothing staged: no second commit
    assert _git(root, "rev-list", "--count", "HEAD") == "2"
    (root / "meta-state" / "mod-tests.yaml").unlink()
    _git(root, "commit", "-q", "-am", "gone")
    with pytest.raises(R.Refused):
        R.commit_evidence(R.read_sibling(root), "0.1.2")
    R.commit_evidence(R.read_sibling(root), "0.1.2", tolerate_missing=True)  # release-finish's form


# --------------------------------------------------------- the CHANGES row

def test_the_release_row_has_the_pages_shape():
    page = (REPO / "docs" / "CHANGES.md").read_text()
    rows = [ln for ln in page.splitlines() if '<a id="r' in ln]
    assert rows, "the page carries release rows"
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        version, date = cells[2], cells[1]
        assert R.changes_row(version, date) == row.strip(), row


def test_the_release_row_goes_on_top_and_stamps_what_was_not_yet_released(tmp_path: Path):
    page = tmp_path / "CHANGES.md"
    page.write_text(CHANGES_HEAD + '| <a id="s2"></a>§2 | 2000-01-02 | not yet | Stage 2: two |\n'
                    + '| <a id="r0-1-0"></a>release 0.1.0 | 2000-01-01 | 0.1.0 | release 0.1.0 |\n')
    assert R.append_release_row(page, "0.1.1.dev1", "2001-02-03", stamp_unreleased=True)
    lines = page.read_text().splitlines()
    assert lines[4] == '| <a id="r0-1-1-dev1"></a>release 0.1.1.dev1 | 2001-02-03 | 0.1.1.dev1 | release 0.1.1.dev1 |'
    assert lines[5] == '| <a id="s2"></a>§2 | 2000-01-02 | 0.1.1.dev1 | Stage 2: two |'
    assert lines[6].endswith("| release 0.1.0 |") and len(lines) == 7
    # a maintenance branch's release contains none of develop's stages: the row alone
    page.write_text(CHANGES_HEAD + '| <a id="s2"></a>§2 | 2000-01-02 | not yet | Stage 2: two |\n')
    assert R.append_release_row(page, "0.0.2", "2001-02-03", stamp_unreleased=False)
    assert "| not yet |" in page.read_text() and page.read_text().count("release 0.0.2") == 2
    assert not R.append_release_row(tmp_path / "absent.md", "0.0.3", "2001-02-03", stamp_unreleased=True)
    page.write_text("# no table\n")
    with pytest.raises(R.Refused, match="no table"):
        R.append_release_row(page, "0.0.3", "2001-02-03", stamp_unreleased=True)


# ------------------------------------------------------------- the probes

OWN = "own-versions-current"
OWN_LINE = f"{OWN}: x-one 0.1.0 is not on testpypi"


def test_a_test_index_asks_the_venv_and_the_own_versions_alone(tmp_path: Path):
    root = _system_repo(tmp_path)
    shell = FakeShell([("docker info", R.Done(1)), (OWN, R.Done(0, OWN_LINE + "\n"))])
    said: list[str] = []
    _family(root, shell, said=said).probes("test")
    assert said == [f"release: {R.VENV_OK}", OWN_LINE] and shell.count("docker") == 0
    assert shell.first("uv sync --all-extras --check") < shell.first(OWN)
    assert shell.texts()[shell.first(OWN)].endswith(f"scripts/{OWN} test --root {root}")


@pytest.mark.parametrize(("rc", "code", "message"), [(1, 1, "UNBUMPED"), (2, 2, "UNASKED"), (127, 2, "UNASKED")])
def test_an_own_version_package_the_index_would_refuse_is_refused_before_the_gate(tmp_path: Path, rc: int, code: int,
                                                                                  message: str):
    """Exit 1 of scripts/own-versions-current is a package changed under a version the index holds; any
    other failure is "could not ask". Either way the release stops at the probes, for every index:
    no gate, no bump, no tag, the tree as it was."""
    for index, env in (("test", {"TEST_PYPI_TOKEN": "t"}), ("pypi", {"PYPI_TOKEN": "p"})):
        root = _system_repo(tmp_path / index)
        sibling = _sibling_repo(tmp_path / index)
        before = {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
        shell = FakeShell([(OWN, R.Done(rc, OWN_LINE + "\n", "uv: stderr\n")), *_answers(root)])
        said: list[str] = []
        with pytest.raises(R.Refused) as e:
            _family(root, shell, sibling, env=env, said=said).release("patch", index)
        assert e.value.code == code and e.value.message == f"release: {getattr(R, message)}"
        assert OWN_LINE in said and ("uv: stderr" in said) == (rc != 1)
        for never in ("just test", "just full-test", "docker info", "bump-my-version bump", "uv lock", "publish-dist"):
            assert shell.count(never) == 0, never
        assert {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts} == before
        assert _git(root, "status", "--porcelain") == "" and _git(root, "tag", "-l") == ""


@pytest.mark.parametrize("index", ["test", "pypi"])
def test_a_stale_venv_is_refused_for_every_index_in_one_line(tmp_path: Path, index: str):
    root = _system_repo(tmp_path)
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell([("uv sync --all-extras --check", R.Done(1))])).probes(index)
    assert e.value.code == 1 and "behind" in e.value.message and "just init" in e.value.message


def test_pypi_without_docker_is_refused_first(tmp_path: Path):
    root = _system_repo(tmp_path)
    said: list[str] = []
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell([("docker info", R.Done(1))]), said=said).probes("pypi")
    assert said == [f"release: {R.VENV_OK}"]
    assert "docker" in e.value.message and "nothing was changed" in e.value.message


def test_pypi_without_a_live_configuration_or_a_session_is_refused_by_name(tmp_path: Path):
    root = _system_repo(tmp_path)
    said: list[str] = []
    with pytest.raises(R.Refused, match="no live configuration"):
        _family(root, FakeShell(), said=said).probes("pypi")
    assert said[-1] == "release: docker answers"
    sibling = _sibling_repo(tmp_path)
    with pytest.raises(R.Refused, match="absent or expired"):
        _family(root, FakeShell([("just preflight", R.Done(2))]), sibling).probes("pypi")


def test_the_session_line_says_the_minutes_left_and_refuses_only_a_lapsed_token(tmp_path: Path):
    """Three branches of the one line (lapsed, under an hour, enough); the operator's decision is to
    SAY the minutes. A token already lapsed is a fact, not a margin -- preflight judges it too -- so that
    branch alone refuses."""
    root = _system_repo(tmp_path)
    sibling = _sibling_repo(tmp_path)

    def line(minutes: str, rc: int = 0) -> str:
        said: list[str] = []
        shell = FakeShell([("session-minutes-left", R.Done(rc, minutes))])
        _family(root, shell, sibling, said=said).probes("pypi")
        assert shell.texts()[-1].endswith(f"session-minutes-left {sibling}")
        return said[-1]

    assert line("120\n").endswith("the soonest-expiring session has 120 minutes left")
    assert "halfway" in line("30\n") and "30 minutes left" in line("30\n")
    assert line("", rc=1) == f"release: {R.SESSIONS_OK}"
    with pytest.raises(R.Refused, match="lapsed 5 minutes ago"):
        line("-5\n")


def test_release_finish_asks_the_venv_alone(tmp_path: Path):
    root = _system_repo(tmp_path)
    shell = FakeShell([("docker info", R.Done(1))])
    said: list[str] = []
    _family(root, shell, said=said).probes("pypi", "release-finish")
    assert said == [f"release-finish: {R.VENV_OK}"] and shell.count("docker") == 0
    assert shell.count(OWN) == 0                                           # it builds and uploads nothing


# ------------------------------------------------------------- the guards

def test_the_branch_guard_names_the_checkout_and_the_fast_forward(tmp_path: Path):
    feature = _system_repo(tmp_path / "f", branch="feature/x")
    with pytest.raises(R.Refused) as e:
        _family(feature, FakeShell()).branch_guard("release", ancestor_check=True)
    assert "feature/x" in e.value.message and "main alone" in e.value.message and "nothing was changed" in e.value.message
    behind = _system_repo(tmp_path / "b", develop_ahead=True)
    with pytest.raises(R.Refused, match="--ff-only develop"):
        _family(behind, FakeShell()).branch_guard("release", ancestor_check=True)
    assert _family(behind, FakeShell()).branch_guard("release-finish", ancestor_check=False) == "main"
    said: list[str] = []
    maint = _system_repo(tmp_path / "m", branch="release/0.1", develop_ahead=True)
    assert _family(maint, FakeShell(), said=said).branch_guard("release", ancestor_check=True) == "release/0.1"
    assert len(said) == 1 and "maintenance branch release/0.1" in said[0] and "develop is not checked" in said[0]


def test_the_version_plan_takes_a_part_or_a_version_and_refuses_the_rest(tmp_path: Path):
    root = _system_repo(tmp_path)
    fam = _family(root, FakeShell(_answers(root)))
    assert fam.version_plan("0.2.0", "0.1.0") == ("0.2.0", ["bump", "--new-version", "0.2.0"])
    assert fam.version_plan("patch", "0.1.0") == ("0.1.1.dev1", ["bump", "patch"])
    with pytest.raises(R.Refused, match="neither a version part"):
        _family(root, FakeShell([("bump-my-version show --increment", R.Done(1))])).version_plan("nope", "0.1.0")
    with pytest.raises(R.Refused, match="final version"):
        _family(root, FakeShell([("bump-my-version show --increment", R.Done(0, "0.1.0.final2\n"))])).version_plan("dev", "0.1.0")


def test_the_index_the_token_and_the_tag_are_asked_before_anything_changes(tmp_path: Path):
    root = _system_repo(tmp_path)
    for ready, needle, code in ((75, "cannot take an upload now", 75), (1, "never re-cut", 1), (3, "could not run", 2)):
        shell = FakeShell(_answers(root, ready=ready))
        with pytest.raises(R.Refused) as e:
            _family(root, shell).release("patch", "test", "yes")
        assert needle in e.value.message and e.value.code == code
        assert shell.count("bump-my-version bump") == 0 and shell.count("uv sync") == 0
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell(_answers(root)), env={}).release("patch", "test", "yes")
    assert e.value.code == 2 and "neither UV_PUBLISH_TOKEN nor TEST_PYPI_TOKEN" in e.value.message
    with pytest.raises(R.Refused, match="PYPI_TOKEN is set"):
        _family(root, FakeShell(_answers(root)), env={}).release("patch", "pypi", "yes")
    _git(root, "tag", "v0.1.1.dev1")
    with pytest.raises(R.Refused, match="already tagged here"):
        _family(root, FakeShell(_answers(root))).release("patch", "test", "yes")
    with pytest.raises(R.Refused, match="not 'gitlab'"):
        _family(root, FakeShell(_answers(root))).release("patch", "gitlab", "yes")


# ----------------------------------------------------------- the dry form

def test_the_dry_form_prints_what_it_would_do_and_touches_nothing(tmp_path: Path):
    root = _system_repo(tmp_path)
    before = {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
    shell = FakeShell([(OWN, R.Done(0, OWN_LINE + "\n")), *_answers(root)])
    said: list[str] = []
    env = {"TEST_PYPI_TOKEN": "t"}
    assert _family(root, shell, env=env, said=said).release("patch", "test", "yes") == 0
    # the dry form answers "would this release go through": the own-version probe runs in it too
    assert shell.count(OWN) == 1 and shell.first("uv sync --all-extras --check") < shell.first(OWN)
    plan = _dry_plan(said)
    assert said.index(OWN_LINE) < said.index(plan)
    assert plan.startswith("release: dry") and "on main, 0.1.0 would become 0.1.1.dev1:" in plan
    for needle in ("the probes above passed", "just test", "the index again", "bump-my-version bump patch", "uv lock",
                   "just publish test", "commit 'release 0.1.1.dev1'", "docs/CHANGES.md", "tag v0.1.1.dev1"):
        assert needle in plan, needle
    assert _would_lines(said) == _would([SYNC, *ENDING_MAIN]) and _moves(shell) == []
    # the order: the index, then the token, the tag, then the venv probe; nothing after the dry line
    assert shell.first("publish-target-ready") < shell.first("uv sync --all-extras --check")
    assert "--refuse-held" in shell.texts()[shell.first("publish-target-ready")]
    for never in ("just test", "bump-my-version bump", "uv lock", "publish-dist", "just build"):
        assert shell.count(never) == 0, never
    assert env["UV_PUBLISH_TOKEN"] == "t"
    assert {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts} == before
    assert _git(root, "status", "--porcelain") == "" and _git(root, "tag", "-l") == ""


def test_the_dry_form_of_a_pypi_release_names_full_test(tmp_path: Path):
    root = _system_repo(tmp_path)
    sibling = _sibling_repo(tmp_path)
    said: list[str] = []
    fam = _family(root, FakeShell(_answers(root)), sibling, env={"PYPI_TOKEN": "p"}, said=said)
    assert fam.release("stage", "pypi", "yes") == 0
    assert "just full-test, the index again" in _dry_plan(said) and "just publish pypi" in _dry_plan(said)


# ---------------------------------------------------------- the real form

def test_the_real_form_probes_gates_asks_again_bumps_uploads_then_commits_and_tags(tmp_path: Path):
    root = _system_repo(tmp_path)
    shell = FakeShell(_answers(root))
    said: list[str] = []
    fam = _family(root, shell, said=said)
    assert fam.release("patch", "test") == 0
    t = shell.texts()
    order = [shell.first(n) for n in ("publish-target-ready", "uv sync --all-extras --check", OWN, "just test",
                                      "bump-my-version bump patch", "uv lock", "just build", "publish-dist")]
    assert order == sorted(order), t
    asks = [i for i, x in enumerate(t) if "publish-target-ready" in x]
    assert len(asks) == 3 and shell.count("just test") == 1                                 # twice refusing a held version, then publish's own
    assert [("--refuse-held" in t[i]) for i in asks] == [True, True, False]
    assert shell.first("just test") < asks[1] < shell.first("bump-my-version bump")         # the index again after the bar
    assert shell.first("publish-dist") < shell.first("git add")                             # the upload before the commit
    dist = t[shell.first("publish-dist")]
    assert " test --version 0.1.1.dev1 --token-var TEST_PYPI_TOKEN --summary " in dist
    assert shell.first("git tag -a") < shell.first("git push")                              # the pushes after the tag
    assert _git(root, "log", "-1", "--format=%s") == "release 0.1.1.dev1" and _git(root, "tag", "-l") == "v0.1.1.dev1"
    assert _git(root, "status", "--porcelain") == ""
    committed = _git(root, "show", "--stat", "--format=", "HEAD")
    for name in ("pyproject.toml", "packages/one/pyproject.toml", "packages/two/pyproject.toml", "uv.lock", "docs/CHANGES.md"):
        assert name in committed, name
    page = (root / "docs" / "CHANGES.md").read_text().splitlines()
    assert page[4] == R.changes_row("0.1.1.dev1", "2001-02-03") and "| not yet |" not in "\n".join(page)
    pushed = fam.closing_line("main")
    assert pushed == "; ".join(" ".join(c) for c in ENDING_MAIN[:-1])
    assert said[-1] == R.RELEASED.format(version="0.1.1.dev1", name="testpypi", pushed=pushed, branch="develop")


def test_a_pypi_release_runs_full_test_needs_the_evidence_and_commits_it_in_the_sibling(tmp_path: Path):
    root = _system_repo(tmp_path)
    sibling = _sibling_repo(tmp_path, evidence=False)
    shell = FakeShell(_answers(root))
    with pytest.raises(R.Refused, match="no modification-test evidence"):
        _family(root, shell, sibling, env={"PYPI_TOKEN": "p"}).release("stage", "pypi")
    assert shell.count("just full-test") == 1 and shell.count("just test") == 0 and shell.count("bump-my-version bump") == 0
    (sibling / "meta-state" / "mod-tests.yaml").write_text("results: {}\n")
    (sibling / "cfg" / "other.yml").write_text("x\n")
    with pytest.raises(R.Refused, match="clean apart from its mod-test evidence"):
        _family(root, FakeShell(_answers(root)), sibling, env={"PYPI_TOKEN": "p"}).release("stage", "pypi")
    (sibling / "cfg" / "other.yml").unlink()
    said: list[str] = []
    assert _family(root, FakeShell(_answers(root, new="0.1.1")), sibling, env={"PYPI_TOKEN": "p"}, said=said) \
        .release("stage", "pypi") == 0
    assert _git(sibling, "log", "-1", "--format=%s") == "release 0.1.1: modification-test evidence"
    assert _git(root, "tag", "-l") == "v0.1.1" and "is on pypi" in said[-1]


def test_a_dirty_tree_is_refused_before_the_bar(tmp_path: Path):
    root = _system_repo(tmp_path)
    (root / "stray").write_text("x\n")
    shell = FakeShell(_answers(root))
    with pytest.raises(R.Refused) as e:
        _family(root, shell).release("patch", "test")
    assert "must be clean" in e.value.message and "?? stray" in e.value.message and "discard" in e.value.message
    assert shell.count("just test") == 0


def test_a_failed_upload_says_what_to_do_with_the_bump(tmp_path: Path):
    # no project holds the version: discard the bump
    root = _system_repo(tmp_path / "a")
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell(_answers(root, upload=1, held=0))).release("patch", "test")
    assert e.value.code == 1 and e.value.message.endswith(
        "discard it with: git checkout -- pyproject.toml packages/*/pyproject.toml uv.lock")
    assert _git(root, "tag", "-l") == "" and " M pyproject.toml" in _git(root, "status", "--porcelain")
    # some do: KEEP it, publish again (in a day after PyPI's 429), then release-finish
    root = _system_repo(tmp_path / "b")
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell(_answers(root, upload=75, held=1, total=2))).release("patch", "test")
    assert e.value.code == 75 and "stopped part-way: 1 of 2 projects hold 0.1.1.dev1" in e.value.message
    assert "KEEP the uncommitted bump" in e.value.message and "`just publish test` again in a day" in e.value.message
    assert "`just release-finish test`" in e.value.message
    assert _git(root, "tag", "-l") == "" and "not yet" in (root / "docs" / "CHANGES.md").read_text()
    root = _system_repo(tmp_path / "c")
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell(_answers(root, upload=1, held=2, total=2))).release("patch", "test")
    assert "`just publish test` again until" in e.value.message and e.value.code == 1


def test_a_failed_bar_stops_the_release_with_its_own_exit_code(tmp_path: Path):
    root = _system_repo(tmp_path)
    shell = FakeShell([("just test", R.Done(3)), *_answers(root)])
    with pytest.raises(R.Refused) as e:
        _family(root, shell).release("patch", "test")
    assert e.value.code == 3 and e.value.message == "" and shell.count("publish-target-ready") == 1


# ------------------------------------------------- the moves and the pushes

def test_from_develop_the_release_moves_to_main_cuts_pushes_and_comes_back(tmp_path: Path):
    """From develop: main checked out and fast-forwarded to develop, the venv synced before the probes,
    the release cut on main, main pushed with its tag, develop checked out, fast-forwarded and pushed,
    and the venv synced again as the last act. The remote is a scratch bare repository: the pushes are real."""
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    shell = FakeShell(_answers(root))
    said: list[str] = []
    fam = _family(root, shell, said=said)
    assert fam.release("patch", "test") == 0
    assert _moves(shell) == [*MOVE, SYNC, *ENDING_MAIN]
    t = shell.texts()
    first_sync = t.index(" ".join(SYNC))
    assert t.index(" ".join(MOVE[1])) < first_sync < shell.first("uv sync --all-extras --check") < shell.first(OWN)
    assert shell.first("git tag -a") < t.index(" ".join(ENDING_MAIN[0])) and t[-1] == " ".join(SYNC)
    head = _git(root, "rev-parse", "HEAD")
    assert _head(root) == "develop" and _git(root, "log", "-1", "--format=%s") == "release 0.1.1.dev1"
    for repo in (root, _remote(root)):
        assert _git(repo, "rev-parse", "main") == head == _git(repo, "rev-parse", "develop"), repo
        assert _git(repo, "tag", "-l") == "v0.1.1.dev1", repo
    assert said[-1] == R.RELEASED.format(version="0.1.1.dev1", name="testpypi", pushed=fam.closing_line("main"),
                                         branch="develop")


def test_from_main_the_release_pushes_main_with_its_tag_and_brings_develop_up(tmp_path: Path):
    root = _system_repo(tmp_path)
    shell = FakeShell(_answers(root))
    assert _family(root, shell).release("patch", "test") == 0
    assert _moves(shell) == [SYNC, *ENDING_MAIN]                                # no move to make before the cut
    head = _git(root, "rev-parse", "HEAD")
    assert _head(root) == "develop"
    for repo in (root, _remote(root)):
        assert _git(repo, "rev-parse", "main") == head == _git(repo, "rev-parse", "develop"), repo
        assert _git(repo, "tag", "-l") == "v0.1.1.dev1", repo


def test_from_a_maintenance_branch_the_release_pushes_that_branch_and_leaves_develop(tmp_path: Path):
    root = _system_repo(tmp_path, branch="release/0.1", develop_ahead=True)
    remote = _remote(root)
    develop = [_git(repo, "rev-parse", "develop") for repo in (root, remote)]
    shell = FakeShell(_answers(root))
    said: list[str] = []
    fam = _family(root, shell, said=said)
    assert fam.release("patch", "test") == 0
    assert _moves(shell) == [SYNC, *ENDING_MAINT] and _head(root) == "release/0.1"
    assert [_git(repo, "rev-parse", "develop") for repo in (root, remote)] == develop
    assert _git(remote, "rev-parse", "release/0.1") == _git(root, "rev-parse", "HEAD")
    assert _git(remote, "tag", "-l") == "v0.1.1.dev1"
    assert said[-1] == R.RELEASED.format(version="0.1.1.dev1", name="testpypi", pushed=fam.closing_line("release/0.1"),
                                         branch="release/0.1")
    assert fam.closing_line("release/0.1") == " ".join(ENDING_MAINT[0])


def _second_ask_fails() -> Callable[[list[str]], object]:
    """publish-target-ready: ready when first asked, "not now" when asked again after the bar."""
    asked: list[int] = []

    def ready(cmd: list[str]):
        asked.append(1)
        return R.Done(0 if len(asked) == 1 else R.NOT_NOW)
    return ready


def _sync_fails(cmd: list[str]):
    return R.Done(4 if cmd == SYNC else 0)


@pytest.mark.parametrize(("where", "answer", "code", "said"), [
    ("the venv", ("uv sync --all-extras --check", R.Done(1)), 1, None),
    ("the resync", ("uv sync", _sync_fails), 4, f"release: {R.SYNC_FAILED}"),
    ("a probe", (OWN, R.Done(1)), 1, f"release: {R.UNBUMPED}"),
    ("the bar", ("just test", R.Done(3)), 3, ""),
    ("the index again", ("publish-target-ready", _second_ask_fails()), R.NOT_NOW, None),
])
def test_a_refusal_before_the_bump_returns_to_develop_with_main_where_it_was(tmp_path: Path, where: str, answer,
                                                                              code: int, said: str | None):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    refs, remote, files = _refs(root), _refs(_remote(root)), _files(root)
    shell = FakeShell([answer, *_answers(root)])
    with pytest.raises(R.Refused) as e:
        _family(root, shell).release("patch", "test")
    assert e.value.code == code, where
    if said is not None:
        assert e.value.message == (said + "\n" if said else "") + BACK, where
    assert e.value.message.endswith("\n" + BACK) or e.value.message == BACK, where
    assert _moves(shell) == [*MOVE, SYNC, ["git", "checkout", "develop"]], where
    assert shell.count("bump-my-version bump") == 0
    assert _head(root) == "develop" and _refs(root) == refs and _refs(_remote(root)) == remote, where
    assert _files(root) == files and _git(root, "status", "--porcelain") == ""
    if where == "the venv":                                                    # the refusal names the checkout
        assert str(R.REPO) in e.value.message


def test_main_that_cannot_fast_forward_to_develop_is_refused_on_develop(tmp_path: Path):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    _git(root, "checkout", "-q", "main")
    (root / "b").write_text("main alone\n")
    _git(root, "add", "b")
    _git(root, "commit", "-q", "-m", "main's own")
    _git(root, "checkout", "-q", "develop")
    refs = _refs(root)
    for dry in ("no", "yes"):
        shell = FakeShell(_answers(root))
        with pytest.raises(R.Refused) as e:
            _family(root, shell).release("patch", "test", dry)
        assert e.value.message == f"release: {R.NO_FAST_FORWARD.format(cut='main')}" and e.value.code == 1, dry
        assert _moves(shell) == [] and _head(root) == "develop" and _refs(root) == refs, dry


def test_a_failed_upload_from_develop_leaves_the_bump_on_main_and_pushes_nothing(tmp_path: Path):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    remote = _refs(_remote(root))
    shell = FakeShell(_answers(root, upload=1, held=0))
    with pytest.raises(R.Refused) as e:
        _family(root, shell).release("patch", "test")
    assert e.value.code == 1 and _head(root) == "main"
    assert " M pyproject.toml" in _git(root, "status", "--porcelain") and _git(root, "tag", "-l") == ""
    assert _git(root, "rev-parse", "main") == _git(root, "rev-parse", "develop")    # main at develop's head
    assert _moves(shell) == [*MOVE, SYNC] and shell.count("git push") == 0 and _refs(_remote(root)) == remote
    assert "main" in e.value.message.split("discard it with:")[0]                    # names the branch the bump is on


@pytest.mark.parametrize(("ref", "at"), [("refs/heads/main", 0), ("refs/heads/develop", 3)])
def test_a_failed_push_names_itself_and_what_is_left_and_exits_non_zero(tmp_path: Path, ref: str, at: int):
    """The version is on the index and committed and tagged here; the failed push is named with the
    commands that are left, and nothing after it runs."""
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    _refuse_pushes_to(root, ref)
    shell = FakeShell(_answers(root))
    with pytest.raises(R.Refused) as e:
        _family(root, shell).release("patch", "test")
    rest = ENDING_MAIN[at:]
    assert e.value.code != 0
    assert e.value.message == "release: " + R.ENDING_FAILED.format(
        version="0.1.1.dev1", name="testpypi", failed=" ".join(rest[0]), rest=" && ".join(" ".join(c) for c in rest))
    assert _moves(shell) == [*MOVE, SYNC, *ENDING_MAIN[:at + 1]]
    assert _git(root, "tag", "-l") == "v0.1.1.dev1" and _git(root, "log", "-1", "--format=%s") == "release 0.1.1.dev1"
    assert _head(root) == ("main" if at == 0 else "develop")
    assert (_git(_remote(root), "tag", "-l") == "v0.1.1.dev1") == (at > 0)        # main and its tag went up first


@pytest.mark.parametrize(("branch", "lines"), [("develop", [*MOVE, SYNC, *ENDING_MAIN]), ("main", [SYNC, *ENDING_MAIN]),
                                               ("release/0.1", [SYNC, *ENDING_MAINT])])
def test_the_dry_form_names_every_move_and_push_and_changes_no_ref_and_no_file(tmp_path: Path, branch: str,
                                                                               lines: list[list[str]]):
    root = _system_repo(tmp_path, branch=branch, develop_ahead=branch != "main")
    refs, remote, files = _refs(root), _refs(_remote(root)), _files(root)
    shell = FakeShell(_answers(root))
    said: list[str] = []
    assert _family(root, shell, said=said).release("patch", "test", "yes") == 0
    would = _would_lines(said)
    assert would == _would(lines)
    # in the real form's order: the move and the resync, the probes, what the release does, the pushes
    plan = _dry_plan(said)
    ending = len(lines) - (5 if branch != "release/0.1" else 2)
    assert said.index(would[ending - 1]) < said.index(f"release: {R.VENV_OK}") < said.index(plan) \
        < said.index(would[ending])
    assert f"on {'main' if branch == 'develop' else branch}," in plan
    assert _moves(shell) == [] and shell.count("bump-my-version bump") == 0 and shell.count("just test") == 0
    assert _head(root) == branch and _refs(root) == refs and _refs(_remote(root)) == remote
    assert _files(root) == files and _git(root, "status", "--porcelain") == ""


def test_the_dry_form_says_a_venv_behind_the_checkout_and_goes_on(tmp_path: Path):
    """The real form syncs the venv before it asks, so the dry form says it is behind rather than refusing."""
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    said: list[str] = []
    shell = FakeShell([("uv sync --all-extras --check", R.Done(1)), *_answers(root)])
    assert _family(root, shell, said=said).release("patch", "test", "yes") == 0
    assert f"release: {R.VENV_WILL_SYNC}" in said and f"release: {R.VENV_OK}" not in said
    assert _moves(shell) == [] and _head(root) == "develop"


def test_a_checkout_with_no_remote_is_refused_before_anything_changes(tmp_path: Path):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True, remote=False)
    refs = _refs(root)
    for dry in ("yes", "no"):
        shell = FakeShell(_answers(root))
        with pytest.raises(R.Refused) as e:
            _family(root, shell).release("patch", "test", dry)
        assert e.value.message == f"release: {R.NO_REMOTE.format(remote='origin')}", dry
        assert _moves(shell) == [] and _refs(root) == refs and _head(root) == "develop", dry


# ------------------------------------------------------- the fetch probe

def _origin_ahead(root: Path, branch: str) -> None:
    """Someone else's push: one commit on ``branch`` in the scratch remote that the checkout lacks."""
    other = root.parent / f"other-{branch.replace('/', '-')}"
    _git(root.parent, "clone", "-q", "-b", branch, str(_remote(root)), str(other))
    (other / "theirs").write_text(f"{branch}\n")
    _git(other, "add", "theirs")
    _git(other, "commit", "-q", "-m", "theirs")
    _git(other, "push", "-q", "origin", branch)


@pytest.mark.parametrize(("start", "ahead"), [("develop", "main"), ("develop", "develop"), ("main", "main"),
                                              ("main", "develop"), ("release/0.1", "release/0.1")])
@pytest.mark.parametrize("dry", ["no", "yes"])
def test_origin_holding_commits_a_pushed_branch_lacks_is_refused_before_anything_changes(tmp_path: Path, start: str,
                                                                                         ahead: str, dry: str):
    root = _system_repo(tmp_path, branch=start, develop_ahead=start != "main")
    _origin_ahead(root, ahead)
    refs, files = _refs(root), _files(root)
    shell = FakeShell(_answers(root))
    said: list[str] = []
    with pytest.raises(R.Refused) as e:
        _family(root, shell, said=said).release("patch", "test", dry)
    assert e.value.message == f"release: {R.BEHIND_ORIGIN.format(remote='origin', branch=ahead, count='1')}"
    assert e.value.code == 1 and shell.count("git fetch -q origin") == 1
    for never in ("uv sync", "just test", "bump-my-version bump", "uv lock", "just build", "publish-dist",
                  "git push", "git checkout"):
        assert shell.count(never) == 0, never
    assert _moves(shell) == [] and _head(root) == start and _refs(root) == refs and _files(root) == files
    assert _git(root, "status", "--porcelain") == "" and not _would_lines(said)


def test_a_maintenance_release_asks_its_own_branch_alone(tmp_path: Path):
    """develop is never pushed by a maintenance release, so origin's develop ahead of it is no concern."""
    root = _system_repo(tmp_path, branch="release/0.1", develop_ahead=True)
    _origin_ahead(root, "develop")
    said: list[str] = []
    assert _family(root, FakeShell(_answers(root)), said=said).release("patch", "test") == 0
    assert f"release: {R.LEVEL_WITH_ORIGIN.format(remote='origin', branches='release/0.1')}" in said


def test_a_local_branch_ahead_of_origin_passes_and_is_pushed(tmp_path: Path):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    (root / "mine").write_text("not yet pushed\n")
    _git(root, "add", "mine")
    _git(root, "commit", "-q", "-m", "mine")
    said: list[str] = []
    assert _family(root, FakeShell(_answers(root)), said=said).release("patch", "test") == 0
    assert f"release: {R.LEVEL_WITH_ORIGIN.format(remote='origin', branches='main or develop')}" in said
    assert _git(_remote(root), "rev-parse", "develop") == _git(root, "rev-parse", "HEAD")


def test_the_dry_form_fetches_and_says_origin_holds_nothing_the_pushes_lack(tmp_path: Path):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    said: list[str] = []
    shell = FakeShell(_answers(root))
    assert _family(root, shell, said=said).release("patch", "test", "yes") == 0
    level = f"release: {R.LEVEL_WITH_ORIGIN.format(remote='origin', branches='main or develop')}"
    assert shell.count("git fetch -q origin") == 1 and said.index(level) < said.index(_dry_plan(said))
    _git(root, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell(_answers(root))).release("patch", "test", "yes")
    assert e.value.message == f"release: {R.NO_FETCH.format(remote='origin')}"


def test_release_finish_asks_origin_before_it_commits(tmp_path: Path):
    root = _system_repo(tmp_path)
    _origin_ahead(root, "develop")
    _bumped(root)
    shell = FakeShell([("bump-my-version show current_version", R.Done(0, "0.1.1.dev1\n"))])
    with pytest.raises(R.Refused) as e:
        _family(root, shell).finish("test")
    assert e.value.message == f"release-finish: {R.BEHIND_ORIGIN.format(remote='origin', branch='develop', count='1')}"
    assert shell.count("publish-target-ready") == 0 and shell.count("git add") == 0 and shell.count("git push") == 0
    assert _git(root, "tag", "-l") == "" and " M pyproject.toml" in _git(root, "status", "--porcelain")


# --------------------------------------------------------- release-finish

def _bumped(root: Path, new: str = "0.1.1.dev1") -> None:
    _bump_writer(root, new)([])


def test_release_finish_commits_and_tags_only_a_completed_upload(tmp_path: Path):
    root = _system_repo(tmp_path)
    shell = FakeShell([("bump-my-version show current_version", R.Done(0, "0.1.0\n"))])
    with pytest.raises(R.Refused, match="already committed"):
        _family(root, shell).finish("test")
    _bumped(root)
    answers = [("bump-my-version show current_version", R.Done(0, "0.1.1.dev1\n"))]
    (root / "stray").write_text("x\n")
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell(answers)).finish("test")
    assert "bump to 0.1.1.dev1 and nothing else" in e.value.message and "?? stray" in e.value.message
    (root / "stray").unlink()
    shell = FakeShell([*answers, ("publish-target-ready", R.Done(1))])
    with pytest.raises(R.Refused, match="not every project holds 0.1.1.dev1 on testpypi"):
        _family(root, shell).finish("test")
    assert "--all-held" in shell.texts()[shell.first("publish-target-ready")]
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell([*answers, ("publish-target-ready", R.Done(75))])).finish("test")
    assert e.value.code == 75 and "cannot be asked now" in e.value.message
    _git(root, "tag", "v0.1.1.dev1")
    with pytest.raises(R.Refused, match="already tagged here"):
        _family(root, FakeShell(answers)).finish("test")
    _git(root, "tag", "-d", "v0.1.1.dev1")
    said: list[str] = []
    shell = FakeShell(answers)
    fam = _family(root, shell, said=said)
    assert fam.finish("test") == 0
    assert shell.first("uv sync --all-extras --check") < shell.first("publish-target-ready") < shell.first("git add")
    assert _git(root, "log", "-1", "--format=%s") == "release 0.1.1.dev1" and _git(root, "tag", "-l") == "v0.1.1.dev1"
    assert _git(root, "status", "--porcelain") == "" and R.changes_row("0.1.1.dev1", "2001-02-03") in (root / "docs" / "CHANGES.md").read_text()
    assert said[-1] == R.FINISHED.format(version="0.1.1.dev1", name="testpypi", pushed=fam.closing_line("main"),
                                         branch="develop")
    _git(root, "checkout", "-q", "main")
    with pytest.raises(R.Refused, match="already committed"):
        _family(root, FakeShell(answers)).finish("test")


def test_release_finish_on_pypi_needs_the_live_configuration_for_the_evidence(tmp_path: Path):
    root = _system_repo(tmp_path)
    _bumped(root, "0.1.1")
    answers = [("bump-my-version show current_version", R.Done(0, "0.1.1\n"))]
    with pytest.raises(R.Refused, match="no live configuration"):
        _family(root, FakeShell(answers), env={"PYPI_TOKEN": "p"}).finish("pypi")
    sibling = _sibling_repo(tmp_path, evidence=False)                      # the evidence may already be committed
    assert _family(root, FakeShell(answers), sibling, env={"PYPI_TOKEN": "p"}).finish("pypi") == 0
    assert _git(root, "tag", "-l") == "v0.1.1"


@pytest.mark.parametrize(("branch", "ending"), [("main", ENDING_MAIN), ("release/0.1", ENDING_MAINT)])
def test_release_finish_ends_as_the_release_does(tmp_path: Path, branch: str, ending: list[list[str]]):
    """After its commit and tag: the same pushes, develop's fast-forward (from main) and the resync."""
    root = _system_repo(tmp_path, branch=branch)
    _bumped(root)
    answers = [("bump-my-version show current_version", R.Done(0, "0.1.1.dev1\n"))]
    shell = FakeShell(answers)
    said: list[str] = []
    fam = _family(root, shell, said=said)
    assert fam.finish("test") == 0
    assert _moves(shell) == ending and shell.first("git tag -a") < shell.first("git push")
    assert shell.texts()[-1] == " ".join(SYNC)
    assert _git(_remote(root), "rev-parse", branch) == _git(root, "rev-parse", branch) and \
        _git(_remote(root), "tag", "-l") == "v0.1.1.dev1"
    ends = "develop" if branch == "main" else branch
    assert _head(root) == ends
    assert said[-1] == R.FINISHED.format(version="0.1.1.dev1", name="testpypi", pushed=fam.closing_line(branch),
                                         branch=ends)
    # a checkout with no remote is refused before the commit
    plain = _system_repo(tmp_path / "plain", remote=False)
    _bumped(plain)
    with pytest.raises(R.Refused) as e:
        _family(plain, FakeShell(answers)).finish("test")
    assert e.value.message == f"release-finish: {R.NO_REMOTE.format(remote='origin')}"
    assert _git(plain, "tag", "-l") == "" and " M pyproject.toml" in _git(plain, "status", "--porcelain")


# ------------------------------------------------------------ release-take

TAKE_TREE = ("just --summary", R.Done(0, "init build test take record\n"))


def _take_world(tmp_path: Path, *answers):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    sibling = _sibling_repo(tmp_path)
    shell = FakeShell([*answers, TAKE_TREE, *_answers(root)])
    said: list[str] = []
    return root, sibling, shell, said, _family(root, shell, sibling, said=said)


@pytest.mark.parametrize("words", [(), ("main",)])
def test_release_take_releases_then_takes_the_version_it_read_back_in_the_live_configuration(tmp_path: Path,
                                                                                             words: tuple[str, ...]):
    root, sibling, shell, said, fam = _take_world(tmp_path)
    assert fam.release_take("patch", "test", *words) == 0
    take = ["just", "take", "0.1.1.dev1", *words]
    at = shell.calls.index(take)
    assert shell.cwds[at] == sibling and at == len(shell.calls) - 1                 # the last act, in the configuration
    last_sync = max(i for i, t in enumerate(shell.texts()) if t == " ".join(SYNC))
    assert shell.first("git push origin develop") < last_sync < at                  # after the release's whole ending
    assert shell.first("just --summary") < shell.first("git fetch")                  # the configuration asked first
    reads = [i for i, t in enumerate(shell.texts()) if "show current_version" in t]
    assert reads[-1] > shell.first("git tag -a")                                     # read back after the cut
    main = R.TAKEN_MAIN if words else ""
    assert said[-1] == "release-take: " + R.TAKEN.format(version="0.1.1.dev1", root=sibling, main=main)
    assert _git(root, "tag", "-l") == "v0.1.1.dev1"


def test_a_release_that_refuses_or_fails_runs_no_take(tmp_path: Path):
    root, _, shell, _, fam = _take_world(tmp_path / "a")
    (root / "stray").write_text("x\n")
    with pytest.raises(R.Refused, match="must be clean"):
        fam.release_take("patch", "test")
    assert shell.count("just take") == 0
    _, _, shell, _, fam = _take_world(tmp_path / "b", ("just test", R.Done(3)))
    with pytest.raises(R.Refused) as e:
        fam.release_take("patch", "test")
    assert e.value.code == 3 and shell.count("just take") == 0


def test_a_take_that_stops_says_the_release_is_done_and_how_to_finish(tmp_path: Path):
    root, sibling, shell, _, fam = _take_world(tmp_path, ("just take", R.Done(1)))
    with pytest.raises(R.Refused) as e:
        fam.release_take("patch", "test", "main")
    assert e.value.code == 1 and e.value.message == "release-take: " + R.TAKE_STOPPED.format(
        version="0.1.1.dev1", root=sibling, rc=1, command="just take 0.1.1.dev1 main")
    assert _git(_remote(root), "tag", "-l") == "v0.1.1.dev1"                         # the release itself went through


def test_the_dry_release_take_is_the_dry_release_then_the_take_it_would_run(tmp_path: Path):
    root, sibling, shell, said, fam = _take_world(tmp_path)
    refs, files = _refs(root), _files(root)
    assert fam.release_take("patch", "test", "yes", "main") == 0
    assert _dry_plan(said) in said and said[-1] == "release-take: " + R.WOULD.format(
        command=f"cd {sibling} && just take 0.1.1.dev1 main")
    assert shell.count("just take") == 0 and shell.count("bump-my-version bump") == 0 and _moves(shell) == []
    assert _refs(root) == refs and _files(root) == files


def test_release_take_refuses_a_word_or_a_configuration_it_cannot_take_in_before_anything(tmp_path: Path):
    _, _, shell, _, fam = _take_world(tmp_path / "a")
    with pytest.raises(R.Refused) as e:
        fam.release_take("patch", "test", "mian")
    assert e.value.code == 2 and e.value.message == "release-take: " + R.NOT_A_TAKE_WORD.format(word="mian")
    root, sibling, shell, _, fam = _take_world(tmp_path / "b", ("just --summary", R.Done(0, "init build\n")))
    with pytest.raises(R.Refused) as e:
        fam.release_take("patch", "test")
    assert e.value.message.startswith("release-take: no live configuration to take")
    assert shell.count("git fetch") == 0 and shell.count("publish-target-ready") == 0
    unconfigured = _family(root, FakeShell([TAKE_TREE, *_answers(root)]), tmp_path / "nowhere")
    with pytest.raises(R.Refused, match="nothing was changed"):
        unconfigured.release_take("patch", "test")


# ---------------------------------------------------------------- publish

def test_publish_asks_the_index_cleans_builds_and_uploads_one_project_at_a_time(tmp_path: Path):
    root = _system_repo(tmp_path)
    (root / "dist").mkdir()
    (root / "dist" / "old.whl").write_text("")
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell(_answers(root)), env={}).publish("test")
    assert e.value.code == 2 and "neither UV_PUBLISH_TOKEN nor TEST_PYPI_TOKEN" in e.value.message
    assert "never in this file" in e.value.message
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell(_answers(root, ready=75))).publish("test")
    assert e.value.code == 75 and "nothing was uploaded" in e.value.message and (root / "dist").is_dir()
    shell = FakeShell(_answers(root))
    said: list[str] = []
    env = {"PYPI_TOKEN": "p", "UV_PUBLISH_TOKEN": ""}
    assert _family(root, shell, env=env, said=said).publish("pypi", summary=tmp_path / "s") == 0
    t = shell.texts()
    probe = t[shell.first("publish-target-ready")]
    assert probe.endswith(" pypi --version 0.1.0 --quiet") and "--refuse-held" not in probe
    assert shell.first("publish-target-ready") < shell.first("just build") < shell.first("publish-dist")
    assert not (root / "dist").exists()                                     # cleaned before the build
    assert t[-1].endswith(f" pypi --version 0.1.0 --token-var PYPI_TOKEN --summary {tmp_path / 's'}")
    assert env["UV_PUBLISH_TOKEN"] == "p"
    assert said == [R.PUBLISHED.format(version="0.1.0", name="pypi", packages=1)]
    assert _family(root, FakeShell(_answers(root, upload=75))).publish("test") == 75


# ------------------------------------------------------------------ main

def test_main_runs_the_family_from_the_working_directory_and_prints_a_refusal(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("CSIS_CONFIG_ROOT", raising=False)
    root = _system_repo(tmp_path / "f", branch="feature/x")
    monkeypatch.chdir(root)
    assert R.main(["release", "patch", "test", "yes"]) == 1
    assert "this checkout is on 'feature/x'" in capsys.readouterr().out
    behind = _system_repo(tmp_path / "b", develop_ahead=True)
    assert R.main(["release", "patch", "test", "yes", "--root", str(behind)]) == 1
    assert "--ff-only develop" in capsys.readouterr().out
    # past the guard on its own branch: whatever stops it next (no project here), it is not the branch
    assert R.main(["release", "patch", "test", "yes", "--release-branch", "feature/x"]) != 0
    assert "nothing was changed" not in capsys.readouterr().out
    with pytest.raises(SystemExit):
        R.main(["release"])
    with pytest.raises(SystemExit):
        R.main(["push"])


def _plan(*args: str) -> list[str]:
    """The commands `just -n` says the recipe would run, one per line."""
    r = subprocess.run(["just", "-n", *args], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return [line for line in r.stderr.splitlines() if line.strip()]


def test_the_recipes_are_wrappers_over_the_script():
    """`just --summary` names the three recipes, and each one's plan is the
    one command that runs the script with the recipe's arguments; `release`
    and `release-finish` pass the release branch and the configuration root,
    the probes the root alone."""
    if not os.access(SCRIPT, os.X_OK):
        pytest.fail("scripts/release.py is run as a script")
    summary = subprocess.run(["just", "--summary"], cwd=REPO, capture_output=True, text=True).stdout.split()
    assert {"release", "release-finish", "release-take", "publish"} <= set(summary)
    script = f'python "{SCRIPT}" '
    for args, call in ((("release", "patch", "test", "yes"),
                        'release "patch" "test" "yes" --release-branch "main" --config-root '),
                       (("release-finish", "pypi"), 'release-finish "pypi" --release-branch "main" --config-root '),
                       (("publish", "test"), 'publish "test"'),
                       (("release-take", "patch", "pypi", "main"),
                        'release-take "patch" "pypi" main --release-branch "main" --config-root '),
                       (("_release-probes", "pypi", "release-finish"),
                        'probes "pypi" "release-finish" --config-root ')):
        plan = _plan(*args)
        assert len(plan) == 1, (args, plan)                                    # a wrapper, not a program
        assert plan[0].startswith("uv run --no-sync --project ") and script + call in plan[0], (args, plan)
