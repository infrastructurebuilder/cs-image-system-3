# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The image kind (stage 30): the builder that bakes base images and
instance images (packer, in the built-in plugin), and the two enums a
provider-specific image carries. The image items themselves (``Image``,
``BaseImage``) are the core's models and ``Any`` here. Stage 106 adds the
image query: the system's vocabulary for "which vendor image", which every
runtime translates to its own."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from .constants import DEFAULT
from .core import BuilderProtocol, RuntimeEnabledBuilderModelProtocol
from .lifecycle import ExecutionLifecyclePhase


class PSIState(StrEnum):
    """State of a ProviderSpecificImage."""
    RESOLVED = "resolved"  # A concrete provider identifier is known (e.g. an AMI id)
    DEFERRED = "deferred"  # The image does not exist yet; only a query/name pattern is known


class PSISourceKind(StrEnum):
    """What kind of source a ProviderSpecificImage was generated from."""
    IMAGE = "image"          # A user-declared Image
    OS_BUILDER = "os_builder"  # An OsBuilder vendor-image lookup


def psi_key(source_name: str, runtime: str) -> str:
    """Registry key for a ProviderSpecificImage.

    "::" cannot appear in validated item names, so the key is unambiguous.
    """
    return f"{source_name}::{runtime}"


class ImageBuilderModelProtocol(RuntimeEnabledBuilderModelProtocol, Protocol):
    """An entry under ``image_builders:``."""

    default_machine_type: str

    def get_default_machine_type(self) -> str: ...


class ImageBuilderProtocol(BuilderProtocol, Protocol):
    """An image builder: it collects the images declared on it and files
    each build block's output under a path per phase."""

    def get_block_directory_for_phase(self, phase: ExecutionLifecyclePhase, block: str = DEFAULT) -> Path: ...

    def get_block_path_for_phase(self, phase: ExecutionLifecyclePhase, block: str = DEFAULT,
                                 discriminator: str | None = None, suffix: str | None = None) -> Path: ...

    def add_image(self, image: Any, os_builder: Any = None) -> None: ...

    def build_target_label(self, image: Any) -> str: ...

    def get_images(self, os_builder: bool = False) -> list[Any]: ...


# ---------------------------------------------------------------- stage 106
# The image query: the system's own vocabulary for "which vendor image", which
# every runtime translates to its own (``RuntimeBuilderProtocol
# .translate_image_query``). The spellings are the system's; where EC2's
# were good names they were kept -- the system started on AWS and used its
# filter keys, the operator's incidental choice, now a declared one.

#: The keys, in the order a query is written out.
QUERY_KEYS: tuple[str, ...] = (
    "name",             # a glob over the vendor's image name
    "family",           # the vendor's own family token, where the runtime has one
    "version",          # the major version (a container runtime's tag; the clouds expand it into name or family)
    "architecture",     # x86_64 or arm64
    "publisher",        # who owns the image: an account, a project, a registry namespace
    "state",            # available
    "virtualization",   # the EC2 particular (hvm)
    "root_device",      # the EC2 particular (ebs)
    "tags",             # a tag or label per key
    "newest",           # take the latest match (the default); false refuses an ambiguous match
    "native",           # the one escape hatch: passed to the runtime verbatim, never translated
)

#: The spellings a tree may still write, each read as its key: EC2's field
#: names (which the system started with) and the nested ``filters:`` form's
#: companions. A key not in QUERY_KEYS and not here is refused.
QUERY_KEY_ALIASES: dict[str, str] = {
    "owners": "publisher",
    "owner": "publisher",
    "project": "publisher",
    "projects": "publisher",
    "image_name": "name",
    "root_device_type": "root_device",
    "root-device-type": "root_device",
    "virtualization_type": "virtualization",
    "virtualization-type": "virtualization",
    "status": "state",
    "most_recent": "newest",
    "most-recent": "newest",
    "arch": "architecture",
}

_SCALARS: tuple[str, ...] = ("name", "family", "version", "architecture", "state", "virtualization", "root_device")


@dataclass
class ImageQuery:
    """A vendor-image query in the system's vocabulary (stage 106).

    A key that is unset (None, an empty list, an empty mapping) is not part
    of the query: ``keys()`` names the set ones, ``to_mapping()`` writes
    them in QUERY_KEYS order, and ``merged(over)`` lets another query's set
    keys land on top of this one's, key by key (``tags`` and ``native``
    merge by their own keys; ``publisher`` replaces; ``name`` and ``family`` displace each other). ``from_mapping`` reads
    what a tree writes: the flat form, or the older ``{"filters": {...},
    "owners": [...]}`` form, with QUERY_KEY_ALIASES applied and
    ``tag:<k>`` keys folded into ``tags``; an unknown key raises ValueError
    naming it. ``substituted(version=...)`` fills ``{version}`` in every
    string value (the catalog's one placeholder).
    """

    name: str | None = None
    family: str | None = None
    version: str | None = None
    architecture: str | None = None
    publisher: tuple[str, ...] = ()
    state: str | None = None
    virtualization: str | None = None
    root_device: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    newest: bool | None = None
    native: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.publisher, str):
            self.publisher = (self.publisher,)
        self.publisher = tuple(str(p).strip() for p in self.publisher if str(p).strip())
        self.tags = {str(k): str(v) for k, v in dict(self.tags or {}).items()}
        self.native = dict(self.native or {})
        for key in _SCALARS:
            value = getattr(self, key)
            if value is not None:
                setattr(self, key, str(value))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any] | None, *, where: str = "") -> "ImageQuery":
        out: dict[str, Any] = {}
        for raw_key, value in dict(mapping or {}).items():
            key = str(raw_key)
            if key == "filters" and isinstance(value, Mapping):
                nested = cls.from_mapping(value, where=where)
                for k in nested.keys():
                    if k == "tags":
                        out.setdefault("tags", {}).update(nested.tags)
                    elif k == "native":
                        out.setdefault("native", {}).update(nested.native)
                    else:
                        out[k] = getattr(nested, k)
                continue
            if key.startswith("tag:"):
                out.setdefault("tags", {})[key[4:]] = str(value)
                continue
            key = QUERY_KEY_ALIASES.get(key, key)
            if key not in QUERY_KEYS:
                known = ", ".join(QUERY_KEYS)
                raise ValueError(f"{where + ': ' if where else ''}image query key {raw_key!r} is not one the system "
                                 f"knows ({known}); a runtime particular goes under `native:`")
            if key == "tags":
                out.setdefault("tags", {}).update({str(k): str(v) for k, v in dict(value or {}).items()})
            elif key == "native":
                out.setdefault("native", {}).update(dict(value or {}))
            elif key == "publisher":
                out["publisher"] = tuple(value) if isinstance(value, (list, tuple, set)) else (value,)
            elif key == "newest":
                out["newest"] = bool(value) if not isinstance(value, str) else value.strip().lower() in ("true", "yes", "1")
            else:
                out[key] = value
        return cls(**out)

    def keys(self) -> frozenset[str]:
        """The keys this query sets (``newest`` only when written explicitly)."""
        out: set[str] = set()
        for key in _SCALARS:
            if getattr(self, key) is not None:
                out.add(key)
        if self.publisher:
            out.add("publisher")
        if self.tags:
            out.add("tags")
        if self.newest is not None:
            out.add("newest")
        if self.native:
            out.add("native")
        return frozenset(out)

    def is_empty(self) -> bool:
        return not self.keys()

    def to_mapping(self) -> dict[str, Any]:
        """The set keys, in QUERY_KEYS order; ``publisher`` as a list."""
        out: dict[str, Any] = {}
        for key in QUERY_KEYS:
            if key not in self.keys():
                continue
            value = getattr(self, key)
            out[key] = list(value) if key == "publisher" else (dict(value) if key in ("tags", "native") else value)
        return out

    def merged(self, over: "ImageQuery | None") -> "ImageQuery":
        """A copy with ``over``'s set keys landing on this one's. ``name`` and
        ``family`` are two ways to say which image: an override that says
        one clears the other from below (both at one level are ANDed)."""
        if over is None:
            return ImageQuery(**self.to_mapping())
        out = self.to_mapping()
        if "name" in over.keys() and "family" not in over.keys():
            out.pop("family", None)
        if "family" in over.keys() and "name" not in over.keys():
            out.pop("name", None)
        for key in over.keys():
            if key == "tags":
                out.setdefault("tags", {}).update(over.tags)
            elif key == "native":
                out.setdefault("native", {}).update(over.native)
            else:
                out[key] = getattr(over, key)
        return ImageQuery(**out)

    def substituted(self, **values: str) -> "ImageQuery":
        """Every ``{name}`` placeholder in a string value filled from ``values``."""
        def fill(v: Any) -> Any:
            if isinstance(v, str):
                for k, val in values.items():
                    v = v.replace("{" + k + "}", str(val))
            return v
        out = self.to_mapping()
        for key, value in list(out.items()):
            if isinstance(value, str):
                out[key] = fill(value)
            elif isinstance(value, list):
                out[key] = [fill(x) for x in value]
            elif isinstance(value, dict):
                out[key] = {k: fill(x) for k, x in value.items()}
        return ImageQuery(**out)

    def __str__(self) -> str:
        return ", ".join(f"{k}={v}" for k, v in self.to_mapping().items()) or "(empty)"
