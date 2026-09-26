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
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from importlib import metadata, resources
from pathlib import Path

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
)
RELEASE_OWNED_DIRS: tuple[str, ...] = (".github/workflows", "tfmodules")

_IGNORED = shutil.ignore_patterns(".DS_Store", "__pycache__", "generated", "_private")


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
    kept: list[str] = field(default_factory=list)       # already there, identical
    refused: list[str] = field(default_factory=list)    # already there, different, no --force

    @property
    def ok(self) -> bool:
        return not self.refused

    def lines(self) -> list[str]:
        what = "the whole tree" if self.whole_tree else "the release-owned parts"
        out = [f"init-config: {what} of {self.starter} ({self.version}) -> {self.destination}: "
               f"{len(self.written)} written, {len(self.kept)} kept as they were"]
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
        if not force:
            report.refused.append(rel)
            return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)          # the mode travels: the hook and the scripts are executable
    report.written.append(rel)


def init_config(destination: Path, starter: str = DEFAULT_STARTER, *, force: bool = False) -> InitReport:
    """Write a starter (or its release-owned parts) into ``destination``."""
    source = starter_path(starter)
    version = release_version()
    destination = destination.resolve()
    empty = not destination.exists() or (destination.is_dir() and not any(destination.iterdir()))
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"{destination} exists and is not a directory")
    report = InitReport(starter=starter, version=version, destination=destination, whole_tree=empty)
    if empty:
        shutil.copytree(source, destination, ignore=_IGNORED, dirs_exist_ok=True)
        report.written = sorted(str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file())
    else:
        for rel in release_owned_paths(source):
            _place(source / rel, destination / rel, rel, report, force=force)
    stamp = destination / VERSION_FILE
    text = version + "\n"
    if stamp.exists() and stamp.read_text() == text:
        if VERSION_FILE not in report.written:
            report.kept.append(VERSION_FILE)
    elif stamp.exists() and not force and not empty:
        report.refused.append(VERSION_FILE)
    else:
        stamp.write_text(text)
        if VERSION_FILE not in report.written:
            report.written.append(VERSION_FILE)
    return report
