#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0
"""The release family: what `just release` and `just release-take` do.

    uv run python scripts/release.py release <part|version> [--full] [yes] [--release-branch B] [--config-root DIR]
    uv run python scripts/release.py release-take <part|version> [--full] [main] [yes] [--release-branch B] [--config-root DIR]
    uv run python scripts/release.py probes [light|full] [--config-root DIR]

The recipes are wrappers over this script; the logic is here, as functions,
so that it can be tested with a stubbed shell and no network. Every command
the family runs -- git, uv, bump-my-version, just, the probe scripts -- goes
through one ``run`` callable, which the tests replace.

Until the operator declares 1.0 a release goes to TestPyPI alone (the
standing decision; specification 013): ``pypi`` is refused, naming it,
before anything is asked or changed. A release never uploads: it commits,
tags and pushes, and the tag's push runs the publish workflow, which uploads
every public project to TestPyPI by trusted publishing (no token anywhere).

``release`` cuts a release and pushes it. It starts on ``develop`` (it moves
to the release branch itself), on the release branch with ``develop`` an
ancestor, or on a maintenance branch ``release/<major.minor>``; any other
branch is refused. In this order: the cheap probes before anything changes
(the words; the branch; a clean working tree; the target names a version of
the accepted shape; TestPyPI answers and holds the version for no project;
no ``v<version>`` tag exists here; the remote is there to push to; and,
after ``git fetch origin``, origin holds no commit that a branch the ending
pushes lacks -- the release branch and ``develop``, or the maintenance
branch -- since that push would be refused after the gate; a local branch
ahead of origin passes; then one line names the local annotated tags origin
lacks, which stay behind, or says none -- never a refusal); then the
advisory (``advise``): when a path changed since the newest fully proven
release is in ``FULL_PROOF_PATHS``, or the take pushes the reference's
``main`` (an applying cycle), one line says a full proof is probably needed
and why -- never a refusal, and not said under ``--full``. From
``develop``, the move: the release branch checked out and fast-forwarded to
``develop`` (refused, on ``develop``, when it cannot be); the resync of the
venv (``uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all``: a branch switch and a moved lock leave the
venv behind the checkout); then the probes that need the venv (it is in
step with the lock; every package whose version the release does not move
is fresh on TestPyPI or held there as this tree's build; every family
released elsewhere has a TestPyPI release inside the range the extras name;
the SDK's surfaces; docker; under ``--full`` the live configuration and its
sessions), the gate (the lighter check -- ``just test`` and the install
check ``just test-quickstart``, the quickstart page's own commands against this tree's wheels -- by default; ``just full-test`` with the
modification-test evidence and a clean live checkout under ``--full``) and
TestPyPI AGAIN after the gate. A refusal or a failure up to here returns the
checkout to the branch it started on, with the release branch where it was,
and says so. Then the bump and the lock, the released families pinned
exactly (``pin_released_families``), the evidence commit in the live
configuration (``--full``), the release's row in ``docs/CHANGES.md``, the
commit ``release <version>`` and the annotated tag (its message carries
``fully proven: full-test`` under ``--full``, the line the advisory measures
from), the families back on their ranges in a commit of their own (a step
that fails there names what is left, as a failed step of the ending does);
and last
the ending: the release branch and the tag ``v<version>`` pushed by name (no
other tag travels with them: GitHub starts no tag run when more than three
tags are pushed at once), ``develop`` checked out, fast-forwarded to it and
pushed (a maintenance branch: that branch and its tag pushed, ``develop``
untouched), and the venv synced again. A failed step of the ending names
itself and the commands that are left, and exits non-zero. The dry form
(``yes``) asks the cheap probes and the venv's, prints every branch move,
push and resync it would make, read from the refs, and changes nothing.

``release-take`` is the release, as ``release`` runs it, then a wait for
TestPyPI to list ``cs-image-system <version>`` (scripts/index-knows, asked
every ``index_interval`` seconds for ``index_wait_minutes`` at most: the
umbrella is uploaded last, so its listing means the publish workflow's
upload is done), and then ``just take <version>`` in the live configuration,
``main`` passed through when given, with ``UV_REFRESH=1`` in that one
command's environment: the take is the tree's own recipe, from the release
it is on, and uv answers its install from the index page it cached before
the upload unless told to ask afresh. The configuration is asked first
(configured, a git checkout, with a ``take`` recipe), before the release
changes anything. The version is read back from the tree the release left
(``bump-my-version show current_version``, its tag here), never recomputed.
A release that refuses or fails runs no take; a version TestPyPI never lists
in time, or a take that stops (an edited file, a lapsed session), is said
with the command that finishes it there, and its exit code. ``yes`` is the
dry form: the release's dry form, then the wait and the take it would run.

``probes`` is what ``release`` asks first: the venv; the packages whose
version it does not move (scripts/own-versions-current); the families
released elsewhere (scripts/with-released-families --check test); the
surfaces; docker; for ``full`` the live configuration and its sessions;
one line each.

The reference configuration's working tree (the live configuration beside
this repository, or ``CSIS_CONFIG_ROOT``) is read by ``read_sibling``
alone: its path, whether it is configured, its branch, its dirty files and
its tags. Everything here that needs the sibling takes a ``SiblingTree``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

#: the one index a release reaches until 1.0: its label for the probe scripts, its name in pyproject.toml's
#: `[[tool.uv.index]]`, its simple API, and the project whose listing says the publish workflow's upload is done
INDEX = "test"
NAME = "testpypi"
INDEX_URL = "https://test.pypi.org/simple/"
PROJECT = "cs-image-system"
#: the refusal of PyPI, after "<who>: " (specification 013, FR-001)
STANDING = ("PyPI is refused by the standing decision, TestPyPI until 1.0 (the operator's to lift): a release "
            "goes to TestPyPI alone, published by its tag's push -- nothing was changed")
#: the words each command takes, in any order; `test` names the one index and changes nothing
RELEASE_WORDS = ("--full", "yes")
TAKE_WORDS = ("--full", "main", "yes")
NOT_A_RELEASE_WORD = ("'{word}' is not an argument of release: '--full' (the full proof), 'yes' (the dry form), "
                      "both, or neither -- nothing was changed")
NOT_A_TAKE_WORD = ("'{word}' is not an argument of release-take: '--full' (the full proof), 'main' (the take pushes "
                   "develop to main too), 'yes' (the dry form), any of them, or none")
NOT_A_PROBE_WORD = "'{word}' is not an argument of the probes: 'light' (the default) or 'full' -- nothing was changed"
SHAPE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(\.dev[0-9]+)?$")
MAINTENANCE = re.compile(r"^release/[0-9]+\.[0-9]+")
NOT_NOW = 75
CHANGES = Path("docs") / "CHANGES.md"
CHANGES_HEADER = "| Stage | Landed | Released in | Squash subject |"
UNRELEASED = "not yet"
#: the line a fully proven release's annotated tag message carries; the advisory measures from the newest such tag
FULLY_PROVEN = "fully proven: full-test"
#: what only the full proof exercises (FR-002a): the runtimes' and identity plugins' sources, the release and take
#: tooling (with the three scripts the full proof alone runs to its end: the families' overlay under every live
#: command, with the index options it runs with, kept in the umbrella's extras module; the development pin's
#: resolution; the sessions' minutes), the starters' workflows, the contract and the SDK. An entry ending in "/"
#: is a tree; `*` is a glob.
FULL_PROOF_PATHS = (
    "packages/*-runtime-plugin/",
    "packages/docker-plugin/",
    "packages/posix-identity-plugin/",
    "scripts/release.py",
    "scripts/publish-dist",
    "scripts/release-watch",
    "scripts/with-released-families",
    "src/cs_image_system/extras.py",
    "scripts/dev-pin-resolves",
    "scripts/session-minutes-left",
    "docs/examples/_skeleton/Justfile",
    "docs/examples/*/.github/",
    "packages/contract/",
    "packages/base/",
    "packages/hashicorp-utils/",
    "packages/tofu-roots/",
)
#: the advisory, after "release: ": printed before anything changes, never a refusal
ADVISE = "a full proof is probably needed: {paths}; run with --full"
PROVEN_SINCE = "{paths} changed since {since}, the newest fully proven release"
NEVER_PROVEN = "{paths} changed since the first tag, {since} (no tag here records a full proof)"
NO_TAG = "no release tag here to measure the changes from"
APPLYING = "the take pushes the reference's main, an applying cycle there"
UNMEASURED = "the changes since {since} could not be read (git diff, exit {rc})"
#: how many changed paths the advisory names before it counts the rest
SHOWN = 8
#: the probes' one-line verdicts, after "<who>: "
VENV_OK = "the venv is in step with the lock"
SESSIONS_OK = "every runtime session of the live configuration is present"
#: the own-version probe's refusals, after "<who>: ", below scripts/own-versions-current's own lines
UNBUMPED = ("a package whose version the release does not move changed since TestPyPI took that version (above), "
            "so the publish workflow's upload would be refused after the tag -- bump that package's own version "
            "and commit it -- nothing was changed")
UNASKED = ("TestPyPI could not be asked whether it holds this tree's build of every package whose version the "
           "release does not move, or one could not be built (above); nothing is guessed -- nothing was changed")
#: the released-elsewhere probe's refusals, after "<who>: ", below scripts/with-released-families' own lines
ELSEWHERE_UNMET = ("the umbrella's extras name a family released from its own repository by a range TestPyPI holds "
                   "no release inside (above), so the release could not pin it and an install of that extra would "
                   "fail -- release the family, or move the range in pyproject.toml -- nothing was changed")
ELSEWHERE_PINNED = ("the tree already pins a family released from its own repository exactly ({pins}); a release "
                    "pins each range itself, at the family's newest TestPyPI release, and puts the range back after "
                    "its tag, so a tree left pinned would ship that version again -- put the range back in "
                    "pyproject.toml, run `uv lock` and commit both -- nothing was changed")
ELSEWHERE_UNASKED = ("TestPyPI could not be asked whether it holds a release inside each range the umbrella's extras "
                     "name for a family released from its own repository (above); nothing is guessed -- nothing was "
                     "changed")
#: the surface probe's refusal, after "<who>: ", below `just surface-check`'s own lines
SURFACE = ("a declared surface of the SDK and its baseline disagree (above): an entry removed or altered needs a new "
           "middle number (`just sdk-bump <line> middle`, then `just surface-record`); an entry added needs only to be "
           "recorded (`just surface-record`) -- nothing was changed")
DEVELOP = "develop"
REMOTE = "origin"
SYNC = ("uv", "sync", "--all-extras", "--no-extra", "gcloud", "--no-extra", "okta", "--no-extra", "all")
#: the dry form's lines, after "release: ": one per branch move, push and resync the real form would make
WOULD = "dry -- would run: {command}"
#: the refusals of the move from develop, after "release: "
NO_BRANCH = "there is no local branch {cut} to cut the release on (git branch {cut} origin/{cut}) -- nothing was changed"
NO_FAST_FORWARD = ("{cut} cannot be fast-forwarded to develop: it holds commits develop does not -- reconcile the two "
                   "first -- nothing was changed")
NO_REMOTE = "this checkout has no remote '{remote}' to push the release to (git remote -v) -- nothing was changed"
#: the fetch probe, after "<who>: ": origin asked whether it holds commits a branch the ending pushes lacks
NO_FETCH = ("`git fetch {remote}` failed (above), so whether {remote} holds commits this checkout lacks is unknown "
            "-- nothing was changed")
BEHIND_ORIGIN = ("{remote}/{branch} holds {count} commit(s) the local {branch} lacks, so its push after the tag "
                 "would be refused -- bring {branch} up first: git checkout {branch} && git merge --ff-only "
                 "{remote}/{branch} (reconcile the two when that cannot fast-forward), then run the same command "
                 "again -- nothing was changed")
LEVEL_WITH_ORIGIN = "{remote} holds no commit the local {branches} lacks (fetched)"
#: the tags probe, after "<who>: ": informational, never a refusal -- the ending pushes v<version> alone
TAGS_BEHIND = "local annotated tags {remote} lacks stay behind (the ending pushes v{version} alone): {tags}"
TAGS_UNASKED = ("`git ls-remote --tags {remote}` failed ({reason}), so the local tags {remote} lacks are not named; "
                "the ending pushes v{version} alone")
SYNC_FAILED = "`uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all` failed (above) -- nothing was changed"
#: what a refusal or a failure before the bump adds, after "release: ", once the release had moved the checkout
BACK = "the checkout is back on {branch}, and {cut} is where it was"
NOT_BACK = "the checkout could not return to {branch} (git checkout {branch}, above); it is on {cut}"
#: the dry form's venv verdict when it is behind: the real form syncs before it asks
VENV_WILL_SYNC = "the venv is behind the checkout; the real form syncs it (uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all) before it asks"
#: a failed step of the ending, after "<who>: ": the version is committed and tagged here, and on no index yet
ENDING_FAILED = ("{version} is committed and tagged v{version} here, but `{failed}` failed (above); nothing is on "
                 "TestPyPI until the tag is pushed; the rest, by hand: {rest}")
#: a failed step between the tag and the ending, while the released families were put back on their ranges,
#: after "<who>: ": the same state, with the ranges written to pyproject.toml and not yet committed
RESTORE_FAILED = ("{version} is committed and tagged v{version} here, but `{failed}` failed (above) while the "
                  "released families were put back on their ranges (pyproject.toml holds the ranges, uncommitted); "
                  "nothing is pushed, and nothing is on TestPyPI until the tag is pushed; the rest, by hand: {rest}")
#: the closing line: what was pushed, the branch the checkout ends on, and the push that publishes
RELEASED = ("release: {version} is committed, tagged v{version} and pushed: {pushed}; the checkout is on {branch} "
            "with its venv synced (uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all); the tag's "
            "push publishes it to TestPyPI by trusted publishing (`just release-watch {version}` waits on the runs)")
#: the take's own environment: a tree's take is the recipe of the release it is on, and uv answers an install
#: from the index page it cached before the upload unless told to ask afresh; every recipe's install honours it
TAKE_ENV = {"UV_REFRESH": "1"}
NO_TAKE_TREE = "no live configuration to take the release in at {root} ({why}) -- nothing was changed"
NOT_READ_BACK = ("the release ended, but the version it cut could not be read back here (v{version} is not tagged) "
                 "-- the take did not run; run it by hand: cd {root} && {command}")
#: release-take's wait for the publish workflow's upload, after "release-take: "
WAITING = ("waiting for TestPyPI to list cs-image-system {version} (scripts/index-knows, every {interval} seconds, "
           "{minutes} minutes at most): the tag's push publishes it")
LISTED = "TestPyPI lists cs-image-system {version}"
NOT_LISTED = ("{version} is released and pushed (above), but TestPyPI did not list it within {minutes} minutes -- the "
              "take did not run; `just release-watch {version}` says how the publish run went; once TestPyPI lists "
              "it, finish the take there: cd {root} && {command}")
TAKE_STOPPED = ("{version} is released and pushed (above), but the take in {root} stopped (exit {rc}; its own lines "
                "above say why and what to do). The release is done and never runs again; finish the take there: "
                "cd {root} && {command} (with `patched` after a refresh by hand, as it said)")
TAKEN = ("{version} is released here and taken in {root}{main}; `just release-watch {version}` waits on the runs "
         "they started")
TAKEN_MAIN = ", main pushed there too (main performs)"


def take_line(version: str, main: bool) -> str:
    """The take as a line to run by hand in the live configuration, its environment first."""
    return " ".join([*(f"{k}={v}" for k, v in TAKE_ENV.items()), "just", "take", version, *(["main"] if main else [])])


def published_members(root: Path) -> list[Path]:
    """The workspace members the publish workflow uploads: every ``packages/*/pyproject.toml`` but the ones
    classified ``Private :: Do Not Upload`` (the workspace-only plugins, built with the rest and never uploaded)."""
    return sorted(p for p in root.glob("packages/*/pyproject.toml") if "Private :: Do Not Upload" not in p.read_text())


def full_proof_paths(changed: Iterable[str]) -> list[str]:
    """The changed paths, in their order, that ``FULL_PROOF_PATHS`` lists (a tree's entry takes every path
    under it)."""
    patterns = [entry + "*" if entry.endswith("/") else entry for entry in FULL_PROOF_PATHS]
    return [path for path in changed if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)]


# ------------------------------------------------------------------ the shell

@dataclass(frozen=True)
class Done:
    rc: int
    out: str = ""
    err: str = ""


Run = Callable[..., Done]


def run(cmd: list[str], *, cwd: Path | None = None, capture: bool = True, env: Mapping[str, str] | None = None) -> Done:
    """Run one command. ``capture`` holds its output for the caller; without
    it the command's output flows to the terminal (the gate, the pushes)."""
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


def commit_evidence(tree: SiblingTree, version: str, *, run: Run = run) -> None:
    """The modification-test evidence, committed in the live configuration when it changed (``--full``)."""
    git = ["git", "-C", str(tree.path)]
    added = run([*git, "add", "meta-state/mod-tests.yaml"])
    if added.rc != 0:
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
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    index_interval: int = 30                          #: release-take's wait: seconds between asks of TestPyPI
    index_wait_minutes: int = 60                      #: and how long it waits at most
    planned: str = field(default="", init=False)      #: the version the last `release` call planned

    # --- helpers

    def git(self, *args: str, capture: bool = True) -> Done:
        return self.run(["git", *args], cwd=self.root, capture=capture)

    def index_name(self, index: str, who: str) -> str:
        """The index a word names: ``test`` is TestPyPI, the one index until 1.0; ``pypi`` is refused, naming
        the standing decision."""
        if index == "pypi":
            raise Refused(f"{who}: {STANDING}", 2)
        if index != INDEX:
            raise Refused(f"{who}: the index is test (TestPyPI), not '{index}' -- nothing was changed", 2)
        return NAME

    def words(self, who: str, words: Iterable[str], allowed: tuple[str, ...], refusal: str) -> set[str]:
        """The command's words, any order: ``pypi`` is refused first, wherever it stands, before anything is
        asked; ``test`` (the one index) and ``no`` (the real form, the old default) change nothing; any other
        word outside ``allowed`` is refused by name."""
        words = list(words)
        if "pypi" in words:
            self.index_name("pypi", who)
        got: set[str] = set()
        for word in words:
            if word in (INDEX, "no"):
                continue
            if word not in allowed:
                raise Refused(f"{who}: {refusal.format(word=word)}", 2)
            got.add(word)
        return got

    def current_version(self, who: str) -> str:
        done = self.run(["uv", "run", "--no-sync", "bump-my-version", "show", "current_version"], cwd=self.root)
        if done.rc != 0:
            raise Refused((done.err + done.out).strip() or f"{who}: bump-my-version could not show the current version",
                          done.rc or 2)
        return done.out.strip()

    def branch_guard(self, who: str) -> str:
        """The branch the checkout is on: the release branch with develop an ancestor of it, a maintenance
        branch, or develop (the release then moves to the release branch itself); any other branch is refused
        by name."""
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD").out.strip()
        if branch == self.release_branch:
            dev = DEVELOP
            if self.git("rev-parse", "-q", "--verify", DEVELOP).rc != 0:
                dev = f"{REMOTE}/{DEVELOP}"
            if self.git("merge-base", "--is-ancestor", dev, "HEAD").rc != 0:
                raise Refused(f"{who}: {self.release_branch} is behind {dev} -- a release never leaves a stage "
                              f"behind; run the release from {DEVELOP} (it fast-forwards {self.release_branch} "
                              f"itself), or first, on {self.release_branch}: git merge --ff-only {dev} -- nothing "
                              "was changed")
            return branch
        if MAINTENANCE.match(branch):
            self.say(f"{who}: on the maintenance branch {branch} (an old version's fix; develop is not checked)")
            return branch
        if branch == DEVELOP:
            return branch
        raise Refused(f"{who}: this checkout is on '{branch}'; a release is cut on {self.release_branch} alone (from "
                      f"{DEVELOP} it moves there itself) (or a maintenance branch release/<major.minor>) -- nothing "
                      "was changed")

    def cut_branch(self, start: str) -> str:
        """The branch the release is cut on: the release branch for a start on develop, else the start."""
        return self.release_branch if start == DEVELOP and start != self.release_branch else start

    def clean_or_refuse(self) -> None:
        dirty = self.git("status", "--porcelain").out.strip()
        if dirty:
            raise Refused("release: the working tree must be clean -- commit these changes, or discard them (git "
                          "restore, or git stash); the guard counts every tracked change and every file git does not "
                          "ignore:\n" + dirty)

    def remote_or_refuse(self, who: str) -> None:
        if self.git("remote", "get-url", REMOTE).rc != 0:
            raise Refused(f"{who}: {NO_REMOTE.format(remote=REMOTE)}")

    def pushed_branches(self, cut: str) -> list[str]:
        """The branches the ending pushes: the one the release is cut on and, for the release branch, develop."""
        return [cut, DEVELOP] if cut == self.release_branch else [cut]

    def fetched_or_refuse(self, who: str, cut: str) -> None:
        """`git fetch origin`, then every branch the ending pushes holds whatever its origin counterpart holds: a
        commit there that the local branch lacks would refuse the push after the tag. A local branch ahead
        of origin passes (the ending pushes it); a branch absent on either side has nothing to compare."""
        fetched = self.git("fetch", "-q", REMOTE)
        if fetched.rc != 0:
            for line in (fetched.err + fetched.out).splitlines():
                if line.strip():
                    self.say(line)
            raise Refused(f"{who}: {NO_FETCH.format(remote=REMOTE)}", fetched.rc)
        branches = self.pushed_branches(cut)
        for branch in branches:
            local = self.git("rev-parse", "-q", "--verify", f"refs/heads/{branch}").out.strip()
            theirs = self.git("rev-parse", "-q", "--verify", f"refs/remotes/{REMOTE}/{branch}").out.strip()
            if not local or not theirs:
                continue
            count = self.git("rev-list", "--count", f"{local}..{theirs}").out.strip()
            if count and count != "0":
                raise Refused(f"{who}: {BEHIND_ORIGIN.format(remote=REMOTE, branch=branch, count=count)}")
        self.say(f"{who}: {LEVEL_WITH_ORIGIN.format(remote=REMOTE, branches=' or '.join(branches))}")

    def tags_behind(self, who: str, version: str) -> None:
        """Informational, never a refusal: the local annotated tags origin lacks (``git ls-remote --tags``,
        asked of the origin the fetch probe just reached), which stay behind since the ending pushes
        ``v<version>`` alone -- or ``none``. Said so the operator sees them before the cut: pushed with
        the release, more than three tags at once would start no tag run on GitHub."""
        listed = self.git("for-each-ref", "--format=%(objecttype) %(refname:strip=2)", "refs/tags").out
        annotated = [name for kind, _, name in (line.partition(" ") for line in listed.splitlines()) if kind == "tag"]
        remote = self.git("ls-remote", "--tags", REMOTE)
        if remote.rc != 0:
            reason = "; ".join(ln.strip() for ln in (remote.err + remote.out).splitlines() if ln.strip())
            reason = reason or f"exit {remote.rc}"
            self.say(f"{who}: {TAGS_UNASKED.format(remote=REMOTE, reason=reason, version=version)}")
            return
        theirs = {ref.removeprefix("refs/tags/").removesuffix("^{}")
                  for ref in (line.partition("\t")[2] for line in remote.out.splitlines()) if ref}
        behind = [name for name in annotated if name not in theirs]
        self.say(f"{who}: {TAGS_BEHIND.format(remote=REMOTE, version=version, tags=', '.join(behind) or 'none')}")

    def release_tags(self) -> list[tuple[str, bool]]:
        """Every annotated release tag ``v<version>`` here, newest version first, each with whether its message
        records a full proof (the line ``FULLY_PROVEN``). One ``git for-each-ref``; a tag whose name is no
        version is left out."""
        from packaging.version import InvalidVersion, Version

        done = self.git("for-each-ref", "--format=%(refname:strip=2)%00%(objecttype)%00%(contents)%00", "refs/tags/v*")
        fields = done.out.split("\0")
        tags: list[tuple[Version, str, bool]] = []
        for i in range(0, len(fields) - 2, 3):
            name, kind, message = fields[i].strip(), fields[i + 1], fields[i + 2]
            if kind != "tag":
                continue
            try:
                version = Version(name[1:])
            except InvalidVersion:
                continue
            tags.append((version, name, FULLY_PROVEN in message.splitlines()))
        return [(name, proven) for _, name, proven in sorted(tags, reverse=True)]

    def advise(self, who: str, *, applying: bool = False) -> None:
        """The advisory (specification 013, FR-002a), said before anything changes and never a refusal: the
        paths changed since the newest release tag whose message records a full proof (with none, since the
        first tag, and said so), when ``FULL_PROOF_PATHS`` lists one; and a take that pushes the reference's
        main, an applying cycle there. Silent when neither holds."""
        reasons: list[str] = []
        tags = self.release_tags()
        proven = next((name for name, full in tags if full), "")
        since = proven or (tags[-1][0] if tags else "")
        if not since:
            reasons.append(NO_TAG)
        else:
            diff = self.git("diff", "--name-only", since, "HEAD")
            if diff.rc != 0:
                self.say(f"{who}: {UNMEASURED.format(since=since, rc=diff.rc)}")
            else:
                listed = full_proof_paths(line for line in diff.out.splitlines() if line.strip())
                if listed:
                    shown = ", ".join(listed[:SHOWN]) + (f" and {len(listed) - SHOWN} more" if len(listed) > SHOWN
                                                         else "")
                    reasons.append((PROVEN_SINCE if proven else NEVER_PROVEN).format(paths=shown, since=since))
        if applying:
            reasons.append(APPLYING)
        if reasons:
            self.say(f"{who}: {ADVISE.format(paths='; '.join(reasons))}")

    def fast_forward_or_refuse(self, cut: str) -> str:
        """The release branch's commit, once it is known to fast-forward to develop; read from the refs alone."""
        old = self.git("rev-parse", "-q", "--verify", f"refs/heads/{cut}").out.strip()
        if not old:
            raise Refused(f"release: {NO_BRANCH.format(cut=cut)}")
        if self.git("merge-base", "--is-ancestor", old, DEVELOP).rc != 0:
            raise Refused(f"release: {NO_FAST_FORWARD.format(cut=cut)}")
        return old

    def move(self, cut: str) -> list[list[str]]:
        """From develop: the release branch checked out and fast-forwarded to develop."""
        return [["git", "checkout", cut], ["git", "merge", "--ff-only", DEVELOP]]

    def ending(self, cut: str, version: str) -> list[list[str]]:
        """After the tag, in order: the branch the release was cut on and the tag ``v<version>`` pushed by name,
        so no other local tag travels with them (GitHub starts no tag run when more than three tags are pushed
        at once); for the release branch, develop checked out, fast-forwarded to it and pushed; then the venv
        synced to what is checked out (a maintenance branch's develop is never touched)."""
        steps = [["git", "push", REMOTE, cut, f"v{version}"]]
        if cut == self.release_branch:
            steps += [["git", "checkout", DEVELOP], ["git", "merge", "--ff-only", cut], ["git", "push", REMOTE, DEVELOP]]
        return [*steps, list(SYNC)]

    def ends_on(self, cut: str) -> str:
        return DEVELOP if cut == self.release_branch else cut

    def sync(self, who: str) -> None:
        """The venv brought to the checkout: a branch switch rewrites the files the branches differ in."""
        done = self.run(list(SYNC), cwd=self.root, capture=False)
        if done.rc != 0:
            raise Refused(f"{who}: {SYNC_FAILED}", done.rc)

    def go_back(self, start: str, cut: str, old: str, refused: Refused) -> Refused:
        """A refusal before the bump, after the move from develop: develop checked out again and the release
        branch's ref put back where it was; the refusal says so."""
        if self.git("checkout", start).rc != 0:
            note = NOT_BACK.format(branch=start, cut=cut)
        else:
            self.git("branch", "-f", cut, old)
            note = BACK.format(branch=start, cut=cut)
        return Refused((refused.message + "\n" if refused.message else "") + f"release: {note}", refused.code)

    def run_ending(self, who: str, version: str, cut: str) -> str:
        """The ending's steps, each shown as it runs; the first that fails is refused with the rest named.
        Returns what was pushed and moved, for the closing line."""
        steps = self.ending(cut, version)
        for i, cmd in enumerate(steps):
            done = self.run(cmd, cwd=self.root, capture=False)
            if done.rc != 0:
                rest = " && ".join(" ".join(c) for c in steps[i:])
                raise Refused(f"{who}: " + ENDING_FAILED.format(version=version, failed=" ".join(cmd), rest=rest),
                              done.rc or 1)
        return self.closing_line(cut, version)

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

    def ready_or_refuse(self, version: str) -> None:
        """scripts/publish-target-ready --refuse-held: TestPyPI answers (the publish workflow uploads there) and no
        project holds the version (an index never takes one twice). First of the probes and again after the gate.
        75 is "not now"; 1 is a version some project already holds (never re-cut); any other, "could not run"."""
        rc = self.run(["uv", "run", "--no-sync", "python", str(HERE / "publish-target-ready"), INDEX,
                       "--version", version, "--refuse-held", "--quiet"], cwd=self.root, capture=False).rc
        if rc == 0:
            return
        if rc == NOT_NOW:
            raise Refused(f"release: {NAME} cannot take an upload now (above) -- nothing was changed; it is the index's "
                          f"condition, not the release's: `just index-ready {INDEX} wait` waits for it", NOT_NOW)
        if rc == 1:
            raise Refused(f"release: {version} is already on {NAME} (above) -- a version is never re-cut")
        raise Refused(f"release: the publish-target probe could not run (exit {rc})", 2)

    def tagged(self, version: str) -> bool:
        return bool(self.git("tag", "-l", f"v{version}").out.strip())

    # --- the probes

    def own_versions_or_refuse(self, who: str) -> None:
        """scripts/own-versions-current, its lines said: every package whose version the release does not move
        (the bump's `glob_exclude`: the contract and the SDK's members) is either not on TestPyPI (it goes up
        fresh) or held there as exactly this tree's build, file for file and byte for byte (the upload skips it).
        Exit 1 is a package that changed under a version TestPyPI holds: refused, since TestPyPI would refuse its
        upload after the tag. Any other failure is refused as "could not ask" (exit 2), never guessed."""
        done = self.run(["uv", "run", "--no-sync", "python", str(HERE / "own-versions-current"), INDEX,
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

    def released_elsewhere_or_refuse(self, who: str) -> None:
        """First scripts/with-released-families --pinned: the tree names each family released from its own
        repository by a range, never by an exact pin a release left behind (``pin_released_families`` leaves an
        exact pin as it finds it, so such a tree would ship that version again); a pin is refused by name.
        Then --check test, its lines said: every range by which the umbrella's
        extras name a family released from its own repository (the Google Cloud family, the Okta plugin) holds a
        release on TestPyPI, where the families release until 1.0 and where the release pins each extra at its
        newest (``pin_released_families``). Exit 1 is a range nothing on TestPyPI meets (the extra could not be
        pinned nor installed); any other failure is refused as "could not ask" (exit 2), never guessed."""
        pinned = self.run(["uv", "run", "--no-sync", "python", str(HERE / "with-released-families"), "--pinned"],
                          cwd=self.root)
        if pinned.rc != 0:
            for line in (pinned.out + pinned.err).splitlines():
                if line.strip():
                    self.say(line)
            raise Refused(f"{who}: {ELSEWHERE_UNASKED}", 2)
        left = [line.strip() for line in pinned.out.splitlines() if line.strip()]
        if left:
            raise Refused(f"{who}: {ELSEWHERE_PINNED.format(pins=', '.join(left))}", 1)
        done = self.run(["uv", "run", "--no-sync", "python", str(HERE / "with-released-families"), "--check", INDEX],
                        cwd=self.root)
        for line in (done.out + done.err).splitlines():
            if line.strip():
                self.say(line)
        if done.rc == 0:
            return
        raise Refused(f"{who}: {ELSEWHERE_UNMET if done.rc == 1 else ELSEWHERE_UNASKED}", 1 if done.rc == 1 else 2)

    def surfaces_or_refuse(self, who: str) -> None:
        """`just surface-check`: each SDK library (the kit, the two terraform libraries) keeps its version rule
        against its committed baseline. An entry of a declared surface removed or altered while the library's
        middle number stands still is refused here, with the entry named, before anything is built: a provider
        that pins the range of that middle number would otherwise receive a release that breaks it."""
        done = self.run(["just", "surface-check"], cwd=self.root)
        if done.rc == 0:
            return
        for line in (done.out + done.err).splitlines():
            if line.strip():
                self.say(line)
        raise Refused(f"{who}: {SURFACE}", 1)

    def probes(self, *words: str | bool, will_sync: bool = False) -> None:
        """What a release needs and its gate only finds out twenty minutes in, asked first and in one line each:
        the venv is in step with the lock (``SYNC`` with `--check`), because every recipe runs `uv run --no-sync`
        and a venv behind the checkout answers with stale metadata; every package whose version the release does
        not move is fresh on TestPyPI or held there as this tree's build (`own_versions_or_refuse`: an index never
        takes a second build under a version, so a changed package without its own bump would be refused at the
        publish workflow's upload, after the tag); every family released from its own repository is on TestPyPI
        inside the range the extras name (`released_elsewhere_or_refuse`); the SDK's surfaces; docker answers (the
        install check of the lighter check and full-test's legs both need it). Under the full proof (``True``,
        ``full`` or ``--full``) also: the live configuration is present and every runtime session of it is present
        (`just preflight`, the gate full-test itself uses: without it the live legs would be skipped, which a
        release cannot accept) and how many minutes the soonest-expiring session has left
        (scripts/session-minutes-left; refused only when a token has already lapsed, otherwise said). ``pypi`` is
        refused, naming the standing decision, before anything is asked. The real form of `release` syncs the
        venv just before; its dry form (``will_sync``) says a venv behind the checkout rather than refusing it,
        since the real form would sync it first."""
        who = "release"
        full, named = False, []
        for word in words:
            if isinstance(word, bool) or word in ("full", "--full"):
                full = full or word is not False
            elif word != "light":
                named.append(word)
        self.words(who, named, (), NOT_A_PROBE_WORD)
        # the venv asked is the one running this script: the checkout's own, named when it is behind
        if self.run([*SYNC, "--check"], cwd=REPO).rc != 0:
            if not will_sync:
                raise Refused(f"{who}: the venv of {REPO} is behind its checkout ({' '.join(SYNC)} --check) -- "
                              "`just init` there syncs it -- nothing was changed")
            self.say(f"{who}: {VENV_WILL_SYNC}")
        else:
            self.say(f"{who}: {VENV_OK}")
        self.own_versions_or_refuse(who)
        self.released_elsewhere_or_refuse(who)
        self.surfaces_or_refuse(who)
        # both gates need the daemon: the lighter check's install check, full-test's legs; asked here, before
        # anything changes, and not found missing after the bar
        if self.run(["docker", "info"], cwd=self.root).rc != 0:
            needs = "full-test's legs need it" if full else "the quickstart page's run (test-quickstart) needs it"
            raise Refused(f"{who}: docker is not answering (docker info) -- {needs}; start the daemon "
                          "-- nothing was changed")
        self.say(f"{who}: docker answers")
        if not full:
            return
        root = self.sibling.path
        if not self.sibling.configured:
            raise Refused(f"{who}: no live configuration at {root} (`just config-guard` says why) -- full-test's live "
                          "legs need it -- nothing was changed")
        if self.run(["just", "preflight"], cwd=self.root).rc != 0:
            raise Refused(f"{who}: a runtime session of the live configuration is absent or expired (`just preflight` "
                          "says which) -- full-test's live legs would be skipped; log in -- nothing was changed")
        # how long the soonest-expiring session has left; a login lasts one hour and a full proof takes nearly
        # all of it; the tree may declare a family released from its own repository, layered in for the probe
        asked = self.run(["uv", "run", "--no-sync", "python", str(HERE / "with-released-families"),
                          "python", str(HERE / "session-minutes-left"), str(root)],
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
        """The files a bump changes, for the release commit: the manifests, the lock, the quickstart page and
        the starters' READMEs, whose installs name the release exactly (specification 002)."""
        members = sorted(str(p.relative_to(self.root)) for p in self.root.glob("packages/*/pyproject.toml"))
        page = ["docs/QUICKSTART.md"] if (self.root / "docs" / "QUICKSTART.md").is_file() else []
        starters = sorted(str(p.relative_to(self.root)) for p in self.root.glob("docs/examples/*/README.md"))
        return ["pyproject.toml", *members, *page, *starters, "uv.lock"]

    def gate(self, full: bool) -> None:
        """The lighter check by default: the acceptance tests (`just test`) and the quickstart page's own
        commands against this tree's wheels (`just test-quickstart`: what a newcomer runs must reach a dry run
        first; specification 002). Under ``full`` the full proof a PyPI release ran: full-test (which holds the
        page's run among its legs), the modification-test evidence in the live configuration and a clean live
        checkout. Nothing is tagged past a failed check."""
        if full:
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
            return
        for check in (["just", "test"], ["just", "test-quickstart"]):
            done = self.run(check, cwd=self.root, capture=False)
            if done.rc != 0:
                raise Refused("", done.rc)

    def bump(self, args: list[str]) -> None:
        for cmd in (["uv", "run", "--no-sync", "bump-my-version", *args], ["uv", "lock"]):
            done = self.run(cmd, cwd=self.root, capture=False)
            if done.rc != 0:
                raise Refused("", done.rc)

    def pin_released_families(self, who: str) -> None:
        """After the bump: every released-elsewhere name of the root's extras pinned exactly at the newest
        TestPyPI release inside its range (``with-released-families --newest test``), so the released umbrella
        names every one of the system's names exactly and the one install form takes each from TestPyPI
        (specification 013, D1). The ranges come back after the tag (``restore_released_ranges``)."""
        self.released_ranges = {}
        done = self.run(["uv", "run", "--no-sync", "python", str(HERE / "with-released-families"), "--newest", INDEX],
                        cwd=self.root)
        if done.rc != 0:
            raise Refused(f"{who}: the released families' newest TestPyPI releases could not be read (above) -- the "
                          "umbrella cannot name them exactly; the bump is uncommitted", done.rc)
        pins = dict(line.split("==", 1) for line in done.out.split() if "==" in line)
        if not pins:
            return
        path = self.root / "pyproject.toml"
        text = path.read_text()
        for name, version in pins.items():
            for spec in sorted(set(re.findall(rf'"{re.escape(name)}([<>=!~,.0-9a-z]*)"', text))):
                if not spec.startswith("=="):
                    self.released_ranges[f'"{name}=={version}"'] = f'"{name}{spec}"'
                    text = text.replace(f'"{name}{spec}"', f'"{name}=={version}"')
        path.write_text(text)
        self.say(f"{who}: the released families pinned for this release: "
                 + ", ".join(f"{n}=={v}" for n, v in sorted(pins.items())))
        self.lock_or_refuse(who)

    def restore_released_ranges(self, who: str, version: str, cut: str) -> None:
        """After the tag: the released families back on their ranges, the tree's own between releases, in a
        commit of its own on the release's branch. The release is committed and tagged by now and nothing is
        pushed, so a step that fails here (the lock, the add, the commit) is refused as a failed push is: with
        what is left by hand, these steps and then the ending's."""
        ranges = getattr(self, "released_ranges", {})
        if not ranges:
            return
        path = self.root / "pyproject.toml"
        text = path.read_text()
        for exact, spec in ranges.items():
            text = text.replace(exact, spec)
        path.write_text(text)
        steps = [["uv", "lock"], ["git", "add", "pyproject.toml", "uv.lock"],
                 ["git", "commit", "-q", "-m", f"after release {version}: the released families back on their ranges"]]
        for i, cmd in enumerate(steps):
            done = self.git(*cmd[1:]) if cmd[0] == "git" else self.run(cmd, cwd=self.root, capture=False)
            if done.rc != 0:
                for line in (done.err + done.out).splitlines():
                    if line.strip():
                        self.say(line)
                rest = " && ".join(shlex.join(c) for c in [*steps[i:], *self.ending(cut, version)])
                raise Refused(f"{who}: " + RESTORE_FAILED.format(version=version, failed=shlex.join(cmd), rest=rest),
                              done.rc or 1)

    def lock_or_refuse(self, who: str) -> None:
        done = self.run(["uv", "lock"], cwd=self.root, capture=False)
        if done.rc != 0:
            raise Refused(f"{who}: `uv lock` failed (above)", done.rc)

    def record_and_tag(self, version: str, *, on_release_branch: bool, full: bool) -> None:
        """The release's row in docs/CHANGES.md, the commit `release <version>` and the annotated tag, whose
        message carries ``FULLY_PROVEN`` when the release ran the full proof."""
        files = self.bumped_files()
        if append_release_row(self.root / CHANGES, version, self.today(), stamp_unreleased=on_release_branch):
            files.append(str(CHANGES))
        else:
            self.say(f"release: no {CHANGES} here to record {version} in")
        message = ["-m", f"release {version}", *(["-m", FULLY_PROVEN] if full else [])]
        for cmd in (["add", *files], ["commit", "-q", "-m", f"release {version}"],
                    ["tag", "-a", f"v{version}", *message]):
            done = self.git(*cmd)
            if done.rc != 0:
                raise Refused((done.err + done.out).strip() or f"release: git {cmd[0]} failed", done.rc)

    def closing_line(self, cut: str, version: str) -> str:
        """What the ending pushed and moved, as the commands it ran (the resync is said apart)."""
        return "; ".join(" ".join(cmd) for cmd in self.ending(cut, version)[:-1])

    # --- the commands

    def dry(self, start: str, cut: str, full: bool, plan: str, version: str) -> int:
        """The dry form's lines, in the real form's order: the move from develop (read from the refs, refused
        as the real form would refuse it), the resync, the probes, what the release would do, the ending."""
        before = [self.move(cut)] if start != cut else []
        if before:
            self.fast_forward_or_refuse(cut)
        for cmd in [*(c for group in before for c in group), list(SYNC)]:
            self.say(f"release: {WOULD.format(command=' '.join(cmd))}")
        self.probes(full, will_sync=True)
        self.say(plan)
        for cmd in self.ending(cut, version):
            self.say(f"release: {WOULD.format(command=' '.join(cmd))}")
        return 0

    def before_bump(self, start: str, cut: str, full: bool, new: str) -> None:
        """The move from develop, the resync, the venv's probes, the gate and the index again; a refusal or a
        failure in any of them returns the checkout to ``start`` with the release branch where it was."""
        old = ""
        if start != cut:
            old = self.fast_forward_or_refuse(cut)
        try:
            if old:
                for cmd in self.move(cut):
                    done = self.run(cmd, cwd=self.root, capture=False)
                    if done.rc != 0:
                        raise Refused(f"release: `{' '.join(cmd)}` failed (above)", done.rc)
            self.sync("release")
            self.probes(full)
            self.gate(full)
            # the gate takes minutes (full-test nearly an hour); an index that went down meanwhile leaves a clean tree
            self.ready_or_refuse(new)
        except Refused as e:
            if old:
                raise self.go_back(start, cut, old, e) from None
            raise

    def release(self, target: str, *words: str, applying: bool = False) -> int:
        """The release; ``words`` are ``--full`` (the full proof, recorded in the tag) and ``yes`` (the dry
        form), in any order; ``pypi`` is refused first. ``applying`` (release-take with ``main``) is a take into
        an applying cycle, which the advisory names."""
        said = self.words("release", words, RELEASE_WORDS, NOT_A_RELEASE_WORD)
        full, dry = "--full" in said, "yes" in said
        start = self.branch_guard("release")
        cut = self.cut_branch(start)
        if not dry:
            self.clean_or_refuse()
        current = self.current_version("release")
        new, bump_args = self.version_plan(target, current)
        self.planned = new
        self.ready_or_refuse(new)
        if self.tagged(new):
            raise Refused(f"release: v{new} is already tagged here -- a version is never re-cut, even after its files "
                          "were deleted from the index")
        self.remote_or_refuse("release")
        self.fetched_or_refuse("release", cut)
        self.tags_behind("release", new)
        if not full:
            self.advise("release", applying=applying)
        if dry:
            gate = "just full-test" if full else "just test, just test-quickstart"
            record = f" (its message: '{FULLY_PROVEN}')" if full else ""
            return self.dry(start, cut, full,
                            f"release: dry -- on {cut}, {current} would become {new}: {NAME} ready and free of it, "
                            f"untagged, the probes above passed. The real form: {gate}, the index again, "
                            f"bump-my-version {' '.join(bump_args)}, uv lock, the released families pinned at their "
                            f"newest TestPyPI releases, "
                            f"{'the modification-test evidence committed in the live configuration, ' if full else ''}"
                            f"commit 'release {new}' (with its {CHANGES} row), tag v{new}{record}, the families back "
                            "on their ranges, then the pushes below; the tag's push publishes it to TestPyPI", new)
        self.before_bump(start, cut, full, new)
        self.bump(bump_args)
        self.pin_released_families("release")
        if full:
            commit_evidence(read_sibling(self.sibling.path, run=self.run), new, run=self.run)
        self.record_and_tag(new, on_release_branch=cut == self.release_branch, full=full)
        self.restore_released_ranges("release", new, cut)
        pushed = self.run_ending("release", new, cut)
        self.say(RELEASED.format(version=new, pushed=pushed, branch=self.ends_on(cut)))
        return 0

    def take_tree_or_refuse(self) -> None:
        """The live configuration can take the release: configured, a git checkout, with a ``take`` recipe."""
        tree, root = self.sibling, self.sibling.path
        why = ""
        if not tree.configured:
            why = "no cfg/_config.yml; `just config-guard` says why"
        elif tree.branch is None:
            why = "not a git checkout"
        elif "take" not in self.run(["just", "--summary"], cwd=root).out.split():
            why = "its Justfile has no `take` recipe (just --summary there)"
        if why:
            raise Refused(f"release-take: {NO_TAKE_TREE.format(root=root, why=why)}")

    def knows_command(self, version: str) -> list[str]:
        return ["uv", "run", "--no-sync", "python", str(HERE / "index-knows"), INDEX_URL, PROJECT, version]

    def wait_listed(self, version: str, root: Path, line: str) -> None:
        """scripts/index-knows, asked every ``index_interval`` seconds until TestPyPI lists the umbrella at
        ``version`` (the publish workflow uploads it last), ``index_wait_minutes`` at most; then refused, with
        the take to run by hand once it is listed."""
        self.say(f"release-take: {WAITING.format(version=version, interval=self.index_interval, minutes=self.index_wait_minutes)}")
        deadline = self.clock() + self.index_wait_minutes * 60
        while True:
            done = self.run(self.knows_command(version), cwd=self.root)
            if done.rc == 0:
                self.say(f"release-take: {LISTED.format(version=version)}")
                return
            if self.clock() >= deadline:
                for said in (done.out + done.err).splitlines():
                    if said.strip():
                        self.say(said)
                raise Refused(f"release-take: {NOT_LISTED.format(version=version, minutes=self.index_wait_minutes, root=root, command=line)}")
            self.sleep(self.index_interval)

    def release_take(self, target: str, *words: str) -> int:
        """The release, then the wait for TestPyPI to list the version, then ``UV_REFRESH=1 just take
        <version>`` in the live configuration (``main`` passed through); the variable reaches the take alone."""
        said = self.words("release-take", words, TAKE_WORDS, NOT_A_TAKE_WORD)
        main = "main" in said
        dry = "yes" in said
        self.take_tree_or_refuse()
        root = self.sibling.path
        self.release(target, *(w for w in ("--full", "yes") if w in said), applying=main)
        if dry:
            self.say(f"release-take: {WOULD.format(command=' '.join(self.knows_command(self.planned)) + ' (until TestPyPI lists it)')}")
            self.say(f"release-take: {WOULD.format(command=f'cd {root} && {take_line(self.planned, main)}')}")
            return 0
        version = self.current_version("release-take")
        line = take_line(version, main)
        if not self.tagged(version):
            raise Refused(f"release-take: {NOT_READ_BACK.format(version=version, root=root, command=line)}")
        self.wait_listed(version, root, line)
        done = self.run(["just", "take", version, *(["main"] if main else [])], cwd=root, capture=False,
                        env={**self.env, **TAKE_ENV})
        if done.rc != 0:
            raise Refused(f"release-take: {TAKE_STOPPED.format(version=version, root=root, rc=done.rc, command=line)}",
                          done.rc)
        self.say(f"release-take: {TAKEN.format(version=version, root=root, main=TAKEN_MAIN if main else '')}")
        return 0


# ------------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="release.py", description=(__doc__ or "").splitlines()[0])
    ap.add_argument("command", choices=["release", "release-take", "probes"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--full", action="store_true", help="the full proof (full-test, the sessions, the evidence)")
    ap.add_argument("--release-branch", default="main")
    ap.add_argument("--config-root", default=None)
    ap.add_argument("--root", type=Path, default=None, help="the system checkout (default: the working directory)")
    ns = ap.parse_intermixed_args(argv)
    root = (ns.root or Path.cwd()).resolve()
    family = Family(root=root, sibling=read_sibling(ns.config_root), release_branch=ns.release_branch)
    words = [*ns.args, *(["--full"] if ns.full else [])]
    try:
        if ns.command == "release":
            if not ns.args:
                ap.error("release needs a version part or a version")
            return family.release(*words)
        if ns.command == "release-take":
            if not ns.args:
                ap.error("release-take needs a version part or a version")
            return family.release_take(*words)
        family.probes(*words)
        return 0
    except Refused as e:
        if e.message:
            print(e.message)
        return e.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
