# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The starter configuration repositories a release carries, and
``init-config``, which writes one out (stage 64 item 1).

A team installs a release and owns a configuration repository. What that
repository needs beyond its own YAML -- the ``Justfile``, the workflow, the
public-safe hook, ``.gitignore``, the terraform modules the emitted roots
call -- comes from the release, never from a clone of the system: the three
trees under the system's ``docs/examples/`` are the source, the build hook
(``packages/system/hatch_build.py``) ships them inside this package as
``starters/<name>/``, and this module finds them again on any machine.

Two forms of ``init-config``:

* a destination that does not exist or is empty takes the WHOLE starter, so a
  team begins from a tree that loads and validates as it stands;
* a destination that already holds a configuration takes only the parts the
  release owns (``RELEASE_OWNED``), so an existing repository -- the reference
  configuration, or a team's after an upgrade -- gains or refreshes them
  without a line of its YAML touched. A release-owned file that already
  exists and differs is refused by name unless ``force`` says to overwrite it.

Either way ``.csis-version`` records the running release, which is the pin
the starter workflow installs.

Refreshing an existing tree (hygiene IX item 1, found taking releases dev7
and dev8 into the reference configuration, where both times the diff had to
be undone by hand):

* the starter is the one the tree came from -- ``--from`` when given, else
  the starter whose workflow the tree's own ``.github/workflows/ci.yml`` is
  closest to (the trees differ only there) -- never silently the default:
  the reference configuration's workflow is ``complete``'s, and refreshing it
  from ``standard-aws`` dropped every GCP step;
* a team's values survive: wherever the release's file carries a
  ``REPLACE-ME`` placeholder and the tree's file has something else in that
  place, the tree's lines are kept (``carry_team_values``). A file that
  differs from the release ONLY there is current, and is kept without
  ``--force``; with ``--force`` the rest becomes the release's and the report
  counts the lines that changed;
* ``.csis-version`` never moves backwards: a tree that already pins a newer
  release than the one running (a development checkout whose installed
  metadata lags the bump, say) keeps its pin.
"""
from __future__ import annotations

import difflib
import shutil
from dataclasses import dataclass, field
from importlib import metadata, resources
from pathlib import Path

from packaging.version import InvalidVersion, Version

STARTERS: tuple[str, ...] = ("standard-aws", "standard-gce", "complete")
DEFAULT_STARTER = "standard-aws"
VERSION_FILE = ".csis-version"

# The parts of a configuration repository that the release owns: written into
# an existing tree by init-config, refreshed on an upgrade, and never a team's
# to edit (a team's values live in the YAML and the workflow's REPLACE-ME lines).
RELEASE_OWNED_FILES: tuple[str, ...] = (
    "Justfile",
    ".gitignore",
    ".githooks/pre-commit",
    "CI_SETUP.md",          # stage 69: the guide names the workflow's secrets, so it moves with the workflow
)
RELEASE_OWNED_DIRS: tuple[str, ...] = (".github/workflows", "tfmodules")

_IGNORED = shutil.ignore_patterns(".DS_Store", "__pycache__", "generated", "_private")

#: Where a release-owned file holds a team's value, the starter says so.
PLACEHOLDER_MARKS: tuple[str, ...] = ("REPLACE-ME", "REPLACE_ME")
WORKFLOW = ".github/workflows/ci.yml"


def _placeholder(line: str) -> bool:
    return any(m in line for m in PLACEHOLDER_MARKS)


def carry_team_values(release: str, tree: str) -> tuple[str, int, int]:
    """The release's text with the tree's lines kept wherever the release
    has a placeholder and the tree has something else there: ``(text,
    carried, replaced)`` -- how many of the tree's lines were kept as its
    values, and how many other lines of the tree now read as the release's
    (release changes, or local edits to a release-owned file)."""
    rel, own = release.splitlines(keepends=True), tree.splitlines(keepends=True)
    out: list[str] = []
    carried = replaced = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, rel, own, autojunk=False).get_opcodes():
        if tag == "equal":
            out.extend(rel[i1:i2])
        elif tag == "replace" and any(_placeholder(x) for x in rel[i1:i2]):
            comment = all(_placeholder(x) or x.lstrip().startswith("#") for x in rel[i1:i2])
            if i2 - i1 == j2 - j1 and not comment:  # line for line: a placeholder line is the team's
                for a, b in zip(rel[i1:i2], own[j1:j2]):
                    if _placeholder(a):
                        out.append(b)
                        carried += 1
                    else:
                        out.append(a)
                        replaced += 1
            else:                                   # a comment naming the placeholders, rewritten in the team's words
                out.extend(own[j1:j2])
                carried += j2 - j1
        elif tag in ("replace", "delete"):
            out.extend(rel[i1:i2])
            replaced += j2 - j1
        else:                                       # insert: lines only the tree has
            replaced += j2 - j1
    return "".join(out), carried, replaced


def infer_starter(destination: Path) -> str | None:
    """The starter an existing tree came from: the one whose workflow its own
    is closest to (the starters differ only there). None when the tree has
    no workflow to judge by."""
    mine = destination / WORKFLOW
    if not mine.is_file():
        return None
    own = mine.read_text().splitlines()

    def distance(name: str) -> tuple[int, int]:
        theirs = (starter_path(name) / WORKFLOW).read_text().splitlines()
        ops = difflib.SequenceMatcher(None, theirs, own, autojunk=False).get_opcodes()
        differing = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in ops if tag != "equal")
        return differing, STARTERS.index(name)
    return min(STARTERS, key=distance)


def release_version() -> str:
    """The running release, as ``.csis-version`` records it."""
    return metadata.version("cs-image-system-system")


def starters_root() -> Path:
    """Where the starter trees are: inside the installed package (what a
    release carries), else the workspace's ``docs/examples`` for an editable
    checkout, where the hook's copies land in site-packages and the source is
    what the tests hold the release to."""
    packaged = Path(str(resources.files("cs_image_system.system") / "starters"))
    if all((packaged / s).is_dir() for s in STARTERS):
        return packaged
    workspace = Path(__file__).resolve().parents[5] / "docs" / "examples"
    if all((workspace / s).is_dir() for s in STARTERS):
        return workspace
    raise RuntimeError(f"the starter trees are neither in the installed package ({packaged}) nor in a "
                       f"workspace checkout ({workspace}); the release is incomplete")


def starter_path(name: str) -> Path:
    if name not in STARTERS:
        raise ValueError(f"no starter named {name!r}; the release carries {', '.join(STARTERS)}")
    return starters_root() / name


def release_owned_paths(starter: Path) -> list[str]:
    """The release-owned files the starter carries, as paths relative to it."""
    out: list[str] = [f for f in RELEASE_OWNED_FILES if (starter / f).is_file()]
    for d in RELEASE_OWNED_DIRS:
        base = starter / d
        if base.is_dir():
            out.extend(str(p.relative_to(starter)) for p in sorted(base.rglob("*")) if p.is_file())
    return out


@dataclass
class InitReport:
    starter: str
    version: str
    destination: Path
    whole_tree: bool
    written: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)       # already there, identical (or different only in the team's values)
    refused: list[str] = field(default_factory=list)    # already there, different, no --force
    inferred: bool = False                              # the starter was read from the tree's workflow
    carried: dict[str, int] = field(default_factory=dict)     # file -> the team's lines kept
    replaced: dict[str, int] = field(default_factory=dict)    # file -> the tree's other lines now the release's
    version_note: str = ""

    @property
    def ok(self) -> bool:
        return not self.refused

    def lines(self) -> list[str]:
        what = "the whole tree" if self.whole_tree else "the release-owned parts"
        out = [f"init-config: {what} of {self.starter} ({self.version}) -> {self.destination}: "
               f"{len(self.written)} written, {len(self.kept)} kept as they were"]
        if self.inferred:
            out.append(f"init-config: the starter {self.starter} was read from the tree's {WORKFLOW} "
                       "(--from names another)")
        for rel, n in sorted(self.carried.items()):
            if n:
                out.append(f"init-config: {rel}: your values kept in {n} line(s) where the release has REPLACE-ME")
        for rel, n in sorted(self.replaced.items()):
            if n:
                out.append(f"init-config: {rel}: {n} other line(s) now read as the release's -- review the diff")
        if self.version_note:
            out.append(f"init-config: {self.version_note}")
        for r in self.refused:
            out.append(f"init-config: REFUSED {r}: it exists and differs from the release's; "
                       "--force overwrites it")
        return out


def _same(a: Path, b: Path) -> bool:
    return a.read_bytes() == b.read_bytes()


def _place(src: Path, dst: Path, rel: str, report: InitReport, *, force: bool) -> None:
    if dst.exists():
        if _same(src, dst):
            report.kept.append(rel)
            return
        # the team's values live in the workflows alone (the guide merely MENTIONS
        # REPLACE-ME, and an older guide is not the team's wording)
        release = src.read_text() if rel.startswith(".github/workflows/") else None
        if release is not None and any(_placeholder(x) for x in release.splitlines()):
            merged, carried, replaced = carry_team_values(release, dst.read_text())
            if merged == dst.read_text():           # different only in the team's values: current
                report.kept.append(rel)
                report.carried[rel] = carried
                return
            if not force:
                report.refused.append(rel)
                return
            dst.write_text(merged)
            shutil.copymode(src, dst)
            report.written.append(rel)
            report.carried[rel] = carried
            report.replaced[rel] = replaced
            return
        if not force:
            report.refused.append(rel)
            return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)          # the mode travels: the hook and the scripts are executable
    report.written.append(rel)


def _version(text: str) -> Version | None:
    try:
        return Version(text.strip())
    except InvalidVersion:
        return None


def init_config(destination: Path, starter: str | None = None, *, force: bool = False) -> InitReport:
    """Write a starter (or its release-owned parts) into ``destination``. With
    no ``starter``, a new tree takes the default and an existing one the
    starter its workflow came from."""
    version = release_version()
    destination = destination.resolve()
    empty = not destination.exists() or (destination.is_dir() and not any(destination.iterdir()))
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"{destination} exists and is not a directory")
    inferred = False
    if starter is None:
        found = None if empty else infer_starter(destination)
        starter, inferred = (found, True) if found else (DEFAULT_STARTER, False)
    source = starter_path(starter)
    report = InitReport(starter=starter, version=version, destination=destination, whole_tree=empty, inferred=inferred)
    if empty:
        shutil.copytree(source, destination, ignore=_IGNORED, dirs_exist_ok=True)
        report.written = sorted(str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file())
    else:
        for rel in release_owned_paths(source):
            _place(source / rel, destination / rel, rel, report, force=force)
    stamp = destination / VERSION_FILE
    text = version + "\n"
    pinned = _version(stamp.read_text()) if stamp.exists() else None
    running = _version(version)
    if stamp.exists() and stamp.read_text() == text:
        if VERSION_FILE not in report.written:
            report.kept.append(VERSION_FILE)
    elif stamp.exists() and not force and not empty:
        report.refused.append(VERSION_FILE)
    elif stamp.exists() and not empty and (pinned is None or running is None or pinned > running):
        # never backwards: a pin newer than the running release (or one that
        # cannot be compared) is the operator's, and stays
        report.kept.append(VERSION_FILE)
        report.version_note = (f"{VERSION_FILE} kept at {stamp.read_text().strip()}: "
                               + (f"newer than this install's {version}; a pin is never moved backwards"
                                  if pinned is not None and running is not None else
                                  f"it cannot be compared with {version}; change it by hand"))
    else:
        stamp.write_text(text)
        if VERSION_FILE not in report.written:
            report.written.append(VERSION_FILE)
    return report
