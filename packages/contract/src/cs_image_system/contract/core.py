# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What every model and every builder is to the system (stage 30).

The protocols here carry NO implementation: a default body lives in the
core's base classes (``cs_image_system.base``), which implement these
protocols nominally so pyright checks them at definition time, and which a
plugin may subclass for convenience. A plugin that satisfies a protocol
structurally is a first-class plugin; ``testing.assert_conforms`` is the
signature-level check.

Runtime checks (``isinstance`` in the loader, the registry and the
orchestrator) are name-only, as ``runtime_checkable`` makes them; the
conformance test is what makes that looseness safe. The protocols here
are ``runtime_checkable``; those with a property or data member
(``NameTypedProtocol``, ``PluginMetadataProtocol``, ``BuilderModelProtocol``,
``ParentPropertyHoldingProtocol``) support ``isinstance`` but not
``issubclass``. The kind protocols in the other modules are typing only:
``isinstance`` against one raises ``TypeError``, and ``assert_conforms`` is
the check.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from packaging.specifiers import SpecifierSet

from .assets import AssetSet
from .constants import VCT
from .executables import CFExecutables
from .lifecycle import ExecutionLifecyclePhase


@runtime_checkable
class PluginArtifactProtocol(Protocol):
    """What a class a plugin registers answers: its canonical name (for a
    builder model, the value a YAML ``type:`` names) and the classification
    it registers under. The registry resolves a ``type:`` through these."""

    @classmethod
    def csis_name(cls) -> str: ...

    @classmethod
    def csis_classifier(cls) -> VCT: ...


@runtime_checkable
class NameTypedProtocol(Protocol):
    """What the registry needs of anything it holds: a name, a type, a
    description, aliases, a classification and a global id
    (``<classification>::<model id>::<name>``)."""

    def get_name(self) -> str: ...

    def get_type(self) -> str: ...

    def get_description(self) -> str | None: ...

    def get_aliases(self) -> set[str]: ...

    def get_classification(self) -> VCT: ...

    @property
    def global_id(self) -> str: ...


@runtime_checkable
class PluginMetadataProtocol(Protocol):
    """What a plugin's entry point returns: the classes to register, grouped
    under service names, the builder for each model, the item models it
    injects, and its versions. ``metadata.PluginMetadata`` is the data
    record that satisfies it; the core's ``AbstractPluginMetadata`` is the
    class-based convenience."""

    @property
    def plugin_metadata_version(self) -> str:
        """ Parseable version string of the plugin metadata """
        ...

    @property
    def version(self) -> str:
        """ Parseable version string of the plugin """
        ...

    @property
    def requires_python(self) -> SpecifierSet:
        """ Python version specifier required by the plugin """
        ...

    @property
    def services(self) -> dict[str, list[type[PluginArtifactProtocol]]]:
        """ Model types that this plugin supports. """
        ...

    @property
    def builders_for_models(self) -> dict[type[NameTypedProtocol], type]:
        """ Builders for the model types that this plugin supports. """
        ...

    @property
    def injected_models(self) -> dict[VCT, type]:
        """ Models that this plugin injects into the system, keyed by an internal type. """
        ...

    @property
    def is_injected_models_default(self) -> bool:
        """ Whether the injected models should be treated as defaults that can be overridden by other plugins. """
        ...


@runtime_checkable
class SelfInjectedNameProtocol(Protocol):
    """An item that enters the Jinja context under a name of its own (an
    image as ``image``, a group as ``group``): the orchestrator asks it."""

    def get_self_injected_name(self) -> str: ...


@runtime_checkable
class SubItemOverrideProtocol(Protocol):
    """An item that names the concrete class of its sub-items per
    classification (an instance's storage mappings)."""

    def get_subitem_overrides(self) -> dict[VCT, type]: ...


@runtime_checkable
class ParentPropertyHoldingProtocol(Protocol):
    """An item that holds the model it belongs to by reference: ``_model_id``
    is the parent's global id (``fields.parent_field`` declares it; a
    protocol cannot carry a dataclass field), ``model_id`` reads and sets it,
    ``identified_model`` and ``builder`` resolve it through the registry.
    The core's ``ParentPropertyHolding`` mixin is the implementation."""

    _model_id: str | None

    @property
    def model_id(self) -> str | None: ...

    @model_id.setter
    def model_id(self, model_name: str) -> None: ...

    @property
    def identified_model(self) -> Any: ...

    @property
    def builder(self) -> Any: ...


@runtime_checkable
class BuilderModelProtocol(NameTypedProtocol, PluginArtifactProtocol, Protocol):
    """A builder's configuration entry: the mandatory interface of every
    builder model. The attributes are what the core reads of any builder
    model; a kind's module declares what more it reads. A model is a pydantic
    dataclass under ``model_config.CSIS_MODEL_CONFIG`` whose ``type`` field
    (``type_``, aliased) carries the plugin's ``csis_name``."""

    name: str
    type_: str
    description: str | None
    aliases: set[str]
    executable: str | None
    is_default: bool
    config: dict[str, Any]
    gitignore: list[str]
    tags: dict[str, str]

    def get_display_name(self) -> str: ...

    def get_executable(self) -> str | None: ...

    def get_is_default(self) -> bool: ...

    def get_config(self) -> dict[str, Any]: ...

    def get_gitignore(self) -> list[str]: ...

    def get_tags(self) -> dict[str, str]: ...

    def finalize(self) -> None:
        """
        Finalize the builder model.  Subclasses should call their parent's finalize method
        appropriately.
        Calls to finalize() will be made after all builders of a type have been initially
        processed in order of precedence:
        1. Runtime builders
        2. Group builders
        3. Storage builders
        4. Mod builders
        5. Image builders
        6. Instance builders
        """
        ...


class RuntimeEnabledBuilderModelProtocol(BuilderModelProtocol, Protocol):
    """A builder model that operates in a runtime (storage, image and
    instance builders): ``runtime`` names it, ``DEFAULT`` until resolved."""

    runtime: str

    def get_runtime_provider(self) -> str: ...


class BuilderProtocol(NameTypedProtocol, PluginArtifactProtocol, Protocol):
    """The builder surface the core drives: the six universal lifecycle
    hooks (``generate_items_*`` return assets, ``get_commands_to_run_*``
    return command lists), the three finalize-phase hooks around a phase's
    deferred commands, ``finalize`` once the configuration is complete, and
    the paths and names the runner files its output under. The core's
    ``BuilderBase`` implements it; a kind's module adds the domain hooks.
    Nothing here reaches the run context (that interface is a later stage)."""

    @property
    def model(self) -> Any: ...

    @property
    def name(self) -> str: ...

    @property
    def type_(self) -> str: ...

    def get_display_name(self) -> str: ...

    def get_tags(self) -> Mapping[str, str]: ...

    def get_config(self) -> dict[str, str] | None: ...

    def add_item(self, item: Any, *args: Any, **kwargs: Any) -> None: ...

    def pre_finalize_phase(self, phase: ExecutionLifecyclePhase) -> None: ...

    def post_finalize_phase(self, phase: ExecutionLifecyclePhase) -> None: ...

    def post_failed_phase(self, phase: ExecutionLifecyclePhase) -> None: ...

    def get_builder_path(self) -> Path: ...

    def get_discriminator(self) -> str: ...

    def get_path_for_phase(self, phase: ExecutionLifecyclePhase, discriminator: str | None = None,
                           suffix: str | None = None) -> Path: ...

    def copy_external_assets(self, target_path: Path, mod: Any = None) -> dict[str, Path]: ...

    def generate_items_before(self, phase: ExecutionLifecyclePhase) -> AssetSet: ...

    def get_commands_to_run_before(self, phase: ExecutionLifecyclePhase) -> CFExecutables: ...

    def generate_items_during(self, phase: ExecutionLifecyclePhase) -> AssetSet: ...

    def get_commands_to_run_during(self, phase: ExecutionLifecyclePhase) -> CFExecutables: ...

    def generate_items_after(self, phase: ExecutionLifecyclePhase) -> AssetSet: ...

    def get_commands_to_run_after(self, phase: ExecutionLifecyclePhase) -> CFExecutables: ...

    def finalize(self) -> None: ...
