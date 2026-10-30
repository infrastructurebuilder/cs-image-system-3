# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The image-source catalog (stage 106): where a vendor image comes from,
per family and runtime type, in the system's query vocabulary
(``cs_image_system.contract.image.ImageQuery``).

Two layers, one lookup. The release-owned default catalog ships with this
package (``data/image-sources.yml``); a tree's ``image_sources:`` entries
(``cfg/image-sources*.yml``) extend or override it by family and version.
An entry may say what its family IS (``is: rhel``): everything that
branches on a family reads that, so a custom family (``rhel-from-jerry``)
is treated as what it is while its query is its own.

A block is looked up by (family, version, runtime type): within a layer an
entry naming the version lands on the generic entry for the family, and
the tree's layer lands on the default's. A runtime type with no block in
either layer answers None; the OS builder's own ``query`` and its runtime
entry's may still provide one, and ``validate`` refuses the entry when
nothing does. The one placeholder, ``{version}``, is filled at lookup.
"""
from __future__ import annotations

import logging
from dataclasses import field
from importlib.resources import files
from typing import Annotated, Any

import yaml
from pydantic import Field, TypeAdapter
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.contract.image import ImageQuery
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.contract.names import safe_name

from .singleton import singleton

log = logging.getLogger(__name__)

#: The runtime type the local modification tests read a stand-in container
#: from, whether or not a container runtime plugin is installed.
DOCKER_RUNTIME_TYPE = "docker"
IMAGE_SOURCES_KEY = "image_sources"


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


def packaged_default_entries() -> list[ImageSource]:
    """The release-owned catalog, read from this package's data file."""
    text = (files("cs_image_system.base") / "data" / "image-sources.yml").read_text()
    doc = yaml.safe_load(text) or {}
    return structure_entries(list(doc.get(IMAGE_SOURCES_KEY) or []), where="the release's image-sources.yml")


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
        """The ``docker`` block the local modification tests read: the
        family's own, else the family it IS (a custom family with no
        container of its own is tested as what it is)."""
        own = self.block(family, version, DOCKER_RUNTIME_TYPE)
        if own is not None:
            return own
        real = self.effective_family(family, version)
        return self.block(real, version, DOCKER_RUNTIME_TYPE) if real != str(family).strip().lower() else None

    def families(self) -> list[str]:
        out: list[str] = []
        for _layer, entries in self.layers():
            for e in entries:
                if e.family not in out:
                    out.append(e.family)
        return out


def container_reference(query: ImageQuery) -> str | None:
    """A ``docker`` block as a container image reference: ``native.image``
    verbatim when given; else ``<publisher>/<name>:<version>``, the
    publisher omitted for Docker Hub's ``library``."""
    image = query.native.get("image") if query.native else None
    if image:
        return str(image)
    if not query.name:
        return None
    publisher = query.publisher[0] if query.publisher else ""
    repo = query.name if publisher in ("", "library") else f"{publisher}/{query.name}"
    return f"{repo}:{query.version}" if query.version else repo


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
