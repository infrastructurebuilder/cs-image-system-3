# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The image-source catalog: where a vendor image comes from, per family
and runtime type, in the system's query vocabulary
(``cs_image_system.contract.image.ImageQuery``).

Two layers, one lookup. The release-owned default catalog is the union of
what the INSTALLED runtime plugins ship as package data: each runtime
builder class answers ``image_source_entries()`` with its own part (the
blocks keyed by its runtime type), and ``packaged_default_entries`` merges
those by family. The core itself names no runtime: a runtime that is not
installed contributes nothing, and a new runtime brings its own part. A
tree's ``image_sources:`` entries (``cfg/image-sources*.yml``) extend or
override the merged catalog by family and version. An entry may say what
its family IS (``is: rhel``): everything that branches on a family reads
that, so a custom family (``rhel-from-jerry``) is treated as what it is
while its query is its own.

A block is looked up by (family, version, runtime type): within a layer an
entry naming the version lands on the generic entry for the family, and
the tree's layer lands on the default's. A runtime type with no block in
either layer answers None; the OS builder's own ``query`` and its runtime
entry's may still provide one, and ``validate`` refuses the entry when
nothing does. The one placeholder, ``{version}``, is filled at lookup.

The local modification tests read one more thing here: the STAND-IN
block, keyed by the runtime type of the one installed runtime that offers
a local test target (``local_test_target()``); ``container_reference``
turns that block into an image reference a container tool can pull.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import field
from importlib.resources import files
from typing import Annotated, Any

import yaml
from pydantic import Field, TypeAdapter
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.contract.image import ImageQuery
from cs_image_system.contract.image_sources import (  # noqa: F401 - re-exported: the words are the contract's
    IMAGE_SOURCES_KEY, PACKAGED_CATALOG_FILE, container_reference)
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.contract.names import safe_name

from .singleton import singleton

log = logging.getLogger(__name__)



@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ImageSource:
    """One entry under ``image_sources:``."""

    family: str
    is_: Annotated[str | None, Field(alias="is")] = None
    versions: list[str] = field(default_factory=list)
    description: str | None = None
    #: runtime type -> a query in the system's vocabulary (``{version}`` allowed)
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.family = str(self.family).strip().lower()
        if not self.family:
            raise ValueError("image_sources: an entry needs a family")
        if self.is_ is not None:
            self.is_ = str(self.is_).strip().lower() or None
        self.versions = [str(v).strip() for v in (self.versions or []) if str(v).strip()]
        parsed: dict[str, dict[str, Any]] = {}
        for runtime_type, block in dict(self.sources or {}).items():
            key = str(runtime_type).strip().lower()
            if not isinstance(block, dict):
                raise ValueError(f"image_sources: family {self.family}: the `{key}` block must be a mapping")
            # the keys are checked here, at load, so a catalog with a key the
            # system does not know is refused before any runtime is asked
            ImageQuery.from_mapping(block, where=f"image_sources: family {self.family}, `{key}` block")
            parsed[key] = dict(block)
        self.sources = parsed

    def effective_family(self) -> str:
        return self.is_ or self.family

    def matches(self, family: str, version: str | None) -> bool:
        if self.family != str(family).strip().lower():
            return False
        return not self.versions or str(version or "").strip() in self.versions

    def block(self, runtime_type: str) -> ImageQuery | None:
        raw = self.sources.get(str(runtime_type).strip().lower())
        return ImageQuery.from_mapping(raw) if raw is not None else None

    def runtime_types(self) -> list[str]:
        return sorted(self.sources)


_ADAPTER = TypeAdapter(ImageSource)


def structure_entries(entries: list[Any], *, where: str) -> list[ImageSource]:
    """A list of raw entries (or ImageSource instances) as ImageSource objects."""
    out: list[ImageSource] = []
    for idx, raw in enumerate(entries or []):
        if isinstance(raw, ImageSource):
            out.append(raw)
            continue
        try:
            out.append(_ADAPTER.validate_python(raw))
        except Exception as e:
            raise ValueError(f"{where}: image_sources entry {idx} ({(raw or {}).get('family', '?') if isinstance(raw, dict) else raw!r}): {e}") from e
    return out


def packaged_entries_of(package: str) -> list[Mapping[str, Any]]:
    """The raw entries of ``<package>/data/image-sources.yml``, the file a
    runtime plugin ships its part of the catalog in: what a runtime builder
    class returns from ``image_source_entries()``. Empty when the package
    ships no such file."""
    resource = files(package) / "data" / PACKAGED_CATALOG_FILE
    if not resource.is_file():
        return []
    doc = yaml.safe_load(resource.read_text()) or {}
    return [dict(e) for e in (doc.get(IMAGE_SOURCES_KEY) or []) if isinstance(e, Mapping)]


def _runtime_classes() -> dict[str, type]:
    """Every registered runtime builder class by name, the plugins loaded
    first (idempotent), so the catalog is the INSTALLED runtimes' and never
    depends on which a tree declares."""
    from .loader import load_plugins
    from .registry import current_registry
    load_plugins()
    return dict(current_registry().runtime_builder_classes())


def _runtime_entries(classes: Mapping[str, type]) -> list[tuple[str, list[ImageSource]]]:
    """Each runtime's part, structured so that an error names the runtime
    whose file carries it, in name order for a deterministic merge."""
    out: list[tuple[str, list[ImageSource]]] = []
    for name, cls in sorted(classes.items()):
        hook: Any = getattr(cls, "image_source_entries", None)
        answered: Any = hook() if callable(hook) else None
        raw: list[Mapping[str, Any]] = list(answered or [])
        if raw:
            out.append((name, structure_entries(raw, where=f"the {name} runtime's {PACKAGED_CATALOG_FILE}")))
    return out


def merge_entries(parts: list[tuple[str, list[ImageSource]]]) -> list[ImageSource]:
    """The runtimes' parts as one catalog, merged by (family, versions):
    ``sources`` is the union by runtime type; ``description``, ``is`` and
    ``versions`` are the first non-empty value, a later part that says
    something else logged at WARNING and ignored. Families keep the order
    in which they were first seen."""
    merged: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    owners: dict[tuple[str, tuple[str, ...]], str] = {}
    for name, entries in parts:
        for e in entries:
            key = (e.family, tuple(e.versions))
            raw = merged.get(key)
            if raw is None:
                merged[key] = {"family": e.family, "versions": list(e.versions), "is": e.is_,
                               "description": e.description, "sources": {k: dict(v) for k, v in e.sources.items()}}
                owners[key] = name
                continue
            for attr, mine in (("is", e.is_), ("description", e.description)):
                if not mine:
                    continue
                if not raw[attr]:
                    raw[attr] = mine
                elif raw[attr] != mine:
                    log.warning(f"image sources: family {e.family}: the {name} runtime says {attr}={mine!r}, "
                                f"the {owners[key]} runtime said {raw[attr]!r}; keeping the first")
            for runtime_type, block in e.sources.items():
                if runtime_type not in raw["sources"]:
                    raw["sources"][runtime_type] = dict(block)
                elif raw["sources"][runtime_type] != dict(block):
                    log.warning(f"image sources: family {e.family}: the {name} runtime's `{runtime_type}` block "
                                f"differs from the {owners[key]} runtime's; keeping the first")
    return structure_entries(list(merged.values()), where="the release's image-source catalog")


def packaged_default_entries(classes: Mapping[str, type] | None = None) -> list[ImageSource]:
    """The release-owned catalog: the parts every installed runtime plugin
    ships, merged by family (``classes`` overrides the registry's runtime
    builder classes, for tests)."""
    return merge_entries(_runtime_entries(_runtime_classes() if classes is None else classes))


def stand_in_runtime_type(classes: Mapping[str, type] | None = None) -> str | None:
    """The runtime type whose catalog block the local modification tests
    read: the ``csis_name()`` of the first registered runtime builder class
    (by name) whose ``local_test_target()`` is not None; None when no
    installed runtime offers a local target."""
    for _name, cls in sorted((_runtime_classes() if classes is None else classes).items()):
        hook = getattr(cls, "local_test_target", None)
        if callable(hook) and hook() is not None:
            return str(cls.csis_name())
    return None


@singleton
class ImageSourceCatalog:
    """The two layers and the lookups over them. One per process; tests
    reset it with the other singletons."""

    def __init__(self) -> None:
        self._default: list[ImageSource] | None = None
        self._tree: list[ImageSource] = []

    def reset(self) -> None:
        self._default = None
        self._tree = []

    # ------------------------------------------------------------ the layers
    def default_entries(self) -> list[ImageSource]:
        if self._default is None:
            self._default = packaged_default_entries()
        return self._default

    def tree_entries(self) -> list[ImageSource]:
        return list(self._tree)

    def set_tree(self, entries: list[Any]) -> None:
        self._tree = structure_entries(entries, where="cfg/image-sources")
        if self._tree:
            log.info(f"image sources: {len(self._tree)} tree entries over the release's {len(self.default_entries())}")

    def layers(self) -> tuple[tuple[str, list[ImageSource]], ...]:
        return (("release", self.default_entries()), ("tree", self.tree_entries()))

    # ------------------------------------------------------------ the lookups
    def _matching(self, family: str, version: str | None) -> list[tuple[str, ImageSource]]:
        """Every matching entry, in landing order: the release's generic, the
        release's for this version, the tree's generic, the tree's for this
        version. Later ones land on earlier ones."""
        out: list[tuple[str, ImageSource]] = []
        for layer, entries in self.layers():
            generic = [e for e in entries if e.matches(family, version) and not e.versions]
            specific = [e for e in entries if e.matches(family, version) and e.versions]
            out.extend((layer, e) for e in generic + specific)
        return out

    def knows(self, family: str, version: str | None = None) -> bool:
        return bool(self._matching(family, version))

    def effective_family(self, family: str, version: str | None = None) -> str:
        """What ``family`` IS: the last matching entry's ``is``, else the token."""
        out = str(family).strip().lower()
        for _layer, entry in self._matching(family, version):
            if entry.is_:
                out = entry.is_
        return out

    def block(self, family: str, version: str | None, runtime_type: str) -> ImageQuery | None:
        """The catalog's query for ``family`` on a runtime type, the layers
        merged, ``{version}`` filled; None when no layer has one."""
        merged: ImageQuery | None = None
        for _layer, entry in self._matching(family, version):
            b = entry.block(runtime_type)
            if b is None:
                continue
            merged = b if merged is None else merged.merged(b)
        return merged.substituted(version=str(version or "")) if merged is not None else None

    def stand_in_block(self, family: str, version: str | None) -> ImageQuery | None:
        """The block the local modification tests read, keyed by the
        runtime type that offers the local test target
        (``stand_in_runtime_type``): the family's own, else the family it
        IS (a custom family with no container of its own is tested as what
        it is). None when no installed runtime offers a local target."""
        runtime_type = stand_in_runtime_type()
        if runtime_type is None:
            return None
        own = self.block(family, version, runtime_type)
        if own is not None:
            return own
        real = self.effective_family(family, version)
        return self.block(real, version, runtime_type) if real != str(family).strip().lower() else None

    def families(self) -> list[str]:
        out: list[str] = []
        for _layer, entries in self.layers():
            for e in entries:
                if e.family not in out:
                    out.append(e.family)
        return out


def default_os_type(family: str, version: str | None, registered: dict[str, type]) -> str | None:
    """The one registered OS model type that serves what ``family`` IS, by
    the classes' ``families()``; None when none or more than one does."""
    real = ImageSourceCatalog().effective_family(family, version)
    hits = sorted(name for name, cls in registered.items()
                  if real in tuple(str(f).lower() for f in getattr(cls, "families", lambda: ())()))
    return hits[0] if len(hits) == 1 else None


def tree_file_name(family: str) -> str:
    """A suggested file for a family's entry, for the refusal messages."""
    return f"cfg/image-sources.yml (family {safe_name(family)})"
