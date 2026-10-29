# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The record a plugin's entry point returns (stage 30).

A plugin's ``initialize`` returns one :class:`PluginMetadata` (or a list of
them): the classes to register under service names, the builder class for
each model class, the item models it injects, and its versions. It
satisfies ``core.PluginMetadataProtocol`` as data; the core's
``AbstractPluginMetadata`` is the class-based convenience that does the
same from constructor arguments.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packaging.specifiers import SpecifierSet

from .constants import VCT
from .core import NameTypedProtocol, PluginArtifactProtocol


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
    the shape of this record, ``python`` the interpreter it needs."""

    services: dict[str, list[type[PluginArtifactProtocol]]] = field(default_factory=dict)
    builders_for_models: dict[type[NameTypedProtocol], type] = field(default_factory=dict)
    injected_models: dict[VCT, type] = field(default_factory=dict)
    is_injected_models_default: bool = False
    version: str = "0"
    plugin_metadata_version: str = "1"
    python: str = ">=3.13"

    @property
    def requires_python(self) -> SpecifierSet:
        return python_specifier(self.python)
