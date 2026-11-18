# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The record a plugin's entry point returns.

A plugin's ``initialize`` returns one :class:`PluginMetadata` (or a list of
them): the classes to register under service names, the builder class for
each model class, the item models it injects, and its versions. It
satisfies ``core.PluginMetadataProtocol`` as data; the core's
``AbstractPluginMetadata`` is the class-based convenience that does the
same from constructor arguments.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from packaging.specifiers import SpecifierSet

from .constants import VCT
from .core import NameTypedProtocol, PluginArtifactProtocol

if TYPE_CHECKING:
    from .enrollment import EnrollmentKind
    from .field_kinds import FieldKindHandler


def python_specifier(spec: str) -> SpecifierSet:
    """A specifier set from what a plugin wrote: a bare version (``"3.13"``)
    reads as its floor (``>=3.13``), a specifier as itself."""
    text = spec.strip()
    if text and text[0] not in "<>=!~":
        text = f">={text}"
    return SpecifierSet(text)


@dataclass(frozen=True)
class PluginMetadata:
    """What a plugin tells the loader. ``services`` groups the classes to
    register under service names (a typical plugin registers a model class
    and its builder class under the plugin's ``type:`` key);
    ``builders_for_models`` maps each model class to its builder;
    ``injected_models`` are item models registered under a classification
    (``is_injected_models_default`` makes them that classification's
    default); ``version`` is the plugin's own, ``plugin_metadata_version``
    the shape of this record, ``python`` the interpreter it needs.

    ``namespace`` is the word the registry qualifies every registration of
    this record with (``<namespace>/<name>``), so two plugins may register
    one ``type:`` word under one classification and a tree may name either
    by its qualified form. Left ``None``, the loader derives it from the
    plugin's distribution name with the ``cs-image-system-`` prefix and
    the ``-plugin`` suffix dropped; a record with no distribution behind
    it (one built in a test) must name it or is refused.

    ``enrollment_kinds`` and ``field_kinds`` are the kinds the plugin
    provides: what it declares, which the loader registers for a plugin it
    accepts, after every collision among the installed plugins is settled.
    A plugin does not register a kind itself."""

    services: dict[str, list[type[PluginArtifactProtocol]]] = field(default_factory=dict)
    builders_for_models: dict[type[NameTypedProtocol], type] = field(default_factory=dict)
    injected_models: dict[VCT, type] = field(default_factory=dict)
    is_injected_models_default: bool = False
    version: str = "0"
    plugin_metadata_version: str = "1"
    python: str = ">=3.13"
    namespace: str | None = None
    enrollment_kinds: tuple[EnrollmentKind, ...] = ()
    field_kinds: Mapping[str, FieldKindHandler] = field(default_factory=dict)

    @property
    def requires_python(self) -> SpecifierSet:
        return python_specifier(self.python)
