# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The release family is scripts/release.py, run by three one-line recipes.

Against a fake shell that answers every command the family runs (uv,
bump-my-version, just, the probe scripts) and lets git through to a
temporary repository whose ``origin`` is a scratch bare repository (so the
pushes are real and local): the probes in their order and their one-line
verdicts; the dry form that prints every move and push it would make and
touches no ref and no file; the real form's order (the index, the move to
main from develop, the resync, the lighter check, the index again, the
bump, the lock, the commit, the tag, the pushes, develop's fast-forward,
the resync) and its closing line, from develop, main and a maintenance
branch; the return to the starting branch on a refusal before the bump; a
failed push named with what is left; ``release-take``'s release, its wait
for TestPyPI to list the version, then the take in the live configuration,
and what it says when any of them stops; the release's row in
docs/CHANGES.md; the fetch probe, which refuses before anything changes
when origin holds commits a branch the ending pushes lacks, and the line
after it naming the local annotated tags origin lacks, which stay behind
(never a refusal); and the one reader of the sibling repository's working
tree.

Specification 013 (TestPyPI until 1.0): ``pypi`` is refused, naming the
standing decision, before anything changes; the release never uploads (the
tag's push publishes); ``--full`` runs the full proof and records it in its
tag's message; and the advisory says, before anything changes, when the
paths changed since the newest fully proven release probably need it.
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
        self.envs: list[dict[str, str] | None] = []

    def __call__(self, cmd: list[str], *, cwd: Path | None = None, capture: bool = True, env=None):
        self.calls.append(list(cmd))
        self.cwds.append(cwd)
        self.envs.append(dict(env) if env is not None else None)
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


def _family(root: Path, shell: FakeShell, sibling: Path | None = None, *, env: dict[str, str] | None = None,
            said: list[str] | None = None, slept: list[float] | None = None):
    tree = R.read_sibling(sibling or root / "no-config", run=shell)
    clock = [0.0]

    def sleep(seconds: float) -> None:                       # the wait's own clock, moved by its sleeps alone
        clock[0] += seconds
        if slept is not None:
            slept.append(seconds)
    return R.Family(root=root, sibling=tree, run=shell, env=env if env is not None else {},
                    say=(said if said is not None else []).append, today=lambda: "2001-02-03",
                    sleep=sleep, clock=lambda: clock[0])


def _current(root: Path) -> Callable[[list[str]], object]:
    """`bump-my-version show current_version`: the version line of the tree as it is now."""
    def show(cmd: list[str]):
        m = re.search(r'^version = "(.*)"$', (root / "pyproject.toml").read_text(), re.M)
        assert m
        return R.Done(0, m.group(1) + "\n")
    return show


def _answers(root: Path, *, new: str = "0.1.1.dev1", ready: int = 0):
    return [
        ("bump-my-version show current_version", _current(root)),
        ("bump-my-version show --increment", R.Done(0, f"{new}\n")),
        ("bump-my-version bump", _bump_writer(root, new)),
        ("publish-target-ready", R.Done(ready)),
    ]


#: what a release never runs: it uploads nothing and holds no token (the tag's push publishes)
NEVER_UPLOADS = ("publish-dist", "uv publish", "just build", "just publish")


SYNC = ["uv", "sync", "--all-extras", "--no-extra", "gcloud", "--no-extra", "okta", "--no-extra", "all"]
MOVE = [["git", "checkout", "main"], ["git", "merge", "--ff-only", "develop"]]
ENDING_MAIN = [["git", "push", "origin", "main", "v0.1.1.dev1"], ["git", "checkout", "develop"],
               ["git", "merge", "--ff-only", "main"], ["git", "push", "origin", "develop"], SYNC]
ENDING_MAINT = [["git", "push", "origin", "release/0.1", "v0.1.1.dev1"], SYNC]
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


def test_a_light_release_asks_the_venv_the_own_versions_testpypi_and_the_daemon_alone(tmp_path: Path):
    """The lighter check runs the install check, which needs the daemon,
    and nothing of the live configuration; the families released elsewhere
    are asked of TestPyPI."""
    root = _system_repo(tmp_path)
    shell = FakeShell([(OWN, R.Done(0, OWN_LINE + "\n"))])
    said: list[str] = []
    _family(root, shell, said=said).probes()
    assert said == [f"release: {R.VENV_OK}", OWN_LINE, "release: docker answers"]
    assert shell.count("docker info") == 1 and shell.count("just preflight") == 0
    assert shell.count("session-minutes-left") == 0
    assert shell.first("uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all --check") < shell.first(OWN)
    assert shell.texts()[shell.first(OWN)].endswith(f"scripts/{OWN} test --root {root}")
    assert shell.count(ELSEWHERE) == 1 and shell.count("with-released-families --check pypi") == 0


@pytest.mark.parametrize(("rc", "code", "message"), [(1, 1, "UNBUMPED"), (2, 2, "UNASKED"), (127, 2, "UNASKED")])
def test_an_own_version_package_the_index_would_refuse_is_refused_before_the_gate(tmp_path: Path, rc: int, code: int,
                                                                                  message: str):
    """Exit 1 of scripts/own-versions-current is a package changed under a version the index holds; any
    other failure is "could not ask". Either way the release stops at the probes, light or full:
    no gate, no bump, no tag, the tree as it was."""
    for form, words in (("light", ()), ("full", ("--full",))):
        root = _system_repo(tmp_path / form)
        sibling = _sibling_repo(tmp_path / form)
        before = {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
        shell = FakeShell([(OWN, R.Done(rc, OWN_LINE + "\n", "uv: stderr\n")), *_answers(root)])
        said: list[str] = []
        with pytest.raises(R.Refused) as e:
            _family(root, shell, sibling, said=said).release("patch", *words)
        assert e.value.code == code and e.value.message == f"release: {getattr(R, message)}"
        assert OWN_LINE in said and ("uv: stderr" in said) == (rc != 1)
        for never in ("just test", "just full-test", "docker info", "bump-my-version bump", "uv lock", *NEVER_UPLOADS):
            assert shell.count(never) == 0, never
        assert {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts} == before
        assert _git(root, "status", "--porcelain") == "" and _git(root, "tag", "-l") == ""


ELSEWHERE = "with-released-families --check test"


@pytest.mark.parametrize(("rc", "code", "message"), [(1, 1, "ELSEWHERE_UNMET"), (2, 2, "ELSEWHERE_UNASKED")])
def test_a_family_released_elsewhere_that_testpypi_lacks_is_refused_before_the_gate(tmp_path: Path, rc: int,
                                                                                    code: int, message: str):
    """spec 005, spec 013: the umbrella names the families released elsewhere by a range; a release whose
    range TestPyPI cannot meet (exit 1), or whose index could not be asked (any other), stops at the
    probes, after the own versions and before the surfaces, light or full; TestPyPI is the index asked."""
    for form, words in (("light", ()), ("full", ("--full",))):
        root = _system_repo(tmp_path / form)
        sibling = _sibling_repo(tmp_path / form)
        line = "with-released-families: cs-image-system-x>=0.2,<0.3 -- NO release on the test index"
        shell = FakeShell([(ELSEWHERE, R.Done(rc, line + "\n")), *_answers(root)])
        said: list[str] = []
        with pytest.raises(R.Refused) as e:
            _family(root, shell, sibling, said=said).release("patch", *words)
        assert e.value.code == code and e.value.message == f"release: {getattr(R, message)}"
        assert line in said and shell.first(OWN) < shell.first(ELSEWHERE)
        for never in ("just surface-check", "just test", "docker info", "bump-my-version bump", *NEVER_UPLOADS):
            assert shell.count(never) == 0, never
        assert _git(root, "status", "--porcelain") == "" and _git(root, "tag", "-l") == ""


@pytest.mark.parametrize("full", [False, True])
def test_a_stale_venv_is_refused_light_or_full_in_one_line(tmp_path: Path, full: bool):
    root = _system_repo(tmp_path)
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell([("uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all --check", R.Done(1))])).probes(full)
    assert e.value.code == 1 and "behind" in e.value.message and "just init" in e.value.message


def test_a_full_proof_without_docker_is_refused_first(tmp_path: Path):
    root = _system_repo(tmp_path)
    said: list[str] = []
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell([("docker info", R.Done(1))]), said=said).probes(True)
    assert said[0] == f"release: {R.VENV_OK}" and said[-1] != "release: docker answers"
    assert "docker" in e.value.message and "full-test" in e.value.message and "nothing was changed" in e.value.message


def test_a_full_proof_without_a_live_configuration_or_a_session_is_refused_by_name(tmp_path: Path):
    root = _system_repo(tmp_path)
    said: list[str] = []
    with pytest.raises(R.Refused, match="no live configuration"):
        _family(root, FakeShell(), said=said).probes(True)
    assert said[-1] == "release: docker answers"
    sibling = _sibling_repo(tmp_path)
    with pytest.raises(R.Refused, match="absent or expired"):
        _family(root, FakeShell([("just preflight", R.Done(2))]), sibling).probes(True)


def test_the_session_line_says_the_minutes_left_and_refuses_only_a_lapsed_token(tmp_path: Path):
    """Three branches of the one line (lapsed, under an hour, enough); the operator's decision is to
    SAY the minutes. A token already lapsed is a fact, not a margin -- preflight judges it too -- so that
    branch alone refuses. The full proof alone asks them."""
    root = _system_repo(tmp_path)
    sibling = _sibling_repo(tmp_path)

    def line(minutes: str, rc: int = 0) -> str:
        said: list[str] = []
        shell = FakeShell([("session-minutes-left", R.Done(rc, minutes))])
        _family(root, shell, sibling, said=said).probes(True)
        assert shell.texts()[-1].endswith(f"session-minutes-left {sibling}")
        return said[-1]

    assert line("120\n").endswith("the soonest-expiring session has 120 minutes left")
    assert "halfway" in line("30\n") and "30 minutes left" in line("30\n")
    assert line("", rc=1) == f"release: {R.SESSIONS_OK}"
    with pytest.raises(R.Refused, match="lapsed 5 minutes ago"):
        line("-5\n")


# ------------------------------------------------------------- the guards

def test_the_branch_guard_names_the_checkout_and_the_fast_forward(tmp_path: Path):
    feature = _system_repo(tmp_path / "f", branch="feature/x")
    with pytest.raises(R.Refused) as e:
        _family(feature, FakeShell()).branch_guard("release")
    assert "feature/x" in e.value.message and "main alone" in e.value.message and "nothing was changed" in e.value.message
    behind = _system_repo(tmp_path / "b", develop_ahead=True)
    with pytest.raises(R.Refused, match="--ff-only develop"):
        _family(behind, FakeShell()).branch_guard("release")
    said: list[str] = []
    maint = _system_repo(tmp_path / "m", branch="release/0.1", develop_ahead=True)
    assert _family(maint, FakeShell(), said=said).branch_guard("release") == "release/0.1"
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


def test_the_index_and_the_tag_are_asked_before_anything_changes_and_no_token_is(tmp_path: Path):
    """The index is asked (it never takes a version twice) and the tag; no token is asked for, since
    the release uploads nothing: the tag's push publishes, by trusted publishing."""
    root = _system_repo(tmp_path)
    for ready, needle, code in ((75, "cannot take an upload now", 75), (1, "never re-cut", 1), (3, "could not run", 2)):
        shell = FakeShell(_answers(root, ready=ready))
        with pytest.raises(R.Refused) as e:
            _family(root, shell).release("patch", "yes")
        assert needle in e.value.message and e.value.code == code
        assert shell.count("bump-my-version bump") == 0 and shell.count("uv sync") == 0
    assert _family(root, FakeShell(_answers(root)), env={}).release("patch", "yes") == 0      # no token anywhere
    _git(root, "tag", "v0.1.1.dev1")
    with pytest.raises(R.Refused, match="already tagged here"):
        _family(root, FakeShell(_answers(root))).release("patch", "yes")
    shell = FakeShell(_answers(root))
    with pytest.raises(R.Refused) as e:
        _family(root, shell).release("patch", "gitlab", "yes")
    assert e.value.code == 2 and "'gitlab'" in e.value.message and "--full" in e.value.message
    assert shell.calls == []                                                 # refused before anything is asked


@pytest.mark.parametrize(("command", "words"), [("release", ("pypi",)), ("release", ("--full", "pypi", "yes")),
                                                ("release_take", ("pypi", "main")), ("probes", ("pypi",))])
def test_pypi_is_refused_naming_the_standing_decision_with_nothing_changed(tmp_path: Path, command: str,
                                                                           words: tuple[str, ...]):
    """Specification 013, FR-001: until the operator declares 1.0 a release goes to TestPyPI alone; one
    asked for PyPI refuses, naming the standing decision, before it asks or changes anything."""
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    sibling = _sibling_repo(tmp_path)
    refs, remote, files = _refs(root), _refs(_remote(root)), _files(root)
    shell = FakeShell([TAKE_TREE, *_answers(root)])
    family = _family(root, shell, sibling)
    read = len(shell.calls)                                                  # the sibling's reading, at construction
    with pytest.raises(R.Refused) as e:
        if command == "probes":
            family.probes(*words)
        else:
            getattr(family, command)("patch", *words)
    assert e.value.code == 2 and e.value.message.endswith(R.STANDING) and "TestPyPI until 1.0" in R.STANDING
    assert shell.calls[read:] == []
    assert _head(root) == "develop" and _refs(root) == refs and _refs(_remote(root)) == remote and _files(root) == files
    assert _git(sibling, "status", "--porcelain") == "?? meta-state/mod-tests.yaml"           # the sibling as it was


# ----------------------------------------------------------- the dry form

def test_the_dry_form_prints_what_it_would_do_and_touches_nothing(tmp_path: Path):
    root = _system_repo(tmp_path)
    before = {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
    shell = FakeShell([(OWN, R.Done(0, OWN_LINE + "\n")), *_answers(root)])
    said: list[str] = []
    env: dict[str, str] = {}
    assert _family(root, shell, env=env, said=said).release("patch", "yes") == 0
    # the dry form answers "would this release go through": the own-version probe runs in it too
    assert shell.count(OWN) == 1 and shell.first("uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all --check") < shell.first(OWN)
    plan = _dry_plan(said)
    assert said.index(OWN_LINE) < said.index(plan)
    assert plan.startswith("release: dry") and "on main, 0.1.0 would become 0.1.1.dev1:" in plan
    for needle in ("the probes above passed", "just test", "just test-quickstart", "the index again",
                   "bump-my-version bump patch", "uv lock", "commit 'release 0.1.1.dev1'", "docs/CHANGES.md",
                   "tag v0.1.1.dev1", "TestPyPI"):
        assert needle in plan, needle
    for never in ("just publish", "just full-test", "token"):
        assert never not in plan, never
    assert _would_lines(said) == _would([SYNC, *ENDING_MAIN]) and _moves(shell) == []
    # the order: the index, then the tag, then the venv probe; nothing after the dry line
    assert shell.first("publish-target-ready") < shell.first("uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all --check")
    assert "--refuse-held" in shell.texts()[shell.first("publish-target-ready")]
    for never in ("just test", "bump-my-version bump", "uv lock", *NEVER_UPLOADS):
        assert shell.count(never) == 0, never
    assert env == {}                                                         # no token is looked for or set
    assert {p: p.read_text() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts} == before
    assert _git(root, "status", "--porcelain") == "" and _git(root, "tag", "-l") == ""


def test_the_dry_form_of_a_full_release_names_full_test_and_its_record(tmp_path: Path):
    root = _system_repo(tmp_path)
    sibling = _sibling_repo(tmp_path)
    said: list[str] = []
    fam = _family(root, FakeShell(_answers(root)), sibling, said=said)
    assert fam.release("stage", "--full", "yes") == 0
    plan = _dry_plan(said)
    assert "just full-test, the index again" in plan and R.FULLY_PROVEN in plan and "just publish" not in plan


# ---------------------------------------------------------- the real form

def test_the_real_form_runs_the_lighter_check_bumps_commits_tags_and_uploads_nothing(tmp_path: Path):
    """Specification 013: the default gate is the lighter check (the acceptance tests and the install
    check, after the probes); the release commits, tags and pushes, and the tag's push publishes:
    nothing is built or uploaded here and no token is asked for."""
    root = _system_repo(tmp_path)
    shell = FakeShell(_answers(root))
    said: list[str] = []
    fam = _family(root, shell, said=said)
    assert fam.release("patch") == 0
    t = shell.texts()
    order = [shell.first(n) for n in ("publish-target-ready", "uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all --check", OWN, ELSEWHERE,
                                      "just surface-check", "docker info", "just test", "just test-quickstart",
                                      "bump-my-version bump patch", "uv lock", "git tag -a", "git push")]
    assert order == sorted(order), t                                       # the install check before anything moves
    asks = [i for i, x in enumerate(t) if "publish-target-ready" in x]
    assert len(asks) == 2 and all("--refuse-held" in t[i] for i in asks)  # before anything, and again after the gate
    assert t.count("just test") == 1 and t.count("just test-quickstart") == 1
    assert shell.first("just test") < asks[1] < shell.first("bump-my-version bump")         # the index again after the bar
    for never in ("just full-test", "just preflight", "session-minutes-left", *NEVER_UPLOADS):
        assert shell.count(never) == 0, never
    assert _git(root, "log", "-1", "--format=%s") == "release 0.1.1.dev1" and _git(root, "tag", "-l") == "v0.1.1.dev1"
    assert R.FULLY_PROVEN not in _git(root, "tag", "-l", "--format=%(contents)", "v0.1.1.dev1")   # not fully proven
    assert _git(root, "status", "--porcelain") == ""
    committed = _git(root, "show", "--stat", "--format=", "HEAD")
    for name in ("pyproject.toml", "packages/one/pyproject.toml", "packages/two/pyproject.toml", "uv.lock", "docs/CHANGES.md"):
        assert name in committed, name
    page = (root / "docs" / "CHANGES.md").read_text().splitlines()
    assert page[4] == R.changes_row("0.1.1.dev1", "2001-02-03") and "| not yet |" not in "\n".join(page)
    pushed = fam.closing_line("main", "0.1.1.dev1")
    assert pushed == "; ".join(" ".join(c) for c in ENDING_MAIN[:-1])
    assert said[-1] == R.RELEASED.format(version="0.1.1.dev1", pushed=pushed, branch="develop")
    assert "trusted publishing" in R.RELEASED and "TestPyPI" in R.RELEASED                  # the push that publishes


def test_a_full_release_runs_full_test_the_session_probes_and_the_evidence_and_records_it(tmp_path: Path):
    """`--full` is what a PyPI release ran, against TestPyPI: the session probes, `just full-test`, the
    modification-test evidence (present, the live checkout otherwise clean, committed there), and the
    annotated tag's message carries the line the advisory measures from."""
    root = _system_repo(tmp_path)
    sibling = _sibling_repo(tmp_path, evidence=False)
    shell = FakeShell(_answers(root))
    with pytest.raises(R.Refused, match="no modification-test evidence"):
        _family(root, shell, sibling).release("stage", "--full")
    assert shell.count("just full-test") == 1 and shell.count("just preflight") == 1
    assert shell.count("session-minutes-left") == 1 and shell.texts().count("just test") == 0
    assert shell.count("just test-quickstart") == 0 and shell.count("bump-my-version bump") == 0
    (sibling / "meta-state" / "mod-tests.yaml").write_text("results: {}\n")
    (sibling / "cfg" / "other.yml").write_text("x\n")
    with pytest.raises(R.Refused, match="clean apart from its mod-test evidence"):
        _family(root, FakeShell(_answers(root)), sibling).release("stage", "--full")
    (sibling / "cfg" / "other.yml").unlink()
    said: list[str] = []
    shell = FakeShell(_answers(root, new="0.1.1"))
    assert _family(root, shell, sibling, said=said).release("stage", "--full") == 0
    assert _git(sibling, "log", "-1", "--format=%s") == "release 0.1.1: modification-test evidence"
    assert _git(root, "tag", "-l") == "v0.1.1"
    assert R.FULLY_PROVEN in _git(root, "tag", "-l", "--format=%(contents)", "v0.1.1").splitlines()
    assert R.FULLY_PROVEN == "fully proven: full-test"
    for never in NEVER_UPLOADS:
        assert shell.count(never) == 0, never


def test_a_dirty_tree_is_refused_before_the_bar(tmp_path: Path):
    root = _system_repo(tmp_path)
    (root / "stray").write_text("x\n")
    shell = FakeShell(_answers(root))
    with pytest.raises(R.Refused) as e:
        _family(root, shell).release("patch")
    assert "must be clean" in e.value.message and "?? stray" in e.value.message and "discard" in e.value.message
    assert shell.count("just test") == 0


def test_a_failed_bar_stops_the_release_with_its_own_exit_code(tmp_path: Path):
    root = _system_repo(tmp_path)
    shell = FakeShell([("just test", R.Done(3)), *_answers(root)])
    with pytest.raises(R.Refused) as e:
        _family(root, shell).release("patch")
    assert e.value.code == 3 and e.value.message == "" and shell.count("publish-target-ready") == 1


# --------------------------------------------------------- the advisory

def _proven(root: Path, tag: str) -> None:
    """A release tag at HEAD whose annotated message records a full proof, as `--full` writes it."""
    _git(root, "tag", "-a", tag, "-m", f"release {tag[1:]}", "-m", R.FULLY_PROVEN)


def _change(root: Path, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(path.read_text() + "x\n" if path.exists() else "x\n")
    _git(root, "add", rel)
    _git(root, "commit", "-q", "-m", f"change {rel}")
    _git(root, "push", "-q", "origin", "HEAD")


def _advice(said: list[str]) -> list[str]:
    head = "release: " + R.ADVISE.partition("{")[0]
    return [line for line in said if line.startswith(head)]


def test_the_advisory_matches_its_one_list():
    """The one constant: the runtimes' and identity plugins' sources, the release and take tooling, the
    starters' workflows, the contract and the SDK; a path elsewhere is not in it."""
    changed = ["packages/aws-runtime-plugin/src/x.py", "packages/posix-identity-plugin/pyproject.toml",
               "packages/docker-plugin/x.py", "scripts/release.py", "scripts/publish-dist", "scripts/release-watch",
               "docs/examples/_skeleton/Justfile", "docs/examples/complete/.github/workflows/ci.yml",
               "packages/contract/x.py", "packages/base/x.py", "packages/hashicorp-utils/x.py",
               "packages/tofu-roots/x.tf"]
    assert R.full_proof_paths(changed) == changed
    for elsewhere in ("docs/OPERATIONS.md", "packages/engine/x.py", "packages/packer-plugin/x.py", "scripts/isolated-run",
                      "docs/examples/complete/README.md", "tests/test_x.py", "packages/okta-opa-plugin/x.py"):
        assert R.full_proof_paths([elsewhere]) == [], elsewhere
    assert not any("okta" in entry for entry in R.FULL_PROOF_PATHS)          # spec 008 took it to its own repository


@pytest.mark.parametrize("dry", ["yes", "no"])
def test_the_advisory_names_a_listed_path_changed_since_the_newest_fully_proven_tag_and_never_refuses(
        tmp_path: Path, dry: str):
    """Measured from the newest tag whose message records a full proof, not from the newest tag; said
    before anything changes; the release goes on."""
    root = _system_repo(tmp_path)
    _proven(root, "v0.0.9")
    _change(root, "packages/contract/x.py")
    _git(root, "tag", "-a", "v0.1.0", "-m", "release 0.1.0")                 # newer, and not fully proven
    _git(root, "branch", "-f", "develop", "main")
    _git(root, "push", "-q", "origin", "develop")
    said: list[str] = []
    shell = FakeShell(_answers(root))
    assert _family(root, shell, said=said).release("patch", dry) == 0
    advice = _advice(said)
    assert len(advice) == 1 and "packages/contract/x.py" in advice[0] and "v0.0.9" in advice[0], said
    assert advice[0].endswith("; run with --full")
    assert said.index(advice[0]) < next(i for i, line in enumerate(said) if line.startswith("release: dry") or
                                        line == f"release: {R.VENV_OK}")    # before the move, the resync and the probes


def test_the_advisory_is_silent_when_nothing_listed_changed_and_under_full(tmp_path: Path):
    root = _system_repo(tmp_path)
    _proven(root, "v0.0.9")
    _change(root, "docs/OPERATIONS.md")
    _git(root, "branch", "-f", "develop", "main")
    _git(root, "push", "-q", "origin", "develop")
    said: list[str] = []
    assert _family(root, FakeShell(_answers(root)), said=said).release("patch", "yes") == 0
    assert _advice(said) == []
    _change(root, "scripts/release.py")
    _git(root, "branch", "-f", "develop", "main")
    _git(root, "push", "-q", "origin", "develop")
    said = []
    assert _family(root, FakeShell(_answers(root)), _sibling_repo(tmp_path), said=said).release("patch", "--full", "yes") == 0
    assert _advice(said) == []                                               # the full proof is what it would advise


def test_the_advisory_without_a_fully_proven_tag_measures_from_the_first_and_says_so(tmp_path: Path):
    root = _system_repo(tmp_path)
    said: list[str] = []
    assert _family(root, FakeShell(_answers(root)), said=said).release("patch", "yes") == 0
    assert len(_advice(said)) == 1 and R.NO_TAG in _advice(said)[0]          # no tag at all: no measure, so advised
    _git(root, "tag", "-a", "v0.0.1", "-m", "release 0.0.1")
    _change(root, "packages/base/x.py")
    _git(root, "branch", "-f", "develop", "main")
    _git(root, "push", "-q", "origin", "develop")
    said = []
    assert _family(root, FakeShell(_answers(root)), said=said).release("patch", "yes") == 0
    advice = _advice(said)
    assert len(advice) == 1 and "packages/base/x.py" in advice[0] and "v0.0.1" in advice[0]
    assert R.NEVER_PROVEN.partition("{")[0] in advice[0]


def test_release_take_into_an_applying_cycle_is_advised_a_full_proof(tmp_path: Path):
    """FR-002a: a take that pushes the reference's main starts an applying cycle there."""
    root, sibling, shell, said, fam = _take_world(tmp_path)
    _proven(root, "v0.0.9")
    assert fam.release_take("patch", "yes", "main") == 0
    advice = _advice(said)
    assert len(advice) == 1 and R.APPLYING in advice[0]
    said.clear()
    assert fam.release_take("patch", "yes") == 0 and _advice(said) == []


# ------------------------------------------------- the moves and the pushes

def test_from_develop_the_release_moves_to_main_cuts_pushes_and_comes_back(tmp_path: Path):
    """From develop: main checked out and fast-forwarded to develop, the venv synced before the probes,
    the release cut on main, main pushed with its tag, develop checked out, fast-forwarded and pushed,
    and the venv synced again as the last act. The remote is a scratch bare repository: the pushes are real."""
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    shell = FakeShell(_answers(root))
    said: list[str] = []
    fam = _family(root, shell, said=said)
    assert fam.release("patch") == 0
    assert _moves(shell) == [*MOVE, SYNC, *ENDING_MAIN]
    t = shell.texts()
    first_sync = t.index(" ".join(SYNC))
    assert t.index(" ".join(MOVE[1])) < first_sync < shell.first("uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all --check") < shell.first(OWN)
    assert shell.first("git tag -a") < t.index(" ".join(ENDING_MAIN[0])) and t[-1] == " ".join(SYNC)
    head = _git(root, "rev-parse", "HEAD")
    assert _head(root) == "develop" and _git(root, "log", "-1", "--format=%s") == "release 0.1.1.dev1"
    for repo in (root, _remote(root)):
        assert _git(repo, "rev-parse", "main") == head == _git(repo, "rev-parse", "develop"), repo
        assert _git(repo, "tag", "-l") == "v0.1.1.dev1", repo
    assert said[-1] == R.RELEASED.format(version="0.1.1.dev1",
                                         pushed=fam.closing_line("main", "0.1.1.dev1"), branch="develop")


def test_from_main_the_release_pushes_main_with_its_tag_and_brings_develop_up(tmp_path: Path):
    root = _system_repo(tmp_path)
    shell = FakeShell(_answers(root))
    assert _family(root, shell).release("patch") == 0
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
    assert fam.release("patch") == 0
    assert _moves(shell) == [SYNC, *ENDING_MAINT] and _head(root) == "release/0.1"
    assert [_git(repo, "rev-parse", "develop") for repo in (root, remote)] == develop
    assert _git(remote, "rev-parse", "release/0.1") == _git(root, "rev-parse", "HEAD")
    assert _git(remote, "tag", "-l") == "v0.1.1.dev1"
    assert said[-1] == R.RELEASED.format(version="0.1.1.dev1",
                                         pushed=fam.closing_line("release/0.1", "0.1.1.dev1"), branch="release/0.1")
    assert fam.closing_line("release/0.1", "0.1.1.dev1") == " ".join(ENDING_MAINT[0])


@pytest.mark.parametrize(("branch", "pushes"), [
    ("main", [ENDING_MAIN[0], ENDING_MAIN[3]]),
    ("release/0.1", [ENDING_MAINT[0]]),
])
def test_the_push_names_the_branch_and_the_releases_own_tag_and_no_other(tmp_path: Path, branch: str,
                                                                        pushes: list[list[str]]):
    """GitHub starts no run for tags when more than three are pushed at once, so the release's tag goes up
    by name beside its branch: three annotated tags here that origin lacks stay here, and the release's
    own tag is the one origin receives."""
    root = _system_repo(tmp_path, branch=branch)
    for stray in ("s1-before", "s1-after", "checkpoint"):
        _git(root, "tag", "-a", stray, "-m", stray)
    shell = FakeShell(_answers(root))
    assert _family(root, shell).release("patch") == 0
    sent = [c for c in shell.calls if c[:2] == ["git", "push"]]
    assert sent == pushes and sent[0] == ["git", "push", "origin", branch, "v0.1.1.dev1"]
    assert not any("--follow-tags" in c or "--tags" in c for c in sent)
    assert _git(_remote(root), "tag", "-l") == "v0.1.1.dev1"
    assert _git(root, "tag", "-l").split() == ["checkpoint", "s1-after", "s1-before", "v0.1.1.dev1"]


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
    ("the venv", ("uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all --check", R.Done(1)), 1, None),
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
        _family(root, shell).release("patch")
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
            _family(root, shell).release("patch", dry)
        assert e.value.message == f"release: {R.NO_FAST_FORWARD.format(cut='main')}" and e.value.code == 1, dry
        assert _moves(shell) == [] and _head(root) == "develop" and _refs(root) == refs, dry


@pytest.mark.parametrize(("ref", "at"), [("refs/heads/main", 0), ("refs/heads/develop", 3)])
def test_a_failed_push_names_itself_and_what_is_left_and_exits_non_zero(tmp_path: Path, ref: str, at: int):
    """The version is on the index and committed and tagged here; the failed push is named with the
    commands that are left, and nothing after it runs."""
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    _refuse_pushes_to(root, ref)
    shell = FakeShell(_answers(root))
    with pytest.raises(R.Refused) as e:
        _family(root, shell).release("patch")
    rest = ENDING_MAIN[at:]
    assert e.value.code != 0
    assert e.value.message == "release: " + R.ENDING_FAILED.format(
        version="0.1.1.dev1", failed=" ".join(rest[0]), rest=" && ".join(" ".join(c) for c in rest))
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
    assert _family(root, shell, said=said).release("patch", "yes") == 0
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
    shell = FakeShell([("uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all --check", R.Done(1)), *_answers(root)])
    assert _family(root, shell, said=said).release("patch", "yes") == 0
    assert f"release: {R.VENV_WILL_SYNC}" in said and f"release: {R.VENV_OK}" not in said
    assert _moves(shell) == [] and _head(root) == "develop"


def test_a_checkout_with_no_remote_is_refused_before_anything_changes(tmp_path: Path):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True, remote=False)
    refs = _refs(root)
    for dry in ("yes", "no"):
        shell = FakeShell(_answers(root))
        with pytest.raises(R.Refused) as e:
            _family(root, shell).release("patch", dry)
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
        _family(root, shell, said=said).release("patch", dry)
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
    assert _family(root, FakeShell(_answers(root)), said=said).release("patch") == 0
    assert f"release: {R.LEVEL_WITH_ORIGIN.format(remote='origin', branches='release/0.1')}" in said


def test_a_local_branch_ahead_of_origin_passes_and_is_pushed(tmp_path: Path):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    (root / "mine").write_text("not yet pushed\n")
    _git(root, "add", "mine")
    _git(root, "commit", "-q", "-m", "mine")
    said: list[str] = []
    assert _family(root, FakeShell(_answers(root)), said=said).release("patch") == 0
    assert f"release: {R.LEVEL_WITH_ORIGIN.format(remote='origin', branches='main or develop')}" in said
    assert _git(_remote(root), "rev-parse", "develop") == _git(root, "rev-parse", "HEAD")


def test_the_dry_form_fetches_and_says_origin_holds_nothing_the_pushes_lack(tmp_path: Path):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    said: list[str] = []
    shell = FakeShell(_answers(root))
    assert _family(root, shell, said=said).release("patch", "yes") == 0
    level = f"release: {R.LEVEL_WITH_ORIGIN.format(remote='origin', branches='main or develop')}"
    assert shell.count("git fetch -q origin") == 1 and said.index(level) < said.index(_dry_plan(said))
    _git(root, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    with pytest.raises(R.Refused) as e:
        _family(root, FakeShell(_answers(root))).release("patch", "yes")
    assert e.value.message == f"release: {R.NO_FETCH.format(remote='origin')}"


@pytest.mark.parametrize("form", ["dry", "real"])
def test_the_local_annotated_tags_origin_lacks_are_named_as_staying_behind(tmp_path: Path, form: str):
    """Informational: the ending pushes the release's own tag alone, so a local annotated tag origin lacks
    stays here, and the probe names it before the cut; a tag origin holds and a lightweight one are not named."""
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    for stray in ("s1-before", "checkpoint", "pushed"):
        _git(root, "tag", "-a", stray, "-m", stray)
    _git(root, "tag", "light")
    _git(root, "push", "-q", "origin", "pushed")
    said: list[str] = []
    shell = FakeShell(_answers(root))
    assert _family(root, shell, said=said).release("patch", "yes" if form == "dry" else "no") == 0
    who = "release"
    behind = f"{who}: {R.TAGS_BEHIND.format(remote='origin', version='0.1.1.dev1', tags='checkpoint, s1-before')}"
    level = next(line for line in said if line.startswith(f"{who}: ") and "(fetched)" in line)
    assert said.index(level) < said.index(behind) and shell.count("git ls-remote --tags origin") == 1
    if form == "dry":
        assert said.index(behind) < said.index(_dry_plan(said))
    assert sorted(_git(_remote(root), "tag", "-l").split()) == (["pushed"] if form == "dry" else ["pushed", "v0.1.1.dev1"])


class _NoLsRemote(FakeShell):
    """origin answers the fetch but not ``git ls-remote``."""

    def __call__(self, cmd: list[str], **kw):
        if cmd[:2] == ["git", "ls-remote"]:
            self.calls.append(list(cmd))
            return R.Done(128, "", "fatal: unable to access origin\n")
        return super().__call__(cmd, **kw)


def test_no_tag_origin_lacks_says_none_and_an_unasked_origin_is_no_refusal(tmp_path: Path):
    root = _system_repo(tmp_path, branch="develop", develop_ahead=True)
    said: list[str] = []
    assert _family(root, FakeShell(_answers(root)), said=said).release("patch", "yes") == 0
    assert f"release: {R.TAGS_BEHIND.format(remote='origin', version='0.1.1.dev1', tags='none')}" in said
    said = []
    shell = _NoLsRemote(_answers(root))
    assert _family(root, shell, said=said).release("patch", "yes") == 0
    unasked = R.TAGS_UNASKED.format(remote="origin", reason="fatal: unable to access origin", version="0.1.1.dev1")
    assert f"release: {unasked}" in said and said.index(f"release: {unasked}") < said.index(_dry_plan(said))


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
    assert fam.release_take("patch", *words) == 0
    take = ["just", "take", "0.1.1.dev1", *words]
    at = shell.calls.index(take)
    assert shell.cwds[at] == sibling and at == len(shell.calls) - 1                 # the last act, in the configuration
    assert shell.envs[at] == {**fam.env, "UV_REFRESH": "1"}                          # the index asked afresh
    assert "UV_REFRESH" not in fam.env                                              # by the take alone
    assert all(e is None or "UV_REFRESH" not in e for i, e in enumerate(shell.envs) if i != at)
    last_sync = max(i for i, t in enumerate(shell.texts()) if t == " ".join(SYNC))
    assert shell.first("git push origin develop") < last_sync < at                  # after the release's whole ending
    assert shell.first("just --summary") < shell.first("git fetch")                  # the configuration asked first
    reads = [i for i, t in enumerate(shell.texts()) if "show current_version" in t]
    assert reads[-1] > shell.first("git tag -a")                                     # read back after the cut
    main = R.TAKEN_MAIN if words else ""
    assert said[-1] == "release-take: " + R.TAKEN.format(version="0.1.1.dev1", root=sibling, main=main)
    assert _git(root, "tag", "-l") == "v0.1.1.dev1"


def _listed_after(misses: int) -> Callable[[list[str]], object]:
    """scripts/index-knows: TestPyPI lists the version from the (misses + 1)th ask on."""
    asked: list[int] = []

    def knows(cmd: list[str]):
        asked.append(1)
        return R.Done(0 if len(asked) > misses else 1)
    return knows


def test_release_take_waits_for_testpypi_to_list_the_version_before_it_takes(tmp_path: Path):
    """The tag's push publishes, in CI; the take installs from TestPyPI, so it waits, through
    scripts/index-knows, until TestPyPI lists the umbrella (uploaded last), asking once an interval."""
    root, sibling, shell, said, fam = _take_world(tmp_path, ("index-knows", _listed_after(2)))
    slept: list[float] = []
    fam.sleep = slept.append
    assert fam.release_take("patch") == 0
    asks = [i for i, c in enumerate(shell.calls) if "index-knows" in " ".join(c)]
    assert len(asks) == 3 and len(slept) == 2 and all(s == fam.index_interval for s in slept)
    assert shell.calls[asks[0]][-3:] == [R.INDEX_URL, "cs-image-system", "0.1.1.dev1"]
    assert R.INDEX_URL == "https://test.pypi.org/simple/"
    assert shell.first("git push origin main") < asks[0] and asks[-1] < shell.calls.index(["just", "take", "0.1.1.dev1"])


def test_release_take_that_testpypi_never_lists_runs_no_take_and_says_how_to_finish(tmp_path: Path):
    root, sibling, shell, said, fam = _take_world(tmp_path, ("index-knows", R.Done(1)))
    with pytest.raises(R.Refused) as e:
        fam.release_take("patch", "main")
    assert e.value.code == 1 and e.value.message == "release-take: " + R.NOT_LISTED.format(
        version="0.1.1.dev1", minutes=fam.index_wait_minutes, root=sibling,
        command="UV_REFRESH=1 just take 0.1.1.dev1 main")
    assert shell.count("just take") == 0 and _git(_remote(root), "tag", "-l") == "v0.1.1.dev1"   # released and pushed


def test_a_release_that_refuses_or_fails_runs_no_take(tmp_path: Path):
    root, _, shell, _, fam = _take_world(tmp_path / "a")
    (root / "stray").write_text("x\n")
    with pytest.raises(R.Refused, match="must be clean"):
        fam.release_take("patch")
    assert shell.count("just take") == 0
    _, _, shell, _, fam = _take_world(tmp_path / "b", ("just test", R.Done(3)))
    with pytest.raises(R.Refused) as e:
        fam.release_take("patch")
    assert e.value.code == 3 and shell.count("just take") == 0


def test_a_take_that_stops_says_the_release_is_done_and_how_to_finish(tmp_path: Path):
    root, sibling, shell, _, fam = _take_world(tmp_path, ("just take", R.Done(1)))
    with pytest.raises(R.Refused) as e:
        fam.release_take("patch", "main")
    assert e.value.code == 1 and e.value.message == "release-take: " + R.TAKE_STOPPED.format(
        version="0.1.1.dev1", root=sibling, rc=1, command="UV_REFRESH=1 just take 0.1.1.dev1 main")
    assert _git(_remote(root), "tag", "-l") == "v0.1.1.dev1"                         # the release itself went through


def test_the_dry_release_take_is_the_dry_release_then_the_take_it_would_run(tmp_path: Path):
    root, sibling, shell, said, fam = _take_world(tmp_path)
    refs, files = _refs(root), _files(root)
    assert fam.release_take("patch", "yes", "main") == 0
    assert _dry_plan(said) in said and said[-1] == "release-take: " + R.WOULD.format(
        command=f"cd {sibling} && UV_REFRESH=1 just take 0.1.1.dev1 main")
    assert "index-knows" in said[-2] and R.INDEX_URL in said[-2]                    # the wait for TestPyPI, first
    assert shell.count("just take") == 0 and shell.count("bump-my-version bump") == 0 and _moves(shell) == []
    assert shell.count("index-knows") == 0
    assert _refs(root) == refs and _files(root) == files


def test_release_take_refuses_a_word_or_a_configuration_it_cannot_take_in_before_anything(tmp_path: Path):
    _, _, shell, _, fam = _take_world(tmp_path / "a")
    with pytest.raises(R.Refused) as e:
        fam.release_take("patch", "mian")
    assert e.value.code == 2 and e.value.message == "release-take: " + R.NOT_A_TAKE_WORD.format(word="mian")
    root, sibling, shell, _, fam = _take_world(tmp_path / "b", ("just --summary", R.Done(0, "init build\n")))
    with pytest.raises(R.Refused) as e:
        fam.release_take("patch")
    assert e.value.message.startswith("release-take: no live configuration to take")
    assert shell.count("git fetch") == 0 and shell.count("publish-target-ready") == 0
    unconfigured = _family(root, FakeShell([TAKE_TREE, *_answers(root)]), tmp_path / "nowhere")
    with pytest.raises(R.Refused, match="nothing was changed"):
        unconfigured.release_take("patch")


# ------------------------------------------------------------------ main

def test_main_runs_the_family_from_the_working_directory_and_prints_a_refusal(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("CSIS_CONFIG_ROOT", raising=False)
    root = _system_repo(tmp_path / "f", branch="feature/x")
    monkeypatch.chdir(root)
    assert R.main(["release", "patch", "yes"]) == 1
    assert "this checkout is on 'feature/x'" in capsys.readouterr().out
    behind = _system_repo(tmp_path / "b", develop_ahead=True)
    assert R.main(["release", "patch", "--full", "yes", "--root", str(behind)]) == 1
    assert "--ff-only develop" in capsys.readouterr().out
    # past the guard on its own branch: whatever stops it next (no project here), it is not the branch
    assert R.main(["release", "patch", "yes", "--release-branch", "feature/x"]) != 0
    assert "nothing was changed" not in capsys.readouterr().out
    assert R.main(["release", "patch", "pypi", "yes"]) == 2                 # the standing decision, before the branch
    assert "TestPyPI until 1.0" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        R.main(["release"])
    for gone in ("push", "publish", "release-finish"):                      # the release uploads nothing itself
        with pytest.raises(SystemExit):
            R.main([gone])


def _plan(*args: str) -> list[str]:
    """The commands `just -n` says the recipe would run, one per line."""
    r = subprocess.run(["just", "-n", *args], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return [line for line in r.stderr.splitlines() if line.strip()]


def test_the_recipes_are_wrappers_over_the_script():
    """`just --summary` names the two recipes (and neither `publish` nor
    `release-finish`: the release uploads nothing, its tag's push publishes),
    and each one's plan is the one command that runs the script with the
    recipe's arguments; `release` and `release-take` pass the release branch
    and the configuration root, the probes the root alone."""
    if not os.access(SCRIPT, os.X_OK):
        pytest.fail("scripts/release.py is run as a script")
    summary = subprocess.run(["just", "--summary"], cwd=REPO, capture_output=True, text=True).stdout.split()
    assert {"release", "release-take"} <= set(summary) and not {"publish", "release-finish"} & set(summary)
    script = f'python "{SCRIPT}" '
    for args, call in ((("release", "patch", "--full", "yes"),
                        'release "patch" --full yes --release-branch "main" --config-root '),
                       (("release", "patch"), 'release "patch" --release-branch "main" --config-root '),
                       (("release-take", "patch", "main"),
                        'release-take "patch" main --release-branch "main" --config-root '),
                       (("_release-probes", "full"), 'probes "full" --config-root ')):
        plan = _plan(*args)
        assert len(plan) == 1, (args, plan)                                    # a wrapper, not a program
        line = " ".join(plan[0].split())                                       # no words: the line has a double space
        assert line.startswith("uv run --no-sync --project ") and script + call in line, (args, plan)


SURFACE_CHECK = "just surface-check"
SURFACE_LINE = "cs_image_system.base: cs_image_system.base.models.thing:Thing was removed from the surface"


def test_a_surface_changed_without_its_version_number_is_refused_before_the_gate(tmp_path: Path):
    """`just surface-check` failing is an entry of a declared surface removed or altered while the library's
    middle number stands still. The release stops at the probes, with the entry said: no gate, no bump, no
    tag, the tree as it was. Passing, the probe says nothing."""
    root = _system_repo(tmp_path)
    sibling = _sibling_repo(tmp_path)
    shell = FakeShell([(SURFACE_CHECK, R.Done(1, SURFACE_LINE + "\n")), (OWN, R.Done(0, OWN_LINE + "\n")), *_answers(root)])
    said: list[str] = []
    with pytest.raises(R.Refused) as e:
        _family(root, shell, sibling, said=said).release("patch")
    assert e.value.code == 1 and e.value.message == f"release: {R.SURFACE}" and SURFACE_LINE in said
    assert shell.first(OWN) < shell.first(SURFACE_CHECK)
    for never in ("just test", "bump-my-version bump", "uv lock", *NEVER_UPLOADS):
        assert shell.count(never) == 0, never
    assert _git(root, "status", "--porcelain") == "" and _git(root, "tag", "-l") == ""



def test_a_release_to_the_test_index_without_docker_is_refused_first(tmp_path: Path):
    """The test index's gate runs the install check, which needs the
    daemon: a release finds it missing before the bar, with nothing changed."""
    root = _system_repo(tmp_path)
    shell = FakeShell([("docker info", R.Done(1))])
    said: list[str] = []
    with pytest.raises(R.Refused) as e:
        _family(root, shell, said=said).probes()
    assert "docker" in e.value.message and "test-quickstart" in e.value.message
    assert "nothing was changed" in e.value.message and shell.count("just test") == 0


def test_a_release_pins_the_released_families_exactly_then_restores_their_ranges(tmp_path: Path):
    """Specification 013, D1: the release commit and its tag name each
    released-elsewhere name exactly at the newest TestPyPI release inside its
    range; the commit after the tag puts the ranges back, the tree's own
    between releases."""
    root = _system_repo(tmp_path)
    pyproject = root / "pyproject.toml"
    pyproject.write_text(pyproject.read_text() + '\n[project.optional-dependencies]\nfam = ["x-fam>=0.2,<0.3"]\n'
                         'all = ["x-fam>=0.2,<0.3"]\n')
    _git(root, "commit", "-qam", "a family released elsewhere")               # on main, checked out
    _git(root, "branch", "-f", "develop", "main")
    _git(root, "push", "-q", "-f", "origin", "develop", "main")
    shell = FakeShell([*_answers(root), ("with-released-families --newest test", R.Done(0, "x-fam==0.2.1\n"))])
    assert _family(root, shell).release("patch") == 0
    tagged = _git(root, "show", "v0.1.1.dev1:pyproject.toml")
    assert tagged.count('"x-fam==0.2.1"') == 2 and ">=0.2,<0.3" not in tagged
    assert _git(root, "show", "HEAD:pyproject.toml").count('"x-fam>=0.2,<0.3"') == 2
    assert _git(root, "log", "-2", "--format=%s").splitlines() == [
        "after release 0.1.1.dev1: the released families back on their ranges", "release 0.1.1.dev1"]
    assert shell.first("with-released-families --newest") < shell.first("git tag -a")     # pinned before the tag
    for never in NEVER_UPLOADS:
        assert shell.count(never) == 0, never
