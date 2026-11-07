# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The release family is scripts/release.py, run by three one-line recipes.

Against a fake shell that answers every command the family runs (uv,
bump-my-version, just, the probe scripts) and lets git through to a
temporary repository: the probes in their order and their one-line
verdicts; the dry form that prints what it would do and touches nothing;
the real form's order (the index, the bar, the index again, the bump, the
lock, the upload, the commit, the tag) and its closing line; what a failed
upload says about the uncommitted bump; ``release-finish``'s guards;
``publish``'s own order; the release's row in docs/CHANGES.md; and the one
reader of the sibling repository's working tree.
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


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


class FakeShell:
    """Answers each command by the first needle found in its text (a Done, or a callable that
    makes one), lets git through to the real repositories, and records every call."""

    def __init__(self, answers: list[tuple[str, object]] | None = None):
        self.answers = list(answers or [])
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], *, cwd: Path | None = None, capture: bool = True, env=None):
        self.calls.append(list(cmd))
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


def _system_repo(tmp_path: Path, *, branch: str = "main", develop_ahead: bool = False) -> Path:
    """A system checkout: pyproject, two members (one private), the lock and the CHANGES page,
    committed on develop, with ``branch`` checked out at develop's head."""
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
    if branch != "develop":
        _git(root, "checkout", "-q", "-b", branch)
    if develop_ahead:
        _git(root, "checkout", "-q", "develop")
        (root / "a").write_text("2\n")
        _git(root, "add", "a")
        _git(root, "commit", "-q", "-m", "two")
        _git(root, "checkout", "-q", branch)
    return root


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

def test_a_test_index_asks_only_the_venv(tmp_path: Path):
    root = _system_repo(tmp_path)
    shell = FakeShell([("docker info", R.Done(1))])
    said: list[str] = []
    _family(root, shell, said=said).probes("test")
    assert said == [f"release: {R.VENV_OK}"] and shell.count("docker") == 0


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
    shell = FakeShell(_answers(root))
    said: list[str] = []
    env = {"TEST_PYPI_TOKEN": "t"}
    assert _family(root, shell, env=env, said=said).release("patch", "test", "yes") == 0
    assert said[-1].startswith("release: dry") and "on main, 0.1.0 would become 0.1.1.dev1:" in said[-1]
    for needle in ("the probes above passed", "just test", "the index again", "bump-my-version bump patch", "uv lock",
                   "just publish test", "commit 'release 0.1.1.dev1'", "docs/CHANGES.md", "tag v0.1.1.dev1"):
        assert needle in said[-1], needle
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
    assert "just full-test, the index again" in said[-1] and "just publish pypi" in said[-1]


# ---------------------------------------------------------- the real form

def test_the_real_form_probes_gates_asks_again_bumps_uploads_then_commits_and_tags(tmp_path: Path):
    root = _system_repo(tmp_path)
    shell = FakeShell(_answers(root))
    said: list[str] = []
    fam = _family(root, shell, said=said)
    assert fam.release("patch", "test") == 0
    t = shell.texts()
    order = [shell.first(n) for n in ("publish-target-ready", "uv sync --all-extras --check", "just test",
                                      "bump-my-version bump patch", "uv lock", "just build", "publish-dist")]
    assert order == sorted(order), t
    asks = [i for i, x in enumerate(t) if "publish-target-ready" in x]
    assert len(asks) == 3 and shell.count("just test") == 1                                 # twice refusing a held version, then publish's own
    assert [("--refuse-held" in t[i]) for i in asks] == [True, True, False]
    assert shell.first("just test") < asks[1] < shell.first("bump-my-version bump")         # the index again after the bar
    assert shell.first("publish-dist") < shell.first("git add")                             # the upload before the commit
    dist = t[shell.first("publish-dist")]
    assert " test --version 0.1.1.dev1 --token-var TEST_PYPI_TOKEN --summary " in dist
    assert shell.count("git push") == 0
    assert _git(root, "log", "-1", "--format=%s") == "release 0.1.1.dev1" and _git(root, "tag", "-l") == "v0.1.1.dev1"
    assert _git(root, "status", "--porcelain") == ""
    committed = _git(root, "show", "--stat", "--format=", "HEAD")
    for name in ("pyproject.toml", "packages/one/pyproject.toml", "packages/two/pyproject.toml", "uv.lock", "docs/CHANGES.md"):
        assert name in committed, name
    page = (root / "docs" / "CHANGES.md").read_text().splitlines()
    assert page[4] == R.changes_row("0.1.1.dev1", "2001-02-03") and "| not yet |" not in "\n".join(page)
    pushes = fam.closing_line("main")
    assert pushes.startswith("git push --follow-tags origin main") and "git checkout develop" in pushes
    assert "git merge --ff-only main" in pushes and pushes.endswith("git push origin develop")
    assert said[-1] == R.RELEASED.format(version="0.1.1.dev1", name="testpypi", pushes=pushes)


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
    assert said[-1] == R.FINISHED.format(version="0.1.1.dev1", name="testpypi", pushes=fam.closing_line("main"))
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


def test_the_recipes_are_wrappers_over_the_script():
    if not os.access(SCRIPT, os.X_OK):
        pytest.fail("scripts/release.py is run as a script")
    text = (REPO / "Justfile").read_text()
    for recipe, call in (("release target index=", "release.py\" release \"{{target}}\" \"{{index}}\" \"{{dry}}\""),
                         ("release-finish index=", "release.py\" release-finish \"{{index}}\""),
                         ("publish index=", "release.py\" publish \"{{index}}\""),
                         ("_release-probes index who=", "release.py\" probes \"{{index}}\" \"{{who}}\"")):
        at = text.index(f"\n{recipe}")
        body = text[at:].split("\n\n", 1)[0]
        assert call in body, recipe
        assert body.count("\n\t") <= 2, f"{recipe}: a wrapper, not a program"
    for needle in ("--release-branch \"{{release_branch}}\"", "--config-root {{quote(config_root)}}"):
        assert text.count(needle) >= 2, needle
