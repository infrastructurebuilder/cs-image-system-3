# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The starter configuration repositories a release carries, and
``init-config``, which writes one out.

A team installs a release and owns a configuration repository. What that
repository needs beyond its own YAML -- the ``Justfile``, the workflow, the
public-safe hook, ``.gitignore``, the terraform modules the emitted roots
call -- comes from the release, never from a clone of the system: the trees
under the system's ``docs/examples/`` are the source, the build hook
(``packages/system/hatch_build.py``) ships them inside this package as
``starters/<name>/``, and this module finds them again on any machine.

A starter is assembled from two parts (``render``):

* the **skeleton**, ``docs/examples/_skeleton/``: the files every starter
  shares byte for byte (the ``Justfile``, ``CI_SETUP.md``, the hook,
  ``.gitignore``, the TEST age identity and recipient, the base images'
  README), kept once;
* the starter's **overlay**, ``docs/examples/<name>/``: everything that is
  the starter's own (its YAML, its workflows, its README, its playbooks
  and scripts), laid over the skeleton; an overlay never repeats a
  skeleton file.

The terraform modules are in neither: they are package data of the plugins
that own them (``cs_image_system.base.modules``), and ``write_starter``
materialises the installed ones into the tree's ``module_source_base``
directory (every starter declares ``tfmodules``), each copy stamped so a
later ``init-config`` can tell an unmodified copy from an edited one. A
starters directory of the older layout -- whole trees, ``tfmodules/``
inside, no ``_skeleton`` -- still renders: each tree's files as they are.
``init-config --changes-since`` reads such a directory from an earlier
release's wheel.

Two forms of ``init-config``:

* a destination that does not exist, is empty, or is a fresh clone holding
  only ``.git`` takes the WHOLE starter, so a team begins from a tree that
  loads and validates as it stands;
* a destination that already holds a configuration takes only the parts the
  release owns (``RELEASE_OWNED``), so an existing repository -- the reference
  configuration, or a team's after an upgrade -- gains or refreshes them
  without a line of its YAML touched. A release-owned file that already
  exists and differs is refused by name unless ``force`` says to overwrite it.
  Any other directory -- one that holds things but no configuration -- is
  refused by name, and nothing is written.

Either way ``.csis-version`` records the running release, which is the pin
the starter workflow installs.

Refreshing an existing tree (found taking early releases into the reference
configuration, where each time the diff had to be undone by hand):

* the starter is the one the tree came from -- ``--from`` when given, else
  the starter whose workflow the tree's own ``.github/workflows/ci.yml`` is
  closest to (the trees differ only there) -- never silently the default:
  the reference configuration's workflow is ``complete``'s, and refreshing it
  from a narrower starter dropped every step the narrower one lacks;
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

import re

import difflib
import posixpath
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import metadata, resources
from pathlib import Path

import yaml
from packaging.version import InvalidVersion, Version

from cs_image_system.base.modules import (STAMP_FILE, ModulesReport, declared_overrides, installed_modules,
                                          materialise_modules)

from .starter_links import rewrite_tree

VERSION_FILE = ".csis-version"
#: The file beside the starter trees that names the one a new tree gets when
#: nobody chose; the trees themselves are the directories beside it that
#: carry a ``cfg/``. The release ships both, so the system carries no list
#: of starters of its own and names none.
DEFAULT_MARKER = "DEFAULT"
#: The directory beside the starters holding the files every starter shares;
#: it has no ``cfg/`` and is never a starter. Nothing else beside the starters
#: may start with an underscore.
SKELETON = "_skeleton"
#: The modules directory a tree gets when its ``cfg/_config.yml`` declares no
#: ``module_source_base``: the starters' own convention.
MODULES_DIR = "tfmodules"
#: Files that are never part of a starter: a run's output, the materialised
#: roots, Python's and Finder's litter.
_LITTER = (".DS_Store", "__pycache__", "generated", "_private")


def _is_starter(path: Path) -> bool:
    return path.is_dir() and not path.name.startswith("_") and (path / "cfg").is_dir()


def _starter_roots() -> list[Path]:
    """Where the starter trees may be: inside the installed package (what a
    release carries), else the workspace's ``docs/examples`` for an editable
    checkout, where the hook's copies land in site-packages and the source is
    what the tests hold the release to."""
    packaged = Path(str(resources.files("cs_image_system.system") / "starters"))
    workspace = Path(__file__).resolve().parents[5] / "docs" / "examples"
    return [packaged, workspace]


def starters_root() -> Path:
    for root in _starter_roots():
        if (root / DEFAULT_MARKER).is_file() and any(_is_starter(c) for c in root.iterdir()):
            return root
    raise RuntimeError(f"the starter trees are in none of {[str(r) for r in _starter_roots()]}; "
                       "the release is incomplete")


def default_starter(root: Path | None = None) -> str:
    """The starter a new tree gets when nobody chose: the marker file's one line."""
    root = root or starters_root()
    name = (root / DEFAULT_MARKER).read_text().strip()
    if not _is_starter(root / name):
        raise RuntimeError(f"{root / DEFAULT_MARKER} names {name!r}, which is not a starter tree beside it")
    return name


def starters(root: Path | None = None) -> tuple[str, ...]:
    """Every starter tree the release carries: the default first (a tie
    between equally close starters resolves to it), the rest by name."""
    root = root or starters_root()
    default = default_starter(root)
    others = sorted(c.name for c in root.iterdir() if _is_starter(c) and c.name != default)
    return (default, *others)


def _discovered() -> tuple[tuple[str, ...], str]:
    try:
        return starters(), default_starter()
    except (RuntimeError, OSError):          # an incomplete install: the commands say so when asked
        return (), ""


STARTERS, DEFAULT_STARTER = _discovered()

# The parts of a configuration repository that the release owns: written into
# an existing tree by init-config, refreshed on an upgrade, and never a team's
# to edit (a team's values live in the YAML and the workflow's REPLACE-ME lines).
RELEASE_OWNED_FILES: tuple[str, ...] = (
    "Justfile",
    ".gitignore",
    ".githooks/pre-commit",
    "CI_SETUP.md",          # the guide names the workflow's secrets, so it moves with the workflow
)
#: ``tfmodules`` stays in the list for a starters directory of the older
#: layout, where the modules were files of the tree (``changes_since``
#: compares such a directory); a rendered starter holds no modules.
RELEASE_OWNED_DIRS: tuple[str, ...] = (".github/workflows", MODULES_DIR)

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
                for a, b in zip(rel[i1:i2], own[j1:j2], strict=True):
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
        theirs = render_sources(name)[WORKFLOW].read_text().splitlines()
        ops = difflib.SequenceMatcher(None, theirs, own, autojunk=False).get_opcodes()
        differing = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in ops if tag != "equal")
        return differing, STARTERS.index(name)
    return min(STARTERS, key=distance)


def release_version() -> str:
    """The running release, as ``.csis-version`` records it."""
    return metadata.version("cs-image-system-system")


def source_tree_version() -> str | None:
    """The version a source checkout's ``packages/system/pyproject.toml``
    declares, when this module runs from one (an editable install); None
    from an installed wheel, where no such file sits beside the package."""
    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    if not pyproject.is_file():
        return None
    text = pyproject.read_text()
    if not re.search(r'^name = "cs-image-system-system"$', text, flags=re.M):
        return None
    m = re.search(r'^version = "([^"]+)"$', text, flags=re.M)
    return m.group(1) if m else None


def stale_install(installed: str | None = None, declared: str | None = None) -> str | None:
    """Why this install may not stamp a tree, or None. A checkout bumped by
    a release and not synced runs the new code under the old metadata, and
    init-config used to write the old version into `.csis-version` (found
    taking a release into the reference)."""
    installed = installed if installed is not None else release_version()
    declared = declared if declared is not None else source_tree_version()
    if declared is None or declared == installed:
        return None
    return (f"this checkout declares {declared} (packages/system/pyproject.toml) but its installed metadata says "
            f"{installed}: the checkout moved and the environment did not. Run `uv sync` (or `just init`) here, "
            "then init-config again. Nothing was written")


def starter_path(name: str) -> Path:
    """The starter's own directory (its overlay) under the release's
    starters; the whole starter is ``render(name)``."""
    if name not in STARTERS:
        raise ValueError(f"no starter named {name!r}; the release carries {', '.join(STARTERS) or 'no starter tree'}")
    return starters_root() / name


def release_owned_paths(starter: Path | Mapping[str, object]) -> list[str]:
    """The release-owned files a starter carries, as paths relative to it.

    ``starter`` is a rendered view (``render``'s mapping, or any mapping
    whose keys are the tree's relative paths) or a directory: an overlay
    beside a ``_skeleton`` is read with the skeleton under it, any other
    directory (a tree of the older layout, a written tree) as it is."""
    if isinstance(starter, Path):
        starter = _render_sources_of(starter)
    out: list[str] = [f for f in RELEASE_OWNED_FILES if f in starter]
    dirs = tuple(d + "/" for d in RELEASE_OWNED_DIRS)
    out.extend(rel for rel in sorted(starter) if rel.startswith(dirs))
    return out


# ------------------------------------------------------------- the render

def _tree_files(root: Path) -> dict[str, Path]:
    """Every file under ``root`` by its relative POSIX path, the litter left out."""
    out: dict[str, Path] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in _LITTER for part in rel.parts):
            continue
        out[rel.as_posix()] = p
    return out


def module_base_of(cfg_text: str | None) -> str | None:
    """The modules directory a tree's ``cfg/_config.yml`` text declares,
    normalised and relative to the tree, when it lies inside the tree
    (``tfmodules``, ``./tfmodules``, ``tools/modules``); None when it is
    absolute, leaves the tree (``../cs-image-system-3/tfmodules``) or names
    a remote source: such a base is the tree's own and no file is written
    for it. No declaration at all means ``MODULES_DIR``."""
    if cfg_text is None:
        return MODULES_DIR
    try:
        doc = yaml.safe_load(cfg_text) or {}
    except yaml.YAMLError:
        return None
    config = doc.get("config") if isinstance(doc, dict) else None
    base = config.get("module_source_base") if isinstance(config, dict) else None
    if base is None:
        return MODULES_DIR
    base = str(base).strip()
    if not base or base.startswith("/") or re.match(r"^[a-z][a-z0-9+.-]*:", base) or "::" in base:
        return None
    norm = posixpath.normpath(base)
    if norm in (".", "") or norm.startswith(".."):
        return None
    return norm


def _render_sources_of(directory: Path) -> dict[str, Path]:
    """A directory's files as a starter's: an overlay beside a ``_skeleton``
    is laid over it, with its modules directory left out (the modules are
    the plugins'); any other directory is read as it is."""
    skeleton = directory.parent / SKELETON
    if not (skeleton.is_dir() and _is_starter(directory)):
        return _tree_files(directory)
    files = _tree_files(skeleton)
    own = _tree_files(directory)
    cfg = own.get("cfg/_config.yml")
    base = module_base_of(cfg.read_text()) if cfg is not None else None
    for rel, p in own.items():
        if base and rel.startswith(base + "/"):
            continue
        files[rel] = p
    return dict(sorted(files.items()))


def render_sources(name: str, root: Path | None = None) -> dict[str, Path]:
    """``render`` with the source file of each path instead of its bytes
    (the file modes travel from them: the hook and the scripts are
    executable)."""
    root = root or starters_root()
    overlay = root / name
    if not _is_starter(overlay):
        known = ", ".join(c.name for c in sorted(root.iterdir()) if _is_starter(c))
        raise ValueError(f"no starter named {name!r}; {root} carries {known or 'no starter tree'}")
    return _render_sources_of(overlay)


def render(name: str, root: Path | None = None) -> dict[str, bytes]:
    """The starter ``name`` as one tree: every file by its relative POSIX
    path, with its bytes as the source holds them. Under ``root`` (the
    running release's starters when None): the skeleton's files, then the
    overlay's over them; under a root of the older layout, which has no
    ``_skeleton``, the starter's files as they are, its ``tfmodules/``
    included. The terraform modules of a current root are not here: they
    come from the installed plugins (``write_starter``)."""
    return {rel: p.read_bytes() for rel, p in render_sources(name, root).items()}


def _modules_written(modules_dir: Path, destination: Path) -> list[str]:
    return sorted(p.relative_to(destination).as_posix() for p in modules_dir.rglob("*") if p.is_file())


def _write_starter(name: str, destination: Path, version: str) -> tuple[list[str], list[str], ModulesReport | None]:
    """``write_starter``'s work: (the paths written, the Markdown files whose
    links were rewritten, the modules report or None when the tree's
    ``module_source_base`` is not a directory inside it)."""
    destination.mkdir(parents=True, exist_ok=True)
    sources = render_sources(name)
    for rel, src in sources.items():
        dst = destination / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)              # the mode travels: the hook and the scripts are executable
    written = list(sources)
    cfg = destination / "cfg" / "_config.yml"
    base = module_base_of(cfg.read_text() if cfg.is_file() else None)
    report = None
    if base:
        report = materialise_modules(destination / base, overrides=declared_overrides(destination))
        written.extend(_modules_written(destination / base, destination))
    # the starter's links into the system repository point at this release's
    # tag, since a relative one points nowhere in a repository of its own
    linked = rewrite_tree(destination, name, version)
    (destination / VERSION_FILE).write_text(version + "\n")
    written.append(VERSION_FILE)
    return sorted(set(written)), linked, report


def write_starter(name: str, destination: Path, *, version: str) -> list[str]:
    """Write the whole starter ``name`` into ``destination`` (created if
    absent; what is there is overwritten): the rendered tree, then the
    installed plugins' terraform modules into the tree's own
    ``module_source_base`` directory (each copy stamped with
    ``.csis-module``), then every Markdown link that leaves the starter
    pointed at the system repository at ``v<version>``, then
    ``.csis-version`` holding ``version``. Returns the relative paths
    written, sorted. This is what ``init-config`` writes into an empty
    destination and what ``scripts/starter-tree`` publishes."""
    written, _, _ = _write_starter(name, destination, version)
    return written


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
    linked: list[str] = field(default_factory=list)    # Markdown whose links out of the starter now name the tag
    modules: ModulesReport | None = None                # the terraform modules' own account (None: none were written)
    modules_dir: str = ""                               # where they went, relative to the tree
    modules_note: str = ""                              # why none were written

    @property
    def ok(self) -> bool:
        return not self.refused and (self.modules is None or self.modules.ok)

    def lines(self) -> list[str]:
        what = "the whole tree" if self.whole_tree else "the release-owned parts"
        out = [f"init-config: {what} of {self.starter} ({self.version}) -> {self.destination}: "
               f"{len(self.written)} written, {len(self.kept)} kept as they were"]
        if self.modules is not None:
            out.extend(self.modules.lines(f"init-config: {self.modules_dir}"))
        if self.modules_note:
            out.append(f"init-config: {self.modules_note}")
        if self.inferred:
            out.append(f"init-config: the starter {self.starter} was read from the tree's {WORKFLOW} "
                       "(--from names another)")
        for rel, n in sorted(self.carried.items()):
            if n:
                out.append(f"init-config: {rel}: your values kept in {n} line(s) where the release has REPLACE-ME")
        for rel, n in sorted(self.replaced.items()):
            if n:
                out.append(f"init-config: {rel}: {n} other line(s) now read as the release's -- review the diff")
        if self.linked:
            out.append(f"init-config: {len(self.linked)} Markdown file(s) link into the system repository at "
                       f"v{self.version}, where the starter's relative links pointed")
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


def _cfg_text(destination: Path) -> str | None:
    cfg = destination / "cfg" / "_config.yml"
    return cfg.read_text() if cfg.is_file() else None


def _refresh_modules(destination: Path, report: InitReport, *, force: bool) -> None:
    """The terraform modules of an existing tree: written, refreshed, adopted,
    kept or refused by name into the tree's own modules directory. An edited
    stamped copy is refused with or without ``force`` (the report says how to
    keep it: name it in ``config: module_sources``); a module so named is
    skipped. A tree whose ``module_source_base`` is not a directory inside it
    gets no module and a line saying why."""
    cfg_text = _cfg_text(destination)
    base = module_base_of(cfg_text)
    if base is None:
        report.modules_note = ("no terraform module written: the tree's module_source_base is not a directory "
                               "inside it; the modules there are the tree's own")
        return
    try:
        overrides = declared_overrides(destination)
    except ValueError as e:
        raise ValueError(f"{destination / 'cfg' / '_config.yml'}: {e}") from e
    modules = materialise_modules(destination / base, force=force, overrides=overrides)
    report.modules, report.modules_dir = modules, base
    report.written.extend(f"{base}/{m}/" for m in (*modules.written, *modules.refreshed, *modules.adopted))
    report.kept.extend(f"{base}/{m}/" for m in modules.kept)


def is_new_tree(destination: Path) -> bool:
    """A destination that takes the WHOLE starter: absent, empty, or a fresh
    clone holding only ``.git`` (a team creates its repository on GitHub
    and clones it, the usual order)."""
    if not destination.exists():
        return True
    entries = [e.name for e in destination.iterdir()]
    return not entries or entries == [".git"]


def holds_configuration(destination: Path) -> bool:
    """A tree the release-owned form may refresh: it has a configuration
    (``cfg/_config.yml``) or a ``.csis-version`` this command wrote."""
    return (destination / "cfg" / "_config.yml").is_file() or (destination / VERSION_FILE).is_file()


def _version(text: str) -> Version | None:
    try:
        return Version(text.strip())
    except InvalidVersion:
        return None


def init_config(destination: Path, starter: str | None = None, *, force: bool = False) -> InitReport:
    """Write a starter (or its release-owned parts) into ``destination``. With
    no ``starter``, a new tree takes the default and an existing one the
    starter its workflow came from."""
    stale = stale_install()
    if stale:
        raise ValueError(stale)
    version = release_version()
    destination = destination.resolve()
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"{destination} exists and is not a directory")
    empty = is_new_tree(destination)
    if not empty and not holds_configuration(destination):
        # the release-owned form refreshes a configuration repository and nothing
        # else. An operator once typed it in the SYSTEM repository's root,
        # which lost its Justfile, .gitignore and workflow to a starter's; and a fresh
        # clone with a README got the release-owned files and no cfg/, with a message
        # that read like success.
        entries = sorted(e.name for e in destination.iterdir())
        shown = ", ".join(entries[:6]) + (", ..." if len(entries) > 6 else "")
        raise ValueError(f"{destination} is neither empty nor a configuration repository (no cfg/_config.yml, "
                         f"no {VERSION_FILE}; it holds {shown}); a whole starter is written only into an empty "
                         f"directory or a fresh clone holding only .git, and a refresh only into a tree that "
                         f"holds a configuration. Nothing was written")
    inferred = False
    if starter is None:
        found = None if empty else infer_starter(destination)
        starter, inferred = (found, True) if found else (DEFAULT_STARTER, False)
    starter_path(starter)                               # an unknown name is refused before anything is written
    report = InitReport(starter=starter, version=version, destination=destination, whole_tree=empty, inferred=inferred)
    if empty:
        report.written, report.linked, report.modules = _write_starter(starter, destination, version)
        report.modules_dir = module_base_of(_cfg_text(destination)) or ""
        report.written.remove(VERSION_FILE)             # stamped below, with the report's say
    else:
        sources = render_sources(starter)
        for rel in release_owned_paths(sources):
            _place(sources[rel], destination / rel, rel, report, force=force)
        _refresh_modules(destination, report, force=force)
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


@dataclass
class ChangesReport:
    """What a release changed in the release-owned files of an existing tree.
    Nothing is written: this is the list a person reads before refreshing by
    hand."""
    starter: str
    inferred: bool
    refresh: list[str] = field(default_factory=list)    # changed by the release; the tree still has the previous release's text
    edited: list[str] = field(default_factory=list)     # changed by the release; the tree's copy also differs from the previous release's
    added: list[str] = field(default_factory=list)      # new in the release; the tree has no such file
    unchanged: int = 0

    @property
    def clear(self) -> bool:
        return not (self.refresh or self.edited or self.added)

    def lines(self) -> list[str]:
        out = [f"init-config: changes since the previous release, in the release-owned files of {self.starter}"
               + (" (read from the tree's workflow)" if self.inferred else "")]
        for title, paths in (("changed by the release; your copy is the previous release's own", self.refresh),
                             ("changed by the release AND edited in your tree (read both)", self.edited),
                             ("new in the release; your tree has no such file", self.added)):
            if paths:
                out.append(f"init-config: {title}:")
                out.extend(f"init-config:   {p}" for p in paths)
        if self.clear:
            out.append("init-config: nothing the release owns changed in a file your tree holds")
        return out


def _is_previous_text(previous: str, tree: str, rel: str) -> bool:
    """The tree's copy is the previous release's text: byte for byte, or (a
    workflow) with the team's values where that release had REPLACE-ME."""
    if previous == tree:
        return True
    if rel.startswith(".github/workflows/") and any(_placeholder(x) for x in previous.splitlines()):
        merged, _, _ = carry_team_values(previous, tree)
        return merged == tree
    return False


def installed_module_files(base: str) -> dict[str, Path]:
    """The installed plugins' module files as they sit in a tree whose
    modules directory is ``base``: ``<base>/<module>/<file>`` to the file
    inside the plugin. The stamps are not content and are not here."""
    out: dict[str, Path] = {}
    for name, module in installed_modules().items():
        for p in sorted(module.path.rglob("*")):
            rel = p.relative_to(module.path)
            if p.is_file() and p.name != STAMP_FILE and not any(part in _LITTER for part in rel.parts):
                out[f"{base}/{name}/{rel.as_posix()}"] = p
    return out


def changes_since(destination: Path, previous_root: Path, starter: str | None = None) -> ChangesReport:
    """Compare, for each release-owned file of this release's starter, the
    previous release's starter (``previous_root``, a ``starters/`` directory
    that release's own wheel carries, of either layout), this release's,
    and the tree's. Writes nothing. A file the release did not change is
    not listed, whatever the tree holds.

    This release's side is the rendered starter plus the installed plugins'
    modules, as they would sit in the tree's own modules directory. The
    previous side's modules are the files of its tree when that release
    carried whole trees; a previous root of the current layout carries no
    module, and a file it lacks is never counted as unchanged: it is listed
    as added when the tree has no such file, as edited when the tree's copy
    differs from this release's, and not at all when it is this release's.
    The stamps (``.csis-module``) are part of no comparison."""
    destination = destination.resolve()
    if not destination.is_dir() or not holds_configuration(destination):
        raise ValueError(f"{destination} is not a configuration repository (no cfg/_config.yml, no {VERSION_FILE})")
    inferred = False
    if starter is None:
        found = infer_starter(destination)
        starter, inferred = (found, True) if found else (DEFAULT_STARTER, False)
    starter_path(starter)
    if not (previous_root / starter).is_dir():
        raise ValueError(f"the previous release's starters ({previous_root}) hold no {starter}; "
                         "a starter new in this release has no previous text to compare with")
    new = render_sources(starter)
    old = render_sources(starter, previous_root)
    owned = release_owned_paths(new)
    base = module_base_of(_cfg_text(destination))
    if base:
        modules = installed_module_files(base)
        new.update(modules)
        owned.extend(sorted(modules))
    report = ChangesReport(starter=starter, inferred=inferred)
    for rel in owned:
        if posixpath.basename(rel) == STAMP_FILE:
            continue
        new_p, mine = new[rel], destination / rel
        old_p = old.get(rel)
        if old_p is None and base and base != MODULES_DIR and rel.startswith(base + "/"):
            old_p = old.get(f"{MODULES_DIR}/{rel[len(base) + 1:]}")       # the older layout's modules directory
        if old_p is not None and _same(old_p, new_p):
            report.unchanged += 1
        elif not mine.is_file():
            report.added.append(rel)
        elif old_p is not None and _is_previous_text(old_p.read_text(), mine.read_text(), rel):
            report.refresh.append(rel)
        elif _same(new_p, mine):
            if old_p is not None:
                report.unchanged += 1
        else:
            report.edited.append(rel)
    return report
