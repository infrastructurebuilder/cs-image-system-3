# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The run context: what one run KNOWS.

:class:`RunContext` holds the merged configuration, the collections (read
live from the registry), the paths, the run id and start time, the scoping
flags and the per-run state a library or plugin keeps beside it. Nothing
here loads a configuration or executes a command: loading is
:mod:`cs_image_system.base.config_loader`'s, which constructs this object
and hands it out; the deferred-command queue and its executor are
:mod:`cs_image_system.base.finalizer`'s, reached through ``ctx.finalizer``.

The context is passed, never fetched: a command takes it as ``ctx``, a
builder holds the one it was bound to (``_get_context()``), a model holds
its run's registry. The process keeps no current context, so a process may
hold several, each with a registry, an image-source catalog and a template
resolver of its own, and none reads another's.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from cs_image_system.contract.constants import DEFAULT_GITIGNORE_ENTRIES, VCT
from cs_image_system.contract.context import RunContextProtocol, ServicesProtocol
from cs_image_system.contract.executables import ExecutableProtocol
from cs_image_system.contract.image import psi_key
from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
from cs_image_system.contract.lifecycles import LifecycleLike
from cs_image_system.contract.names import super_safe_name
from cs_image_system.contract.state import StateBuilderProtocol

from . import registry
from .image_sources import ImageSourceCatalog
from .lifecycles import runner_script_name
from .meta_state import META_STATE_DIRNAME, MetaState
from .models.provider_specific_image import ProviderSpecificImage

if TYPE_CHECKING:
    from .basic.builder_base import BuilderBase
    from .basic.builder_base_group import GroupBuilderBase
    from .basic.builder_base_image import ImageBuilderBase
    from .basic.builder_base_instance import InstanceBuilderBase
    from .basic.builder_base_mod import ModBuilderBase
    from .basic.builder_base_os import OsBuilderBase
    from .basic.builder_base_runtime import RuntimeBuilderBase
    from .basic.builder_base_storage import StorageBuilderBase
    from .basic.builder_base_user import UserBuilderBase
    from .finalizer import Finalizer
    from .models.base_image import BaseImage
    from .models.executable import ExecutableModel
    from .models.group import Group
    from .models.ia_config import IAConfig
    from .models.image import Image
    from .models.instance import Instance
    from .models.storage import Storage
    from .models.user import User
    from .orchestrator import TemplateResolver

log = logging.getLogger(__name__)


class RunContext(RunContextProtocol):
    """What one run knows: configuration, collections, paths, flags.

    The contract's :class:`~cs_image_system.contract.context.RunContextProtocol`
    is a base so pyright compares every member a plugin may
    read; the class has more than the protocol (the registry, the
    finalizer, the scoping flags), which is the engine's.

    Constructed by the loader (:func:`~.config_loader.read_config_and_transform`)
    with the full configuration and the three objects the loader made for
    this run before it (the registry, the image-source catalog and the
    template resolver); there is no partial construction and no
    no-argument accessor on this class. The builder collections and the
    domain-item collections are not cached here -- every property reads
    the registry, the single source of truth.
    """

    def __init__(self,
                 verbose: bool,
                 config_dir: Path,
                 config_data: IAConfig,
                 working_path: Path,
                 generation_directory: Path,
                 all_sorted_builders: list[BuilderBase],
                 *,
                 reg: registry.Registry,
                 image_sources: ImageSourceCatalog,
                 template_resolver: TemplateResolver,
                 dry_run: bool = True,
                 overlays: list[Path] | None = None,
                 overlay_data: list[dict[str, Any]] | None = None,
                 undeclared: list[tuple[str, str]] | None = None,
                 run_start_time: datetime | None = None,
                 ) -> None:
        # the run's registry, image-source catalog and template resolver: the
        # loader makes one of each per run and hands them in
        self.reg: registry.Registry = reg
        self._image_sources: ImageSourceCatalog = image_sources
        self._template_resolver: TemplateResolver = template_resolver
        self._dry_run = dry_run
        self._verbose = verbose or False
        self._run_start_time = run_start_time or datetime.now()
        self._config_dir = config_dir
        self._read_config = config_data
        self._working_path = working_path
        self._generation_path = generation_directory
        self._executables: dict[str, ExecutableModel] = config_data.executables_as_dict or {}
        self._all_sorted_builders: list[BuilderBase] = all_sorted_builders or []
        self._sleep_before_finalization: int = config_data.sleep_before_finalization
        lgie: list[str] = DEFAULT_GITIGNORE_ENTRIES + list(config_data.gitignore or [])
        # No dupes, and the LAST occurrence keeps its place: gitignore reads
        # later rules as overriding earlier ones, so a configuration that
        # restates a default (`!.terraform.lock.hcl` after its own `.*`)
        # means it there (a first-wins rule dropped the restatement and left
        # the built-in negation ahead of `.*`).
        self._gitignore_entries: list[str] = [e for i, e in enumerate(lgie) if e not in lgie[i + 1:]]
        # per-run state that a library or plugin keeps beside this context (a
        # terraform collector, say), created on first ask and gone with the context
        self._plugin_state: dict[str, Any] = {}
        # Transient declarations: overlay files merged over the tree
        # for THIS invocation only -- items by name, config keys by key. The
        # loader read them; the context only remembers what was read.
        self.overlays: list[Path] = list(overlays or [])
        self._overlay_data: list[dict[str, Any]] = list(overlay_data or [])
        self.overlay_declared: set[tuple[str, str]] = set()
        # `--undeclare <kind>:<name>` -- the overlay `undeclare` form as a
        # flag, so a live configuration needs no overlay file to decommission
        # a tree entry for one invocation
        self.undeclared: list[tuple[str, str]] = list(undeclared or [])
        # the foreign keys that named nothing at load -- (object
        # class, object name, field, value, target) -- as the object stage
        # returned them; set by the loader as the item kinds are read, read by
        # `validate`, which refuses each entry
        self.unresolved_foreign_keys: list[tuple[str, str, str, str, str]] = []
        self.apply_runtime: str | None = None      # `run --apply-runtime <rt>`
        # `run --migrate-state <ws>`: the workspaces whose state MOVES this run
        self.migrate_state: list[str] = []
        # run scoping safe by construction
        self.implied_scope: str | None = None      # --apply-runtime implied the bake filter to this runtime
        self.allow_unscoped_bakes: bool = False    # `run --allow-unscoped-bakes`
        self.explicit_bake_selection: bool = False # --only / --only-runtime given by the operator
        self.only_runtime_scope: str | None = None  # --only-runtime (explicit or implied): roots of other runtimes emit nothing
        # scoped-runs: the run's --only image selection; None = everything.
        # Image builders filter their enumeration on it (get_images).
        self.only_images: set[str] | None = None
        # convergent bakes: forced images (None = none; FORCE_ALL = all)
        # and the per-run cache of bake decisions (`<series>@<runtime>` -> reason|None)
        self.force_bake: set[str] | None = None
        self.bake_decisions: dict[str, str | None] = {}
        self._current_lifecycle: LifecycleLike | None = None
        self._generated_lifecycles: set[LifecycleLike] = set()
        self._meta_state: MetaState | None = None
        self._root_group: Group | None = None       # set by the groups kind's validator (the loader)
        self._finalizer: Finalizer | None = None    # bound by the loader
        self._services: ServicesProtocol | None = None   # bound by the loader
        # what the adoption of meta-state/runtime-facts.yaml left
        # unanswered (a `default` network nothing recorded, a subnet the record
        # never checked); set by the loader's adopt, reported by a validator
        self.network_facts_problems: list[str] = []

    # --- identity: a context is shared, never cloned
    # A model copy (`copy.deepcopy(executable)`, a builder's executable copy)
    # must share the run it belongs to. Without this, the copy walked from the
    # model's registry handle to the builders, from a builder to its bound
    # context and from there to the whole run -- every builder, model and
    # collector -- a copy that ran for hours and took tens of gigabytes.
    def __deepcopy__(self, memo: dict[int, Any]) -> RunContext:
        memo[id(self)] = self
        return self

    def __copy__(self) -> RunContext:
        return self

    @property
    def image_sources(self) -> ImageSourceCatalog:
        """This run's image-source catalog: the release's entries over the
        registry's runtimes, the tree's entries on them."""
        return self._image_sources

    @property
    def template_resolver(self) -> TemplateResolver:
        """This run's object stage: the flat map of its structured models,
        and the converter that structures more of them (a base image an OS
        builder synthesises, the item kinds the loader reads)."""
        return self._template_resolver

    # --- the finalizer handle
    @property
    def finalizer(self) -> Finalizer:
        """The deferred-command queue and executor of this run, made and
        bound by the loader (:mod:`~.finalizer`)."""
        if self._finalizer is None:
            raise RuntimeError("this run context has no finalizer bound; the loader binds one")
        return self._finalizer

    def bind_finalizer(self, finalizer: Finalizer) -> None:
        self._finalizer = finalizer

    # --- the services behind the context
    @property
    def services(self) -> ServicesProtocol:
        """The engine's run-bound knowledge as a plugin reaches it
        (``ctx.services.lineage``, ``.launch``, ``.secrets``, ``.files``,
        ``.commands``, ``.images``, ``.identity``, ``.storage``,
        ``.meta_state``): adapters the loader binds, each delegating to the
        module the functions live in."""
        if self._services is None:
            raise RuntimeError("this run context has no services bound; the loader binds them")
        return self._services

    def bind_services(self, services: ServicesProtocol) -> None:
        self._services = services

    # --- flags and defaults
    @property
    def dry_run(self) -> bool:
        """When set, finalization enumerates deferred commands without executing."""
        return self._dry_run
    def _require_default(self, vct: VCT, label: str) -> str:
        """The registry's default builder name for ``vct``, or raise if unset."""
        dflt = self.reg.get_default_for(vct)
        if not dflt:
            raise ValueError(f"No default {label} configured")
        return dflt
    @property
    def default_mod_builder(self) -> str:
        return self._require_default(VCT.MOD_BUILDER_MODEL, "mod builder")
    @property
    def default_image_builder(self) -> str:
        return self._require_default(VCT.IMAGE_BUILDER_MODEL, "image builder")
    @property
    def default_instance_builder(self) -> str:
        return self._require_default(VCT.INSTANCE_BUILDER_MODEL, "instance builder")
    @property
    def default_runtime_builder(self) -> str:
        return self._require_default(VCT.RUNTIME_BUILDER_MODEL, "runtime builder")
    @property
    def default_os_builder(self) -> str:
        return self._require_default(VCT.OS_BUILDER_MODEL, "OS builder")
    @property
    def default_storage_builder(self) -> str:
        return self._require_default(VCT.STORAGE_BUILDER_MODEL, "storage builder")
    @property
    def default_group_builder(self) -> str:
        return self._require_default(VCT.GROUP_BUILDER_MODEL, "group builder")
    @property
    def default_user_builder(self) -> str:
        return self._require_default(VCT.USER_BUILDER_MODEL, "user builder")
    @property
    def default_state_backend(self) -> str:
        return self._require_default(VCT.STATE_BACKEND_MODEL, "state backend")

    # --- the run
    @property
    def start_time(self) -> datetime:
        return self._run_start_time
    @property
    def iso_start_time(self) -> str:
        return self._run_start_time.isoformat()
    @property
    def iso_sanitized(self) -> str:
        return super_safe_name(self.iso_start_time)
    @property
    def run_id(self) -> str:
        """Run identifier: the run-start timestamp, sanitized."""
        return self.iso_sanitized
    @property
    def sleep_before_finalization(self) -> int:
        return self._sleep_before_finalization
    @property
    def verbose(self) -> bool:
        return self._verbose or False
    @property
    def dateformat(self) -> str:
        """The tree's ``dateformat``: the timestamp format a build's final
        name carries (a plugin reads it here, not the model)."""
        return self._read_config.dateformat

    # --- paths
    @property
    def root_dir(self) -> Path:
        return self._config_dir
    @property
    def working_path(self) -> Path:
        return self._working_path
    @property
    def generation_path(self) -> Path:
        """Where generated files land RIGHT NOW.

        V2: while a lifecycle is current, its own directory
        (``generated/<lifecycle>/``) so every builder's relative output paths
        (``<builder>/<phase>/...``) relocate under it unchanged (DESIGN §3A).
        Legacy: the base-only tree for base-only runs, else the root.
        """
        if self._current_lifecycle is not None:
            return self._generation_path / self._current_lifecycle.value
        return self._generation_path
    @property
    def root_generation_path(self) -> Path:
        """The root of the generated tree (``generated/``), lifecycle-independent."""
        return self._generation_path
    def lifecycle_generation_path(self, lifecycle: LifecycleLike) -> Path:
        return self._generation_path / lifecycle.value
    def runner_script_path(self, lifecycle: LifecycleLike) -> Path:
        """``generated/<lifecycle>/run-<lifecycle>.sh`` (DESIGN §3C)."""
        return self.lifecycle_generation_path(lifecycle) / runner_script_name(lifecycle)
    @property
    def gating_script_path(self) -> Path:
        """The root ``final_execution.sh``: runs each lifecycle's runner script
        when (and only when) it exists."""
        return self._generation_path / "final_execution.sh"
    @property
    def meta_state_path(self) -> Path:
        """``<config root>/meta-state`` -- outside every generated directory."""
        return self._working_path / META_STATE_DIRNAME
    @property
    def meta_state(self) -> MetaState:
        if self._meta_state is None:
            self._meta_state = MetaState(self.meta_state_path)
        return self._meta_state

    # --- lifecycle state of the run
    @property
    def current_lifecycle(self) -> LifecycleLike | None:
        return self._current_lifecycle
    @current_lifecycle.setter
    def current_lifecycle(self, lifecycle: LifecycleLike | None) -> None:
        self._current_lifecycle = lifecycle
    @property
    def generated_lifecycles(self) -> set[LifecycleLike]:
        """Lifecycles whose generation completed in THIS run."""
        return set(self._generated_lifecycles)
    def mark_generated(self, lifecycle: LifecycleLike) -> None:
        self._generated_lifecycles.add(lifecycle)
    def reset_generated_lifecycles(self) -> None:
        """Start-of-run reset: 'generated in THIS run' must never carry over
        (finding 34 -- the apply step trusts this set to scope execution)."""
        self._generated_lifecycles = set()
    def plugin_state(self, key: str, factory: Callable[[], Any]) -> Any:
        """The one object a library or plugin keeps for this run under
        ``key``: made by ``factory`` on the first ask, the same object after,
        and gone when the context is. The core names none of them; this is
        how a collector or a cache lives beside the context without being
        process-wide state."""
        if key not in self._plugin_state:
            self._plugin_state[key] = factory()
        return self._plugin_state[key]

    # --- the configuration
    @property
    def read_config(self) -> IAConfig:
        return self._read_config
    @property
    def config(self) -> dict[str, Any]:
        """The global ``config:`` map from the merged configuration."""
        return self._read_config.config or {}
    @property
    def executables(self) -> dict[str, ExecutableModel]:
        return self._executables or {}
    @property
    def gitignore(self) -> list[str]:
        return self._gitignore_entries

    # --- the builders: read straight from the registry, keyed by builder name
    @property
    def image_builders(self) -> dict[str, ImageBuilderBase]:
        return self.reg.get_all_instances_by_classification(VCT.IMAGE_BUILDER)
    @property
    def instance_builders(self) -> dict[str, InstanceBuilderBase]:
        return self.reg.get_all_instances_by_classification(VCT.INSTANCE_BUILDER)
    @property
    def mod_builders(self) -> dict[str, ModBuilderBase]:
        return self.reg.get_all_instances_by_classification(VCT.MOD_BUILDER)
    @property
    def runtime_builders(self) -> dict[str, RuntimeBuilderBase]:
        return self.reg.get_all_instances_by_classification(VCT.RUNTIME_BUILDER)
    @property
    def storage_builders(self) -> dict[str, StorageBuilderBase]:
        return self.reg.get_all_instances_by_classification(VCT.STORAGE_BUILDER)
    @property
    def os_builders(self) -> dict[str, OsBuilderBase]:
        return self.reg.get_all_instances_by_classification(VCT.OS_BUILDER)
    @property
    def group_builders(self) -> dict[str, GroupBuilderBase]:
        return self.reg.get_all_instances_by_classification(VCT.GROUP_BUILDER)
    @property
    def user_builders(self) -> dict[str, UserBuilderBase]:
        return self.reg.get_all_instances_by_classification(VCT.USER_BUILDER)
    @property
    def all_sorted_builders(self) -> list[BuilderBase]:
        return self._all_sorted_builders or []
    @property
    def state_backends(self) -> dict[str, StateBuilderProtocol]:
        return self.reg.get_all_instances_by_classification(VCT.STATE_BACKEND)
    @property
    def provider_specific_images(self) -> dict[str, ProviderSpecificImage]:
        """All registered provider-specific images, keyed by '<source>::<runtime>'."""
        return self.reg.get_all_instances_by_classification(VCT.PROVIDER_SPECIFIC_IMAGE)
    def get_provider_specific_image(self, source_name: str, runtime: str) -> ProviderSpecificImage | None:
        """Get the provider-specific image for a source (Image or OsBuilder name) on a runtime.

        The runtime may be given by name, alias, or the DEFAULT sentinel; it is
        canonicalized before the lookup because provider-specific images are
        keyed by the runtime builder's canonical name.
        """
        rtb = self.reg.get_instance_by_name_or_alias(VCT.RUNTIME_BUILDER, runtime)
        runtime_name = rtb.get_name() if rtb is not None else runtime
        return self.reg.get_instance_by_name_or_alias(
            VCT.PROVIDER_SPECIFIC_IMAGE, psi_key(source_name, runtime_name)
        )

    # --- the domain items: read live from the registry, keyed by item name
    @property
    def instances(self) -> list[Instance]:
        return list(self.reg.get_all_instances_by_classification(VCT.INSTANCE_MODEL).values())
    @property
    def base_images(self) -> list[BaseImage]:
        return list(self.reg.get_all_instances_by_classification(VCT.BASE_IMAGE_MODEL).values())
    @property
    def images(self) -> list[Image]:
        return list(self.images_map.values())
    @property
    def images_map(self) -> dict[str, Image]:
        return self.reg.get_all_instances_by_classification(VCT.IMAGE_MODEL)
    @property
    def groups(self) -> list[Group]:
        return list(self.reg.get_all_instances_by_classification(VCT.GROUP_MODEL).values())
    @property
    def users(self) -> list[User]:
        return list(self.reg.get_all_instances_by_classification(VCT.USER_MODEL).values())
    @property
    def storages(self) -> list[Storage]:
        return list(self.reg.get_all_instances_by_classification(VCT.STORAGE_MODEL).values())
    @property
    def root_group(self) -> Group:
        if self._root_group is None:
            root_groups = [g for g in self.groups if g.is_root]
            if root_groups:
                if len(root_groups) > 1:
                    raise ValueError("Multiple 'root' groups found, expected only one")
                else:
                    self._root_group = root_groups[0]
            else:
                raise ValueError("No 'root' group found in groups list, expected one ")
        return self._root_group

    # --- the one finalizer verb a plugin reaches through the context (the
    # contract's ``RunContextProtocol`` declares it); everything else of the
    # finalizer is reached as ``ctx.finalizer.<name>``
    def extend_finalization_phase(
        self, phase: ExecutionLifecyclePhase, executables: Sequence[ExecutableProtocol]
    ) -> None:
        """Queue ``executables`` for ``phase`` on this run's finalizer.
        Takes the contract's executables: what a plugin queues comes from
        this run's ``executables`` map, the kit's models."""
        self.finalizer.extend_finalization_phase(phase, cast("list[ExecutableModel]", list(executables)))
