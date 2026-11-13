#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0
"""The release family: what `just release`, `just release-finish` and `just publish` do.

    uv run python scripts/release.py release <part|version> [test|pypi] [yes] [--release-branch B] [--config-root DIR]
    uv run python scripts/release.py release-finish [test|pypi] [--release-branch B] [--config-root DIR]
    uv run python scripts/release.py publish [test|pypi]
    uv run python scripts/release.py probes <test|pypi> [release|release-finish] [--config-root DIR]

The recipes are wrappers over this script; the logic is here, as functions,
so that it can be tested with a stubbed shell and no network. Every command
the family runs -- git, uv, bump-my-version, just, the probe scripts -- goes
through one ``run`` callable, which the tests replace.

``release`` cuts a release and publishes it, in this order: the probes
before anything changes (the branch is the release branch with ``develop``
an ancestor, or a maintenance branch ``release/<major.minor>``; the target
names a version of the accepted shape; the index can take an upload and
holds the version for no project; the token is set; no ``v<version>`` tag
exists here; the venv is in step with the lock; every package whose
version the release does not move is fresh on the index or held there as
this tree's build; for PyPI, docker and the live configuration's sessions
answer); the dry form (``yes``) prints
what the real form would do and stops; then a clean working tree, the gate
(the bar for TestPyPI, ``full-test`` with the modification-test evidence
for PyPI), the index AGAIN after the gate, the bump and the lock, the
upload BEFORE the commit and the tag (a failed upload leaves an uncommitted
bump and never a tagged, unpublished version), then the evidence commit in
the live configuration (PyPI), the release's row in ``docs/CHANGES.md``,
the commit ``release <version>`` and the annotated tag. Nothing is pushed;
the closing line names the operator's pushes.

``release-finish`` makes the commit and the tag of a release whose upload
stopped part-way and was completed by ``just publish``: on the release
branch with the bump uncommitted and nothing else changed, once the index
holds the version for every project.

``publish`` builds and uploads the version in the tree: the index asked
first, ``dist/`` cleaned, ``just build``, then ``scripts/publish-dist``,
one project at a time.

``probes`` is what ``release`` asks first: the venv; the packages whose
version it does not move (scripts/own-versions-current); for a PyPI
release docker, the live configuration and its sessions; one line each.
``release-finish`` asks the venv alone: it builds and uploads nothing.

The reference configuration's working tree (the live configuration beside
this repository, or ``CSIS_CONFIG_ROOT``) is read by ``read_sibling``
alone: its path, whether it is configured, its branch, its dirty files and
its tags. Everything here that needs the sibling takes a ``SiblingTree``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

INDEXES: dict[str, str] = {"test": "testpypi", "pypi": "pypi"}
TOKEN_VARS: dict[str, str] = {"testpypi": "TEST_PYPI_TOKEN", "pypi": "PYPI_TOKEN"}
SHAPE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(\.dev[0-9]+)?$")
MAINTENANCE = re.compile(r"^release/[0-9]+\.[0-9]+")
NOT_NOW = 75
#: the files a bump changes: what the release commit takes, and all that may be dirty at a finish
BUMPED = re.compile(r"^ M (pyproject\.toml|packages/[^/]+/pyproject\.toml|uv\.lock)$")
PRIVATE = "Private :: Do Not Upload"
CHANGES = Path("docs") / "CHANGES.md"
CHANGES_HEADER = "| Stage | Landed | Released in | Squash subject |"
UNRELEASED = "not yet"
#: the probes' one-line verdicts, after "<who>: "
VENV_OK = "the venv is in step with the lock"
SESSIONS_OK = "every runtime session of the live configuration is present"
#: the own-version probe's refusals, after "<who>: ", below scripts/own-versions-current's own lines
UNBUMPED = ("a package whose version the release does not move changed since the index took that version (above), "
            "so the upload would be refused after the gate -- bump that package's own version and commit it -- "
            "nothing was changed")
UNASKED = ("the index could not be asked whether it holds this tree's build of every package whose version the "
           "release does not move, or one could not be built (above); nothing is guessed -- nothing was changed")
#: the closing lines: what is on the index, and (a release) the operator's pushes
RELEASED = ("release: {version} is on {name}, committed and tagged v{version}; push with: {pushes} "
            "(CI checks the pushed tag against the index and uploads nothing already there)")
FINISHED = ("release-finish: {version} is on {name} for every project, committed and tagged v{version}; "
            "push with: {pushes}")
PUBLISHED = ("publish: cs-image-system {version} is on {name} (the system and its {packages} published packages, "
             "sdist and wheel each; files already there with the same content were skipped)")


def published_members(root: Path) -> list[Path]:
    """The workspace members an upload takes: every ``packages/*/pyproject.toml`` but the ones classified
    ``Private :: Do Not Upload`` (the workspace-only plugins, built with the rest and never uploaded)."""
    return sorted(p for p in root.glob("packages/*/pyproject.toml") if PRIVATE not in p.read_text())


# ------------------------------------------------------------------ the shell

@dataclass(frozen=True)
class Done:
    rc: int
    out: str = ""
    err: str = ""


Run = Callable[..., Done]


def run(cmd: list[str], *, cwd: Path | None = None, capture: bool = True, env: Mapping[str, str] | None = None) -> Done:
    """Run one command. ``capture`` holds its output for the caller; without
    it the command's output flows to the terminal (the bar, the upload)."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True, env=dict(env) if env else None,
                           stdin=subprocess.DEVNULL)
    except FileNotFoundError as e:
        return Done(127, "", str(e))
    return Done(p.returncode, p.stdout or "", p.stderr or "")


class Refused(Exception):
    """A guard that stopped the family, with the message to print and the exit code."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.message, self.code = message, code


# -------------------------------------------------------------- the sibling

def default_config_root() -> Path:
    """The Justfile's default: ``CSIS_CONFIG_ROOT``, else the reference configuration beside this repository."""
    return Path(os.environ.get("CSIS_CONFIG_ROOT") or REPO.parent / "cs-image-system-testconfig")


@dataclass(frozen=True)
class SiblingTree:
    """What ``read_sibling`` found: the reference configuration's working tree."""
    path: Path
    configured: bool                   #: cfg/_config.yml is there (what `just config-guard` checks)
    branch: str | None                 #: None when the path is not a git checkout
    dirty: tuple[str, ...]             #: `git status --porcelain` lines
    tags: tuple[str, ...]

    def dirty_apart_from(self, *names: str) -> tuple[str, ...]:
        """The dirty lines whose path is none of ``names``."""
        return tuple(line for line in self.dirty if line[3:] not in names)

    def has(self, rel: str) -> bool:
        return (self.path / rel).is_file()


def read_sibling(config_root: Path | str | None = None, *, run: Run = run) -> SiblingTree:
    """The one reader of the sibling repository's working tree.

    ``config_root`` is the tree's path; ``None`` takes ``CSIS_CONFIG_ROOT``,
    else the reference configuration beside this repository (the Justfile's
    ``config_root`` default). Returns its path, whether ``cfg/_config.yml``
    is there, its branch (``None`` when it is no git checkout), its dirty
    files as ``git status --porcelain`` lines and its tags. Reads only; the
    writes the release makes there (the modification-test evidence commit)
    are ``commit_evidence``'s.
    """
    path = Path(config_root) if config_root else default_config_root()
    configured = (path / "cfg" / "_config.yml").is_file()
    if not path.is_dir():
        return SiblingTree(path, configured, None, (), ())
    head = run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"])
    if head.rc != 0:
        return SiblingTree(path, configured, None, (), ())
    status = run(["git", "-C", str(path), "status", "--porcelain"])
    tags = run(["git", "-C", str(path), "tag", "-l"])
    return SiblingTree(path, configured, head.out.strip(), tuple(status.out.splitlines()), tuple(tags.out.split()))


def commit_evidence(tree: SiblingTree, version: str, *, run: Run = run, tolerate_missing: bool = False) -> None:
    """The modification-test evidence, committed in the live configuration when it changed."""
    git = ["git", "-C", str(tree.path)]
    added = run([*git, "add", "meta-state/mod-tests.yaml"])
    if added.rc != 0 and not tolerate_missing:
        raise Refused(added.err.strip() or "release: git add meta-state/mod-tests.yaml failed", added.rc)
    if run([*git, "diff", "--cached", "--quiet"]).rc != 0:
        done = run([*git, "commit", "-q", "-m", f"release {version}: modification-test evidence"])
        if done.rc != 0:
            raise Refused(done.err.strip() or "release: the evidence commit failed", done.rc)


# ------------------------------------------------------------ the CHANGES row

def changes_row(version: str, date: str) -> str:
    """The release's row of docs/CHANGES.md: the ``#r<version>`` anchor with dots as dashes, the date,
    the version as what it was released in, and the release commit's subject."""
    anchor = "r" + version.replace(".", "-")
    return f'| <a id="{anchor}"></a>release {version} | {date} | {version} | release {version} |'


def append_release_row(page: Path, version: str, date: str, *, stamp_unreleased: bool) -> bool:
    """Insert the release's row at the top of the table (newest first). With
    ``stamp_unreleased`` every row still "not yet" released is stamped with
    this version, since the tag contains it. False when the page is absent."""
    if not page.is_file():
        return False
    lines = page.read_text().splitlines(keepends=True)
    try:
        at = next(i for i, line in enumerate(lines) if line.startswith(CHANGES_HEADER)) + 2
    except StopIteration:
        raise Refused(f"release: {page} has no table headed {CHANGES_HEADER!r} -- nothing was changed", 2) from None
    if stamp_unreleased:
        for i in range(at, len(lines)):
            if lines[i].startswith("|"):
                lines[i] = lines[i].replace(f"| {UNRELEASED} |", f"| {version} |", 1)
    lines.insert(at, changes_row(version, date) + "\n")
    page.write_text("".join(lines))
    return True


# -------------------------------------------------------------- the family

@dataclass
class Family:
    """The release family over one checkout: ``root`` is the system repository, ``sibling`` the
    reference configuration, ``release_branch`` the one branch releases are cut on."""
    root: Path
    sibling: SiblingTree
    release_branch: str = "main"
    run: Run = run
    env: MutableMapping[str, str] = field(default_factory=lambda: os.environ)
    say: Callable[[str], None] = print
    today: Callable[[], str] = lambda: _dt.date.today().isoformat()

    # --- helpers

    def git(self, *args: str, capture: bool = True) -> Done:
        return self.run(["git", *args], cwd=self.root, capture=capture)

    def index_name(self, index: str, who: str) -> str:
        if index not in INDEXES:
            raise Refused(f"{who}: the index is test (TestPyPI, the default) or pypi, not '{index}'", 2)
        return INDEXES[index]

    def current_version(self, who: str) -> str:
        done = self.run(["uv", "run", "--no-sync", "bump-my-version", "show", "current_version"], cwd=self.root)
        if done.rc != 0:
            raise Refused((done.err + done.out).strip() or f"{who}: bump-my-version could not show the current version",
                          done.rc or 2)
        return done.out.strip()

    def branch_guard(self, who: str, *, ancestor_check: bool) -> str:
        """The checkout is on the release branch (and, for ``release``, develop is an ancestor of it) or on a
        maintenance branch; any other branch is refused by name."""
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD").out.strip()
        if branch == self.release_branch:
            if ancestor_check:
                dev = "develop"
                if self.git("rev-parse", "-q", "--verify", "develop").rc != 0:
                    dev = "origin/develop"
                if self.git("merge-base", "--is-ancestor", dev, "HEAD").rc != 0:
                    raise Refused(f"{who}: {self.release_branch} is behind {dev} -- a release never leaves a stage "
                                  f"behind; first, on {self.release_branch}: git merge --ff-only {dev} -- nothing "
                                  "was changed")
            return branch
        if MAINTENANCE.match(branch):
            if ancestor_check:
                self.say(f"{who}: on the maintenance branch {branch} (an old version's fix; develop is not checked)")
            return branch
        raise Refused(f"{who}: this checkout is on '{branch}'; a release is cut on {self.release_branch} alone (or a "
                      f"maintenance branch release/<major.minor>) -- nothing was changed")

    def version_plan(self, target: str, current: str) -> tuple[str, list[str]]:
        """(the new version, bump-my-version's arguments for it) from a part or an explicit version."""
        if SHAPE.match(target):
            return target, ["bump", "--new-version", target]
        done = self.run(["uv", "run", "--no-sync", "bump-my-version", "show", "--increment", target, "new_version"],
                        cwd=self.root)
        if done.rc != 0:
            raise Refused(f"release: '{target}' is neither a version part (patch, minor, major, dev, stage) nor a "
                          "version", 2)
        new = done.out.strip()
        if not SHAPE.match(new):
            raise Refused(f"release: {current} is a final version and '{target}' would make it {new} -- open the next "
                          "version with patch, minor or major (its first development release), then dev for each "
                          "further one", 2)
        return new, ["bump", target]

    def index_ready(self, index: str, version: str, *flags: str) -> int:
        """scripts/publish-target-ready's verdict: 0 ready, 75 not now, 1 a held version refused, 2 could not run."""
        done = self.run(["uv", "run", "--no-sync", "python", str(HERE / "publish-target-ready"), index,
                         "--version", version, *flags, "--quiet"], cwd=self.root, capture=False)
        return done.rc

    def ready_or_refuse(self, index: str, name: str, version: str) -> None:
        """The index itself, first of the probes and again after the bar. 75 is "not now";
        1 is a version some project already holds (never re-cut)."""
        rc = self.index_ready(index, version, "--refuse-held")
        if rc == 0:
            return
        if rc == NOT_NOW:
            raise Refused(f"release: {name} cannot take an upload now (above) -- nothing was changed; it is the index's "
                          f"condition, not the release's: `just index-ready {index} wait` waits for it", NOT_NOW)
        if rc == 1:
            raise Refused(f"release: {version} is already on {name} (above) -- a version is never re-cut")
        raise Refused(f"release: the publish-target probe could not run (exit {rc})", 2)

    def token(self, name: str, who: str) -> str:
        """UV_PUBLISH_TOKEN, else the index's own name (TEST_PYPI_TOKEN or PYPI_TOKEN, the repository secrets'
        names, so one .envrc line serves the shell and CI alike); exported for the upload."""
        var = TOKEN_VARS[name]
        token = self.env.get("UV_PUBLISH_TOKEN") or self.env.get(var) or ""
        if not token:
            if who == "publish":
                raise Refused(f"publish: neither UV_PUBLISH_TOKEN nor {var} is set -- the API token for {name}, from "
                              "the environment; never in this file", 2)
            raise Refused(f"release: neither UV_PUBLISH_TOKEN nor {var} is set -- the API token for {name}; a release "
                          "publishes, so it refuses up front rather than leave a tagged, unpublished version", 2)
        self.env["UV_PUBLISH_TOKEN"] = token
        return var

    def tagged(self, version: str) -> bool:
        return bool(self.git("tag", "-l", f"v{version}").out.strip())

    # --- the probes

    def own_versions_or_refuse(self, index: str, who: str) -> None:
        """scripts/own-versions-current, its lines said: every package whose version the release does not move
        (the bump's `glob_exclude`: the contract) is either not on the index (it goes up fresh) or held there as
        exactly this tree's build, file for file and byte for byte (the upload skips it). Exit 1 is a package
        that changed under a version the index holds: refused, since the index would refuse its upload after the
        gate. Any other failure is refused as "could not ask" (exit 2), never guessed."""
        done = self.run(["uv", "run", "--no-sync", "python", str(HERE / "own-versions-current"), index,
                         "--root", str(self.root)], cwd=self.root)
        for line in done.out.splitlines():
            if line.strip():
                self.say(line)
        if done.rc == 0:
            return
        if done.rc == 1:
            raise Refused(f"{who}: {UNBUMPED}", 1)
        for line in done.err.splitlines():
            if line.strip():
                self.say(line)
        raise Refused(f"{who}: {UNASKED}", 2)

    def probes(self, index: str, who: str = "release") -> None:
        """What a release needs and full-test only finds out twenty minutes in, asked first and in one line each.
        For every index: the venv is in step with the lock (`uv sync --all-extras --check`), because every recipe
        runs `uv run --no-sync` and a venv behind the checkout answers with stale metadata; then, for a release,
        every package whose version the release does not move is fresh on the index or held there as this tree's
        build (`own_versions_or_refuse`: an index never takes a second build under a version, so a changed
        package without its own bump would be refused at the upload, after the gate). For a PyPI release
        also: docker answers, the live configuration is present and every runtime session of it is present
        (`just preflight`, the gate full-test itself uses: without it the live legs would be skipped, which a
        release cannot accept) and how many minutes the soonest-expiring session has left
        (scripts/session-minutes-left; refused only when a token has already lapsed, otherwise said).
        `release-finish` asks the venv alone: it runs no bar, builds nothing and uploads nothing."""
        # the venv asked is the one running this script: the checkout's own
        if self.run(["uv", "sync", "--all-extras", "--check"], cwd=REPO).rc != 0:
            raise Refused(f"{who}: the venv is behind the checkout (uv sync --all-extras --check) -- `just init` syncs "
                          "it -- nothing was changed")
        self.say(f"{who}: {VENV_OK}")
        if who == "release":
            self.own_versions_or_refuse(index, who)
        if index != "pypi" or who != "release":
            return
        if self.run(["docker", "info"], cwd=self.root).rc != 0:
            raise Refused(f"{who}: docker is not answering (docker info) -- full-test's legs need it; start the daemon "
                          "-- nothing was changed")
        self.say(f"{who}: docker answers")
        root = self.sibling.path
        if not self.sibling.configured:
            raise Refused(f"{who}: no live configuration at {root} (`just config-guard` says why) -- full-test's live "
                          "legs need it -- nothing was changed")
        if self.run(["just", "preflight"], cwd=self.root).rc != 0:
            raise Refused(f"{who}: a runtime session of the live configuration is absent or expired (`just preflight` "
                          "says which) -- full-test's live legs would be skipped; log in -- nothing was changed")
        # how long the soonest-expiring session has left; a login lasts one hour and a PyPI release takes nearly
        # all of it
        asked = self.run(["uv", "run", "--no-sync", "python", str(HERE / "session-minutes-left"), str(root)],
                         cwd=self.root)
        left = asked.out.strip() if asked.rc == 0 else ""
        try:
            minutes = int(left)
        except ValueError:
            self.say(f"{who}: {SESSIONS_OK}")
            return
        if minutes < 0:
            raise Refused(f"{who}: a session's cached token lapsed {-minutes} minutes ago -- a release takes about an "
                          "hour; log in again first (`just preflight` names the command) -- nothing was changed")
        if minutes < 60:
            self.say(f"{who}: {SESSIONS_OK}; the soonest-expiring session has {minutes} minutes left and a release "
                     "takes about an hour -- log in again from a second terminal about halfway: a running run picks "
                     "the new token up")
        else:
            self.say(f"{who}: {SESSIONS_OK}; the soonest-expiring session has {minutes} minutes left")

    # --- the pieces of a release

    def bumped_files(self) -> list[str]:
        """The files a bump changes, for the release commit."""
        members = sorted(str(p.relative_to(self.root)) for p in self.root.glob("packages/*/pyproject.toml"))
        return ["pyproject.toml", *members, "uv.lock"]

    def gate(self, name: str) -> None:
        """The bar for a development release to TestPyPI; full-test, the modification-test evidence in the live
        configuration and a clean live checkout for PyPI."""
        if name == "pypi":
            done = self.run(["just", "full-test"], cwd=self.root, capture=False)
            if done.rc != 0:
                raise Refused("", done.rc)
            root = self.sibling.path
            if not self.sibling.has("meta-state/mod-tests.yaml"):
                raise Refused(f"release: no modification-test evidence at {root}/meta-state/mod-tests.yaml (run "
                              "full-test with docker)")
            # full-test's docker leg wrote the evidence, so the tree is read again
            tree = read_sibling(root, run=self.run)
            others = tree.dirty_apart_from("meta-state/mod-tests.yaml")
            if others:
                raise Refused("release: the live configuration must be clean apart from its mod-test evidence:\n"
                              + "\n".join(others))
        else:
            done = self.run(["just", "test"], cwd=self.root, capture=False)
            if done.rc != 0:
                raise Refused("", done.rc)

    def bump(self, args: list[str]) -> None:
        for cmd in (["uv", "run", "--no-sync", "bump-my-version", *args], ["uv", "lock"]):
            done = self.run(cmd, cwd=self.root, capture=False)
            if done.rc != 0:
                raise Refused("", done.rc)

    def upload(self, index: str, name: str, version: str) -> None:
        """`publish`, with the advice a failed upload needs: what to do with the uncommitted bump depends on
        whether any project already holds the version, counted by publish-dist from its own upload (the
        index's pages lag by minutes)."""
        fd, summary_path = tempfile.mkstemp(prefix="csis-publish-summary.", dir=self.env.get("TMPDIR") or None)
        os.close(fd)
        summary = Path(summary_path)
        try:
            rc = self.publish(index, summary=summary)
            if rc == 0:
                return
            held, total = 0, "?"
            if summary.is_file():
                for line in summary.read_text().splitlines():
                    if line.startswith("held "):
                        held = int(line[5:])
                    elif line.startswith("total "):
                        total = line[6:]
        finally:
            summary.unlink(missing_ok=True)
        if held > 0:
            when = "again in a day" if rc == NOT_NOW else "again"
            raise Refused(f"release: the upload to {name} stopped part-way: {held} of {total} projects hold {version}, "
                          "and those files can never be uploaded again under another version. KEEP the uncommitted "
                          f"bump to {version}; run `just publish {index}` {when} until every project holds it, then "
                          f"`just release-finish {index}` commits, tags and records the release", rc)
        raise Refused(f"release: the upload to {name} failed and no project holds {version}; the bump is uncommitted "
                      "-- discard it with: git checkout -- pyproject.toml packages/*/pyproject.toml uv.lock")

    def record_and_tag(self, version: str, *, on_release_branch: bool) -> None:
        """The release's row in docs/CHANGES.md, the commit `release <version>` and the annotated tag."""
        files = self.bumped_files()
        if append_release_row(self.root / CHANGES, version, self.today(), stamp_unreleased=on_release_branch):
            files.append(str(CHANGES))
        else:
            self.say(f"release: no {CHANGES} here to record {version} in")
        for cmd in (["add", *files], ["commit", "-q", "-m", f"release {version}"],
                    ["tag", "-a", f"v{version}", "-m", f"release {version}"]):
            done = self.git(*cmd)
            if done.rc != 0:
                raise Refused((done.err + done.out).strip() or f"release: git {cmd[0]} failed", done.rc)

    def closing_line(self, branch: str) -> str:
        """The operator's pushes: the release branch with its tags, then develop's fast-forward back."""
        after = f"git push --follow-tags origin {branch}"
        if branch == self.release_branch:
            after += (f"; then develop takes it back: git checkout develop && git merge --ff-only "
                      f"{self.release_branch} && git push origin develop")
        return after

    # --- the commands

    def release(self, target: str, index: str = "test", dry: str = "no") -> int:
        name = self.index_name(index, "release")
        branch = self.branch_guard("release", ancestor_check=True)
        current = self.current_version("release")
        new, bump_args = self.version_plan(target, current)
        self.ready_or_refuse(index, name, new)
        self.token(name, "release")
        if self.tagged(new):
            raise Refused(f"release: v{new} is already tagged here -- a version is never re-cut, even after its files "
                          "were deleted from the index")
        self.probes(index, "release")
        gate = "full-test" if name == "pypi" else "test"
        if dry == "yes":
            self.say(f"release: dry -- on {branch}, {current} would become {new}: {name} ready and free of it, "
                     f"untagged, token present, the probes above passed. The real form: just {gate}, the index "
                     f"again, bump-my-version {' '.join(bump_args)}, uv lock, just publish {index}, commit "
                     f"'release {new}' (with its {CHANGES} row), tag v{new}")
            return 0
        dirty = self.git("status", "--porcelain").out.strip()
        if dirty:
            raise Refused("release: the working tree must be clean -- commit these changes, or discard them (git "
                          "restore, or git stash); the guard counts every tracked change and every file git does not "
                          "ignore:\n" + dirty)
        self.gate(name)
        # the bar takes twenty minutes; an index that went down meanwhile leaves a clean tree
        self.ready_or_refuse(index, name, new)
        self.bump(bump_args)
        self.upload(index, name, new)
        if name == "pypi":
            commit_evidence(read_sibling(self.sibling.path, run=self.run), new, run=self.run)
        self.record_and_tag(new, on_release_branch=branch == self.release_branch)
        self.say(RELEASED.format(version=new, name=name, pushes=self.closing_line(branch)))
        return 0

    def finish(self, index: str = "test") -> int:
        name = self.index_name(index, "release-finish")
        branch = self.branch_guard("release-finish", ancestor_check=False)
        self.probes(index, "release-finish")
        new = self.current_version("release-finish")
        shown = self.git("show", "HEAD:pyproject.toml").out
        committed = next((m.group(1) for m in (re.match(r'^version = "(.*)"$', line) for line in shown.splitlines())
                          if m), "")
        if committed == new:
            raise Refused(f"release-finish: {new} is already committed -- there is no uncommitted bump to finish")
        if self.tagged(new):
            raise Refused(f"release-finish: v{new} is already tagged here")
        others = [line for line in self.git("status", "--porcelain").out.splitlines() if not BUMPED.match(line)]
        if others:
            raise Refused(f"release-finish: the tree must hold the bump to {new} and nothing else:\n" + "\n".join(others))
        rc = self.index_ready(index, new, "--all-held")
        if rc == 1:
            raise Refused(f"release-finish: not every project holds {new} on {name} (above) -- run `just publish "
                          f"{index}` until it completes (the index's pages lag an upload by minutes)")
        if rc == NOT_NOW:
            raise Refused(f"release-finish: {name} cannot be asked now (above) -- nothing was changed", NOT_NOW)
        if rc != 0:
            raise Refused(f"release-finish: the publish-target probe could not run (exit {rc})", 2)
        if name == "pypi":
            tree = read_sibling(self.sibling.path, run=self.run)
            if not tree.configured:
                raise Refused(f"release-finish: no live configuration at {tree.path} (cfg/_config.yml) for the "
                              "modification-test evidence -- nothing was changed")
            commit_evidence(tree, new, run=self.run, tolerate_missing=True)
        self.record_and_tag(new, on_release_branch=branch == self.release_branch)
        self.say(FINISHED.format(version=new, name=name, pushes=self.closing_line(branch)))
        return 0

    def publish(self, index: str = "test", *, summary: Path | None = None) -> int:
        """Build and upload the version in the tree: the index asked first (a partial upload of this version is
        what a re-run completes, so a project that already holds it is reported, not refused), `dist/` cleaned,
        every package built, then scripts/publish-dist: one project at a time, sdist and wheel together,
        dependencies first and cs-image-system last; a 429 is exit 75 with what is left; when everything was
        already there, one file is sent again to prove the token. Returns publish-dist's exit code."""
        name = self.index_name(index, "publish")
        var = self.token(name, "publish")
        version = self.current_version("publish")
        rc = self.index_ready(index, version)
        if rc == NOT_NOW:
            raise Refused(f"publish: {name} cannot take an upload now (above) -- nothing was uploaded; it is the "
                          f"index's condition: `just index-ready {index} wait` waits for it", NOT_NOW)
        if rc != 0:
            raise Refused(f"publish: the publish-target probe could not run (exit {rc})", 2)
        shutil.rmtree(self.root / "dist", ignore_errors=True)
        built = self.run(["just", "build"], cwd=self.root, capture=False)
        if built.rc != 0:
            raise Refused("", built.rc)
        packages = len(published_members(self.root))
        cmd = ["uv", "run", "--no-sync", "python", str(HERE / "publish-dist"), index, "--version", version,
               "--token-var", var]
        if summary is not None:
            cmd += ["--summary", str(summary)]
        done = self.run(cmd, cwd=self.root, capture=False)
        if done.rc != 0:
            return done.rc
        self.say(PUBLISHED.format(version=version, name=name, packages=packages))
        return 0


# ------------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="release.py", description=(__doc__ or "").splitlines()[0])
    ap.add_argument("command", choices=["release", "release-finish", "publish", "probes"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--release-branch", default="main")
    ap.add_argument("--config-root", default=None)
    ap.add_argument("--root", type=Path, default=None, help="the system checkout (default: the working directory)")
    ns = ap.parse_args(argv)
    root = (ns.root or Path.cwd()).resolve()
    family = Family(root=root, sibling=read_sibling(ns.config_root), release_branch=ns.release_branch)
    try:
        if ns.command == "release":
            if not ns.args:
                ap.error("release needs a version part or a version")
            return family.release(*ns.args[:3])
        if ns.command == "release-finish":
            return family.finish(*ns.args[:1])
        if ns.command == "publish":
            return family.publish(*ns.args[:1])
        family.probes(*ns.args[:2])
        return 0
    except Refused as e:
        if e.message:
            print(e.message)
        return e.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
