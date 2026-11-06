# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The terraform modules a release ships, and how they reach a tree.

Every terraform module (``some_instance``, ``some_storage``, ...) is
package data inside the plugin that owns it, and the plugin names its
modules directory through one entry point in the group
:data:`~cs_image_system.contract.modules.MODULES_ENTRY_POINT_GROUP`.
This module is the one API over that declaration:

- :func:`installed_modules` lists the modules of every installed plugin,
  with the namespace and the release each came from, without importing
  any plugin's code (the entry point names a package and a directory; the
  directory is read, the package is never imported);
- :func:`materialise_modules` copies them into a tree's modules directory
  and stamps every copy (:data:`STAMP_FILE`: the plugin, the release, the
  content hash) so a later materialisation refreshes only copies nobody
  edited, refuses an edited one by name, and leaves alone a module the
  tree sources elsewhere (``config: module_sources``);
- :func:`content_hash` is the hash the stamp carries;
- :func:`declared_overrides` reads the names ``config: module_sources``
  declares, from the raw YAML, without loading the configuration.

A tree that wants the release's version of a module it edited deletes
its copy; a tree that wants to keep the edit names the module in
``config: module_sources`` and the materialisation skips it from then on.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from importlib.resources import files
from pathlib import Path

import yaml

from cs_image_system.contract.modules import MODULES_ENTRY_POINT_GROUP

from .loader import namespace_of_distribution

#: The stamp a materialised copy carries, written beside the module's files.
STAMP_FILE = ".csis-module"

#: Names that are neither module content nor part of the hash.
_IGNORED_NAMES = frozenset({STAMP_FILE, ".DS_Store", "__pycache__"})


@dataclass(frozen=True)
class ModuleSource:
    """One installed terraform module: where the plugin's package keeps it."""

    name: str            # the module's directory name, what a `module` call names
    namespace: str       # the owning plugin's namespace (`some-runtime`, `base`, ...)
    distribution: str    # the distribution that declares it
    version: str         # that distribution's version
    path: Path           # the module directory inside the installed plugin


def _module_dirs(root: Path) -> list[Path]:
    """The immediate subdirectories of ``root`` holding at least one file."""
    if not root.is_dir():
        return []
    out: list[Path] = []
    for d in sorted(root.iterdir(), key=lambda p: p.name):
        if not d.is_dir() or d.name in _IGNORED_NAMES:
            continue
        if any(p.is_file() and p.name not in _IGNORED_NAMES for p in d.rglob("*")):
            out.append(d)
    return out


def installed_modules() -> dict[str, ModuleSource]:
    """Every terraform module an installed plugin declares, by directory
    name, in sorted order.

    An entry point in :data:`MODULES_ENTRY_POINT_GROUP` has the value
    ``<package>:<dirname>``; the directory is resolved as package data and
    read, the package itself is never imported for its code. A module
    name two distributions ship is refused, naming both.
    """
    found: dict[str, ModuleSource] = {}
    for ep in sorted(entry_points(group=MODULES_ENTRY_POINT_GROUP), key=lambda e: (e.value, e.name)):
        if ":" not in ep.value:
            raise ValueError(
                f"modules entry point {ep.name!r} has the value {ep.value!r}; expected <package>:<dirname>")
        package, _, dirname = ep.value.partition(":")
        dist = ep.dist
        if dist is None:
            raise ValueError(f"modules entry point {ep.name!r} ({ep.value}) has no distribution to derive a "
                             "namespace from")
        root = Path(str(files(package) / dirname))
        for d in _module_dirs(root):
            other = found.get(d.name)
            if other is not None:
                raise ValueError(
                    f"terraform module {d.name!r} is shipped by two distributions: "
                    f"{other.distribution} ({other.path}) and {dist.name} ({d})")
            found[d.name] = ModuleSource(name=d.name, namespace=namespace_of_distribution(dist.name),
                                         distribution=dist.name, version=dist.version, path=d)
    return dict(sorted(found.items()))


def _content_files(directory: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for p in directory.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(directory)
        if any(part in _IGNORED_NAMES for part in rel.parts):
            continue
        out.append((rel.as_posix(), p))
    out.sort()
    return out


def content_hash(directory: Path) -> str:
    """``sha256:<hex>`` over the sorted relative POSIX paths and the bytes of
    every file under ``directory``, the stamp, ``.DS_Store`` and
    ``__pycache__`` excluded."""
    h = hashlib.sha256()
    for rel, p in _content_files(directory):
        data = p.read_bytes()
        h.update(f"{rel}\0{len(data)}\0".encode())
        h.update(data)
    return f"sha256:{h.hexdigest()}"


@dataclass(frozen=True)
class Stamp:
    """What a materialised copy records of where it came from."""

    plugin: str     # the owning plugin's namespace
    release: str    # the distribution's version at the time of the copy
    hash: str       # content_hash of the copy as written

    @classmethod
    def read(cls, path: Path) -> Stamp | None:
        """The stamp at ``path``; None when absent or not a stamp."""
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            return None
        fields: dict[str, str] = {}
        for line in text.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
        try:
            return cls(plugin=fields["plugin"], release=fields["release"], hash=fields["hash"])
        except KeyError:
            return None

    def write(self, path: Path) -> None:
        path.write_text(f"plugin: {self.plugin}\nrelease: {self.release}\nhash: {self.hash}\n")


@dataclass
class ModulesReport:
    """What one materialisation did, by module name."""

    written: list[str] = field(default_factory=list)    # absent before: copied whole and stamped
    refreshed: list[str] = field(default_factory=list)  # an unmodified copy of another release: replaced
    adopted: list[str] = field(default_factory=list)    # an unstamped copy identical to the release's: stamped
    kept: list[str] = field(default_factory=list)       # already the release's, stamped: untouched
    refused: list[str] = field(default_factory=list)    # edited in the tree, or unstamped and different without force
    skipped: list[str] = field(default_factory=list)    # named in `config: module_sources`: never written
    notes: list[str] = field(default_factory=list)      # anything else worth a line
    reasons: dict[str, str] = field(default_factory=dict)   # module -> why it was refused

    @property
    def ok(self) -> bool:
        return not self.refused

    def lines(self, prefix: str = "modules") -> list[str]:
        out = [f"{prefix}: {len(self.written)} written, {len(self.refreshed)} refreshed, "
               f"{len(self.adopted)} adopted, {len(self.kept)} kept, {len(self.skipped)} skipped, "
               f"{len(self.refused)} refused"]
        for name in self.written:
            out.append(f"{prefix}: {name}: written from the release")
        for name in self.refreshed:
            out.append(f"{prefix}: {name}: refreshed -- the copy was another release's, unmodified")
        for name in self.adopted:
            out.append(f"{prefix}: {name}: adopted -- an unstamped copy identical to the release's, now stamped")
        for name in self.kept:
            out.append(f"{prefix}: {name}: kept as it was")
        for name in self.skipped:
            out.append(f"{prefix}: {name}: skipped -- config: module_sources names it, the tree's source stands")
        for note in self.notes:
            out.append(f"{prefix}: {note}")
        for name in self.refused:
            out.append(f"{prefix}: REFUSED {name}: {self.reasons.get(name, 'it exists and differs')}")
        return out


def _copy_module(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*_IGNORED_NAMES))


def materialise_modules(dest: Path, *, force: bool = False, overrides: Iterable[str] = (),
                        only: Iterable[str] | None = None) -> ModulesReport:
    """Write the installed modules into ``dest`` (a tree's modules
    directory, created if absent), one subdirectory per module, each
    stamped.

    ``overrides`` are the module names ``config: module_sources`` declares:
    they are skipped, never written. ``only`` narrows the set to those
    names. For each module: absent, it is copied whole and stamped
    (written); present with a stamp whose hash is still the copy's
    (unmodified), it is kept when it is the release's content and replaced
    whole and re-stamped when it is another release's (refreshed); present
    with a stamp whose hash is no longer the copy's (edited in the tree),
    it is refused, ``force`` or not; present without a stamp, identical
    content is stamped (adopted) and different content is refused unless
    ``force`` replaces it. Nothing outside ``dest`` is touched.
    """
    report = ModulesReport()
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    wanted = None if only is None else set(only)
    skip = set(overrides)
    for name, module in installed_modules().items():
        if wanted is not None and name not in wanted:
            continue
        if name in skip:
            report.skipped.append(name)
            continue
        copy = dest / name
        stamp = Stamp(plugin=module.namespace, release=module.version, hash=content_hash(module.path))
        if not copy.exists():
            _copy_module(module.path, copy)
            stamp.write(copy / STAMP_FILE)
            report.written.append(name)
            continue
        if not copy.is_dir():
            report.refused.append(name)
            report.reasons[name] = f"{copy} exists and is not a directory; remove it to take the release's module"
            continue
        current = content_hash(copy)
        existing = Stamp.read(copy / STAMP_FILE)
        if existing is not None:
            if existing.hash != current:
                report.refused.append(name)
                report.reasons[name] = (
                    f"the copy was edited after it was written (release {existing.release}); keep your "
                    f"version by naming it in config: module_sources ({name}: <path or URL>), or delete "
                    f"the copy to take the release's")
                continue
            if current == stamp.hash:
                if existing != stamp:
                    stamp.write(copy / STAMP_FILE)
                    report.notes.append(f"{name}: the stamp now names release {stamp.release} "
                                        f"(it named {existing.release}; the content is the same)")
                report.kept.append(name)
                continue
            shutil.rmtree(copy)
            _copy_module(module.path, copy)
            stamp.write(copy / STAMP_FILE)
            report.refreshed.append(name)
            continue
        # unstamped: a copy from a release that wrote no stamps, or the tree's own
        if current == stamp.hash:
            stamp.write(copy / STAMP_FILE)
            report.adopted.append(name)
            continue
        if not force:
            report.refused.append(name)
            report.reasons[name] = (
                "it exists without a stamp and differs from the release's; --force overwrites it, "
                f"or keep your version by naming it in config: module_sources ({name}: <path or URL>)")
            continue
        shutil.rmtree(copy)
        _copy_module(module.path, copy)
        stamp.write(copy / STAMP_FILE)
        report.written.append(name)
        report.notes.append(f"{name}: an unstamped copy that differed was replaced (--force)")
    return report


def declared_overrides(config_root: Path) -> list[str]:
    """The module names ``config: module_sources`` declares in
    ``<config_root>/cfg/_config.yml``, read as plain YAML (no configuration
    load); ``[]`` when the file or the key is absent. A ``module_sources``
    that is not a mapping is refused."""
    path = Path(config_root) / "cfg" / "_config.yml"
    if not path.is_file():
        return []
    doc = yaml.safe_load(path.read_text()) or {}
    config = doc.get("config") if isinstance(doc, dict) else None
    if not isinstance(config, dict):
        return []
    sources = config.get("module_sources")
    if sources is None:
        return []
    if not isinstance(sources, dict):
        raise ValueError(f"config: module_sources must be a mapping of module name to path or URL, "
                         f"not {type(sources).__name__}")
    return [str(k) for k in sources]
