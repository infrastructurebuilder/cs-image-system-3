# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import is_dataclass
from .models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
import logging
import os
from pathlib import Path
from datetime import datetime
from pprint import pformat
from typing import Any
import typer
import yaml

from cs_image_system.base.models.base_image import BaseImage

from .orchestrator import Orchestrator, TemplateResolver

from .protocols.state_management import StateManagementRootProtocol

from .models.user import User
from .models.ia_config import IAConfig
from typing import TYPE_CHECKING
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
from . import registry
from .utils import super_safe_name
from .template_utils import cycle_main_yaml, read_and_preprocess_yaml_files
from .encryption import decrypt_tree, decrypted_plaintexts, refuse_markers_at
from .materialize import ensure_ignored, materialize, mirror_path, sync_back

log = logging.getLogger(__name__)

from .constants import (
    BASE_IMAGES,
    DEFAULT_GITIGNORE_ENTRIES,
    GROUPS,
    IMAGES,
    INSTANCES,
    OOPS_DEFAULTS,
    PLUGIN_TYPES,
    STORAGES,
    VCT,
)


from .lifecycle import ExecutionLifecyclePhase
from .lifecycles import LifecycleLike, all_lifecycles, runner_script_name
from .meta_state import META_STATE_DIRNAME, MetaState
from .models.group import Group
from .models.image import Image
from .models.instance import Instance
from .models.storage import Storage
from .models.group_builder import GroupBuilderModel
from .models.image_builder_model import ImageBuilderModel
from .models.instance_builder import InstanceBuilderModel
from .models.mod_builder import ModBuilderModel
from .models.os_builder_model import OsBuilderModel
from .models.provider_specific_image import ProviderSpecificImage, psi_key
from .models.runtime import RuntimeBuilderModel
from .models.state_builder import StateBuilderModel
from .models.storage_builder import StorageBuilderModel
from .models.user_builder import UserBuilderModel

from .singleton import singleton

from .models.executable import ExecutableModel

from .basic.builder_base import BuilderBase
from .models.builder_model import BuilderModel, NameTyped
from .protocols.builder_model_protocol import BuilderModelProtocol
from .protocols.name_typed_protocol import NameTypedProtocol
from .protocols.plugin_metadata import PluginArtifactProtocol

PLUGIN_TYPEMAP: dict[str, type] = {
    "base" : dict,
    "runtime": RuntimeBuilderModel,
    "state": StateBuilderModel,
    "modification": ModBuilderModel,
    "storage": StorageBuilderModel,
    "group": GroupBuilderModel,
    "user": UserBuilderModel,
    "os": OsBuilderModel,
    "image": ImageBuilderModel,
    "instance": InstanceBuilderModel,
    "other": dict,
    "executables": ExecutableModel,
}


@dataclass(frozen=True, config=CSIS_MODEL_CONFIG)
class ItemKind:
    """Declarative spec for reading one domain-item collection from YAML.

    The generic reader :meth:`GlobalTypeContext._read_item_kind` turns each spec
    into the read -> structure -> resolve -> register -> attach-to-builder flow that
    used to be copy-pasted as ``read_*_from_files``. Register additional kinds via
    :func:`register_item_kind` -- this is the extension seam for a plugin that
    manages a new kind of domain item.

    ``model_cls`` must be a :class:`~.models.builder_model.NameTyped` subclass:
    the reader relies on its ``name``/``type`` fields (``type`` is the FK naming
    the owning builder) and its registrability.
    """
    name: str                                   # collection name; result stored on self._<name>
    source_dir: str                             # subdir under working_path (constants.IMAGES, ...)
    model_cls: type[NameTyped]                  # dataclass the YAML items structure into
    builder_vct: VCT                            # classification of the builder that owns each item
    attach: Callable[[Any, Any], None]          # (builder, item) -> None, e.g. b.add_image(item)
    default_missing_type_to: VCT | None = None  # if item.type_ is a DEFAULT sentinel, fill from this VCT's default
    validate: Callable[["GlobalTypeContext", list[Any]], None] | None = None
    base_only: bool = False                     # read in base-only mode instead of the normal flow


_ITEM_KINDS: list[ItemKind] = []


def register_item_kind(spec: ItemKind) -> None:
    """Register a domain-item kind to be read during ``GlobalTypeContext.__post_init__``."""
    _ITEM_KINDS.append(spec)


def item_kinds() -> list[ItemKind]:
    """The registered domain-item kinds, in read order."""
    return list(_ITEM_KINDS)


@singleton
class GlobalTypeContext:
    """
    This class serves as a global context for the state of the running application.
    It allows us to consume the typer context and associated data, but then be fully
    detached from that one processing starts.

    This is where we will store all the "global" data that needs to be accessed across
    the application, such as the list of builders, the list of images/instances/groups, etc.

    This object is a singleton (you can only ever have one instance), and once it has been
    created, you can get that instance (with all its data) just by calling this class's
    constructor with no arguments.  (e.g. `ctx = GlobalTypeContext()`)

    """
    _run_start_time: datetime
    _root_dir: Path
    _working_path: Path
    _generation_path: Path
    _read_config: IAConfig
    _verbose: bool = False
    _executables: dict[str, ExecutableModel] = {}
    # Builder collections (image/instance/mod/runtime/storage/os/group/user builders
    # and state_backends) are NOT cached here -- the properties read them from the
    # registry. See the *_builders / state_backends properties.
    _all_sorted_builders: list[BuilderBase] = []
    # Deferred (finalization) executables, bucketed by the lifecycle that was
    # current when they were recorded (None = the legacy single-script flow).
    # Allocated per instance in __init__: a class-level dict leaked commands
    # between contexts.
    _finalization: dict[LifecycleLike | None, dict[ExecutionLifecyclePhase, list[ExecutableModel]]]
    _current_lifecycle: LifecycleLike | None = None
    _generated_lifecycles: set[LifecycleLike]
    _final_execution_path: Path
    # default_* builder names are read live from the registry (see default_* props).

    # Domain-item collections (base_images/instances/images/groups/users/storages)
    # are read live from the registry by their properties -- not cached here.
    _root_group: Group = None  # type: ignore

    _sleep_before_finalization: int = 1     # the model's default (stage 67; it said 10)

    _gitignore_entries: list[str] = []


# --- Properties
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
    @property
    def start_time(self) -> datetime:
        return self._run_start_time
    @property
    def iso_start_time(self) -> str:
        return self._run_start_time.isoformat()
    @property
    def iso_sanitized(self) -> str:
        return  super_safe_name(self.iso_start_time)
    @property
    def sleep_before_finalization(self) -> int:
        return self._sleep_before_finalization
    @property
    def verbose(self) -> bool:
        return self._verbose or False
    @property
    def root_dir(self) -> Path:
        return self._root_dir
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
    @property
    def meta_state_path(self) -> Path:
        """``<config root>/meta-state`` -- outside every generated directory."""
        return self._working_path / META_STATE_DIRNAME
    @property
    def meta_state(self) -> MetaState:
        ms: MetaState | None = getattr(self, "_meta_state", None)
        if ms is None:
            ms = MetaState(self.meta_state_path)
            self._meta_state = ms
        return ms
    @property
    def run_id(self) -> str:
        """Run identifier: the run-start timestamp, sanitized."""
        return self.iso_sanitized
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
    # The builder collections are not stored on the context; they are read straight
    # from the registry (single source of truth), keyed by builder name.
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
    def state_backends(self) -> dict[str, StateManagementRootProtocol]:
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
    # Domain-item collections are read live from the registry (single source of
    # truth), keyed by item name. The readers populate the registry; nothing is
    # cached on the context.
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
    def gitignore(self) -> list[str]:
        return self._gitignore_entries
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
    def extend_finalization_phase(
        self, phase: ExecutionLifecyclePhase, executables: list[ExecutableModel]
    ) -> None:
        """Extend the list of executables to run at finalization for a given phase."""
        if phase.index_of() > ExecutionLifecyclePhase.PRE_VERIFY.index_of():
            if executables:
                log.critical("Cannot extend finalization phase after PRE_VERIFY. ")
                raise ValueError("Extending finalization phase after PRE_VERIFY not allowed")
        if not executables:
            return
        bucket = self._finalization.setdefault(self._current_lifecycle, {})
        bucket.setdefault(phase, []).extend(executables)

    def get_finalization_executables_for_phase(
        self, phase: ExecutionLifecyclePhase, lifecycle: LifecycleLike | None | str = "current",
    ) -> list[ExecutableModel]:
        """Deferred executables for ``phase`` recorded under ``lifecycle``
        (default: the lifecycle that is current now; ``None`` = legacy flow)."""
        key = self._current_lifecycle if lifecycle == "current" else lifecycle
        return self._finalization.get(key, {}).get(phase, [])  # type: ignore[arg-type]

    def finalization_phases_for(self, lifecycle: LifecycleLike | None) -> list[ExecutionLifecyclePhase]:
        """Phases with deferred executables under ``lifecycle``, in enum order."""
        bucket = self._finalization.get(lifecycle, {})
        return [p for p in ExecutionLifecyclePhase if bucket.get(p)]

    @property
    def final_execution_path(self) -> Path:
        return self._final_execution_path

    @staticmethod
    def render_executable_line(executable: ExecutableModel) -> str:
        """One reviewable shell line for a deferred executable."""
        return render_executable_line(executable)

    def write_final_execution_script(self) -> Path:
        """Legacy single-script flow: write the accumulated deferred commands
        (recorded with no lifecycle current) to ``final_execution_path``.

        The script is a phase-ordered, reviewable (and manually runnable)
        record of what finalization will execute. Note that the real
        finalization path runs these commands in-process so the builders'
        pre/post_finalize_phase hooks (packer-manifest parsing, instance
        tfvars) fire between phases -- running the script by hand skips
        those hooks.
        """
        lines = script_lines(self, [
            "# Generated by cs-image-system finalization.",
            "# Phase-ordered deferred commands accumulated during generation.",
        ], None, script_dir=Path(self.final_execution_path).parent)
        script = write_script(self.final_execution_path, lines)
        log.info(f"Wrote finalization script to {script}")
        return script

    def write_lifecycle_runner_script(self, lifecycle: LifecycleLike,
                                      extra_header: list[str] | None = None) -> Path | None:
        """Write ``generated/<lifecycle>/run-<lifecycle>.sh`` (DESIGN §3C).

        Only written when the lifecycle recorded deferred work: the script's
        very existence is the apply gate (script exists -> it runs; absent ->
        that lifecycle is a no-op), so an empty lifecycle must leave no script
        behind.
        """
        if not self.finalization_phases_for(lifecycle):
            log.info(f"Lifecycle {lifecycle.value}: no deferred commands; no runner script written")
            return None
        header = [
            f"# cs-image-system lifecycle runner: {lifecycle.value}",
            f"# run id: {self.run_id}",
            "# Deferred commands accumulated while generating this lifecycle,",
            "# in phase order. Paths are relative to this lifecycle's directory.",
        ]
        if extra_header:
            header.extend(extra_header)
        lines = script_lines(self, header, lifecycle, script_dir=self.lifecycle_generation_path(lifecycle))
        script = write_script(self.runner_script_path(lifecycle), lines)
        log.info(f"Wrote lifecycle runner script to {script}")
        return script

    def write_gating_script(self) -> Path:
        """The root ``final_execution.sh``: GOALS.md 5.5's gating mechanism in
        shell form -- each lifecycle's runner runs iff its script exists."""
        lines = [
            "#!/usr/bin/env bash",
            "# Generated by cs-image-system (V2 meta-workflow).",
            "# Runs each lifecycle's runner script in meta-workflow order, if and",
            "# only if that script exists. An absent script is a no-op lifecycle.",
            "set -euo pipefail",
            'cd "$(dirname "$0")"',
            f"for lc in {' '.join(lc.value for lc in all_lifecycles())}; do",
            '  script="$lc/run-$lc.sh"',
            '  if [ -x "$script" ]; then',
            '    echo "== lifecycle $lc: running $script"',
            '    "$script"',
            "  else",
            '    echo "== lifecycle $lc: no runner script; skipping"',
            "  fi",
            "done",
        ]
        return write_script(self.gating_script_path, lines)

    def final_execute(self) -> bool:
        """Run all deferred (finalize) executables, phase by phase, fail-fast.

        Phases run in enum definition order, so IMAGE_GENERATION's packer builds
        run before INSTANCE_GENERATION's terraform plan/apply. Around each
        phase's commands, every builder's pre/post_finalize_phase hooks fire —
        e.g. the packer builder parses build manifests after its builds, and the
        instance builder writes concrete AMI tfvars before its plan/apply.
        """
        self.write_final_execution_script()
        pwd = Path(os.getcwd()).absolute()
        try:
            for phase in ExecutionLifecyclePhase:
                executables = self.get_finalization_executables_for_phase(phase)
                if not executables:
                    continue
                if self.dry_run:
                    # Enumerate only: no commands, no pre/post hooks (hooks have
                    # side effects like writing tfvars / parsing build manifests
                    # that only make sense when the commands actually ran).
                    for executable in executables:
                        log.info(
                            f"[DRY RUN] phase {phase.value}: would execute "
                            f"{executable.binary} {' '.join(executable.args)} "
                            f"in {executable.working_directory if executable.working_directory else 'current working directory'}"
                        )
                    continue
                for builder in self.all_sorted_builders:
                    builder.pre_finalize_phase(phase)
                for executable in executables:
                    log.info(
                        f"Final execution of command for phase {phase.value}: "
                        f"{executable.binary} {' '.join(executable.args)} "
                        f"in {executable.working_directory if executable.working_directory else 'current working directory'}"
                    )
                    os.chdir(self.generation_path)
                    executable = materialized_for(getattr(self, "working_path", None),
                                                  self.generation_path, executable)
                    try:
                        res = executable.execute(skips=False)
                    except Exception as e:
                        log.error(
                            f"Final execution failed for command in phase {phase.value}: "
                            f"{executable.binary} {' '.join(executable.args)} ({e})"
                        )
                        return False
                    finally:
                        os.chdir(pwd)
                    if not res or res.returncode != 0:
                        rc = str(res.returncode) if res else "None"
                        log.error(
                            f"Final execution failed for command in phase {phase.value}: "
                            f"{executable.binary} {' '.join(executable.args)} "
                            f"(Return code: {rc})"
                        )
                        return False
                for builder in self.all_sorted_builders:
                    builder.post_finalize_phase(phase)
        finally:
            os.chdir(pwd)
        return True










    def _read_item_kind(self, spec: ItemKind) -> list[Any]:
        """Generic reader replacing the per-type ``read_*_from_files`` methods.

        Reads the YAML for a domain-item collection, structures each item into
        ``spec.model_cls``, resolves templates, registers the item, resolves its
        owning builder from the registry (alias-aware) and attaches it, then runs
        the kind's optional cross-item validation.
        """
        yaml_files = get_files_by_extensions(self.working_path / spec.source_dir)
        cvt = Orchestrator().get_converter()
        template_resolver = TemplateResolver()
        from .orchestrator import reset_unresolved_fks
        reset_unresolved_fks()          # stage 48.3: a fresh load starts with no unresolved foreign keys
        reg = self.reg
        items: list[NameTyped] = []
        try:
            read_dict = read_and_preprocess_yaml_files(spec.model_cls, yaml_files)[0]
            apply_overlays(self, spec, read_dict)
            for _key, raw in read_dict.items():
                structured = cvt.structure(raw, spec.model_cls)
                for ri in (structured if isinstance(structured, list) else [structured]):
                    if isinstance(ri, spec.model_cls):
                        items.append(ri)
                        template_resolver.flatten_dataclass(ri)
                        reg.register_built_instance(ri)
        except Exception as e:
            log.error(f"Error parsing {yaml_files}: {e}")
            raise
        template_resolver.resolve_all()
        for it in items:
            if spec.default_missing_type_to is not None and it.type_ in OOPS_DEFAULTS:
                log.debug(f"{spec.name} item '{it.get_name()}' using default builder")
                dflt = reg.get_default_for(spec.default_missing_type_to)
                if not dflt:
                    raise ValueError(
                        f"{spec.name} item '{it.get_name()}' has no builder type and no "
                        f"default is registered for {spec.default_missing_type_to}"
                    )
                it.type_ = dflt
            builder = reg.get_instance_by_name_or_alias(spec.builder_vct, it.type_)
            if builder is None:
                raise ValueError(
                    f"{spec.name} builder '{it.type_}' specified for '{it.get_name()}' not configured"
                )
            spec.attach(builder, it)
        if spec.validate is not None:
            spec.validate(self, items)
        log.info(f"Total {spec.name} read: {len(items)}")
        return items

    def __init__(self,
                 verbose: bool = False,
                 config_dir: Path | None = None,
                 config_data: IAConfig | None = None,
                 working_path: Path | None = None,
                 generation_directory: Path | None = None,
                 all_sorted_builders: list[BuilderBase] | None = None,
                 dry_run: bool = True,
                 overlays: list[Path] | None = None,
                 undeclare: list[str] | None = None,
                 ) -> None:
        # The parameters default to None only so the ubiquitous no-arg
        # singleton-accessor calls (`GlobalTypeContext()`) type-check; the
        # FIRST construction (read_config_and_transform) must supply the full
        # configuration, enforced here.
        if (config_data is None or working_path is None or config_dir is None
                or generation_directory is None or all_sorted_builders is None):
            raise ValueError(
                "GlobalTypeContext must be constructed with its full "
                "configuration on first use (see read_config_and_transform)"
            )
        self.reg = registry.Registry()
        self._dry_run = dry_run
        # Transient declarations (stage 8): overlay files merged over the tree
        # for THIS invocation only -- items by name, config keys by key.
        self.overlays: list[Path] = [Path(p).resolve() for p in (overlays or [])]
        self._overlay_data: list[dict[str, Any]] = [load_overlay(p) for p in self.overlays]
        self.overlay_declared: set[tuple[str, str]] = set()
        # stage 28: `--undeclare <kind>:<name>` -- the overlay `undeclare` form
        # as a flag, so a live configuration needs no overlay file to
        # decommission a tree entry for one invocation (ledger 68, 71)
        self.undeclared: list[tuple[str, str]] = parse_undeclare(undeclare)
        self.apply_runtime: str | None = None      # `run --apply-runtime <rt>` (stage 11.5)
        self.migrate_state: list[str] = []          # `run --migrate-state <ws>` (stage 46): the workspaces whose state MOVES this run
        # stage 12: run scoping safe by construction
        self.implied_scope: str | None = None      # --apply-runtime implied the bake filter to this runtime
        self.allow_unscoped_bakes: bool = False    # `run --allow-unscoped-bakes`
        self.explicit_bake_selection: bool = False # --only / --only-runtime given by the operator
        self.only_runtime_scope: str | None = None  # --only-runtime (explicit or implied): roots of other runtimes emit nothing
        if config_data is not None:
            for data in self._overlay_data:
                if data.get("config"):
                    if config_data.config is None:
                        config_data.config = {}
                    config_data.config.update(data["config"])
        self._verbose = verbose or False
        # scoped-runs: the run's --only image selection; None = everything.
        # Image builders filter their enumeration on it (get_images).
        self.only_images: set[str] | None = None
        # convergent bakes (stage 9): forced images (None = none; FORCE_ALL = all)
        # and the per-run cache of bake decisions (`<series>@<runtime>` -> reason|None)
        self.force_bake: set[str] | None = None
        self.bake_decisions: dict[str, str | None] = {}
        self._finalization = {}
        self._current_lifecycle = None
        self._generated_lifecycles = set()
        self._meta_state = None
        self._run_start_time = datetime.now()
        self._config_dir = config_dir
        self._read_config = config_data
        if config_data is not None:
            # self._typer_context = typer_context
            # self._run_start_time = typer_context.obj.get("run_start_time", datetime.now())
            self._working_path = working_path # typer_context.obj.get(WORKING_PATH, None)
            self._generation_path = generation_directory
            # Builder collections live in the registry; the *_builders properties read
            # them. Nothing is cached on the context here anymore.
            self._executables = config_data.executables_as_dict or {} # typer_context.obj.get(EXECUTABLES, None)
            self._all_sorted_builders = all_sorted_builders or []
            # self._terraform_provider_setups = typer_context.obj.get(
            #     TERRAFORM_PROVIDER_SETUPS, None
            # )
            self._final_execution_path = generation_directory / "final_execution.sh"
            self._sleep_before_finalization = self._read_config.sleep_before_finalization
            lgie:list[str] = DEFAULT_GITIGNORE_ENTRIES + list(self._read_config.gitignore if self._read_config and self._read_config.gitignore else [])
            # No dupes, and the LAST occurrence keeps its place: gitignore reads
            # later rules as overriding earlier ones, so a configuration that
            # restates a default (`!.terraform.lock.hcl` after its own `.*`)
            # means it there (found 2026-09-11: the first-wins rule dropped the
            # restatement and the built-in negation stayed ahead of `.*`).
            self._gitignore_entries = [e for i, e in enumerate(lgie) if e not in lgie[i + 1:]]
            # default_* builder names are resolved live from the registry by the
            # default_* properties, so there is nothing to pre-seed here.


    # This must be called directly, as GTC isn't a dataclass
    def __post_init__(self) -> GlobalTypeContext:
        # Read the normal-flow domain-item kinds in registration order. Each reader
        # registers its items into the registry (from which the collection properties
        # read) and attaches them to their builders; the group kind's validator sets
        # _root_group.
        #
        # base_only kinds (e.g. base_images) are registered but intentionally NOT
        # auto-read yet: that read path is incomplete on the current models
        # (base_image.type_ is an OS family, not an image-builder reference), exactly
        # as it was when read_base_images_from_files existed but was never called.
        for spec in item_kinds():
            if not spec.base_only:
                self._read_item_kind(spec)
        # FIXME: Should I finalize() everyhting here?
        return self


ROOT_VARIABLE = "CSIS_ROOT"     # the runner scripts' name for the configuration root (stage 38)


def materialized_for(root: Path | None, generation_path: Any, executable: Any) -> Any:
    """``executable`` pointed at the private mirror of its directory (stage 49).

    The committed emission carries the ``ENC[age:...]`` ciphertext; the tools
    cannot read that, so the root is copied to ``_private/`` with the plaintext
    substituted and the command runs there. An executable with no working
    directory, a directory that does not exist, or no configuration root to
    mirror under, is returned untouched."""
    wd = getattr(executable, "working_directory", None)
    if not wd or root is None:
        return executable
    src = (Path(generation_path) / wd).resolve()
    if not src.is_dir():
        return executable
    dst = mirror_path(Path(root), src)
    ensure_ignored(Path(root))      # the system made the mirror; the system ignores it
    # on the way IN: bring back what the PREVIOUS command in this root wrote
    # and the emission must carry -- the provider lock file `init` writes. A
    # root's commands run in sequence (init, plan, apply), so the lock reaches
    # the committed tree at the next command's materialize.
    for name in sync_back(src, dst):
        log.info("Synced back from the private mirror: %s", name)
    written, substituted = materialize(src, dst)
    log.info("Materialized %s -> %s (%d file(s), %d carrying ciphertext)",
             src.name, dst, written, substituted)
    moved = executable.model_copy() if hasattr(executable, "model_copy") else copy.copy(executable)
    moved.working_directory = dst
    return moved


def render_executable_line(executable: Any, base: Path | None = None, root: Path | None = None) -> str:
    """One reviewable shell line for a deferred executable. A working
    directory under ``base`` (the lifecycle's directory) is rendered
    RELATIVE to it -- the runner header promises "paths are relative to
    this lifecycle's directory", and an absolute workspace path would tie
    the script (and the golden) to one checkout (ledger 71). An argument
    that is ``root`` (the configuration root: ``--root-dir``) or a path under
    it (``--overlay``) is rendered as ``"$CSIS_ROOT"`` / ``"$CSIS_ROOT/<rel>"``
    -- the header defines the variable relative to the script (stage 38), so
    a committed script names no machine's absolute path, while the
    executable itself keeps the absolute argument for in-process execution."""
    def portable(arg: str) -> str:
        if root is None or not arg.startswith("/"):
            return arg
        try:
            rel = Path(arg).resolve().relative_to(Path(root).resolve())
        except ValueError:
            return arg
        return f'"${ROOT_VARIABLE}"' if str(rel) == "." else f'"${ROOT_VARIABLE}/{rel}"'
    cmd_parts = [str(executable.binary or executable.name)]
    cmd_parts += [portable(str(a)) for a in getattr(executable, "prepended_arguments", []) or []]
    cmd_parts += [portable(str(a)) for a in executable.args or []]
    cmd_parts += [portable(str(a)) for a in getattr(executable, "appended_arguments", []) or []]
    cmd = " ".join(cmd_parts)
    wd = executable.working_directory
    if wd:
        if base is not None:
            try:
                wd = Path(wd).resolve().relative_to(Path(base).resolve())
            except ValueError:
                pass
        # stage 49: the committed emission carries the ENC[age:...] ciphertext,
        # so the command runs in the PRIVATE MIRROR of its root. Entering the
        # emitted root first keeps the line saying which root it is (and keeps
        # the directory the first quoted token), then `materialize` writes the
        # mirror, prints where, and the command runs there.
        if root is not None:
            return (f'( cd "{wd}" && cd "$(cs-image-system materialize . '
                    f'--root-dir "${ROOT_VARIABLE}")" && {cmd} )')
        return f'( cd "{wd}" && {cmd} )'
    return cmd


def script_lines(ctx: Any, header: list[str], lifecycle: LifecycleLike | None,
                 script_dir: Path | None = None) -> list[str]:
    """Phase-ordered shell lines for the deferred executables of ``lifecycle``
    (``None`` = the legacy bucket). Module-level so it works on any object
    exposing ``get_finalization_executables_for_phase``. With ``script_dir``
    (where the script will live) and a context that knows its
    ``working_path``, the header defines ``CSIS_ROOT`` as the configuration
    root RELATIVE to the script and every root-based argument is rendered
    through it (stage 38): the committed script runs from any checkout."""
    root = getattr(ctx, "working_path", None) if script_dir is not None else None
    lines: list[str] = [
        "#!/usr/bin/env bash",
        *header,
        "# NOTE: builders' pre/post finalize hooks are NOT part of this",
        "# script; a --no-dry-run run performs them in-process.",
        "set -euo pipefail",
        'cd "$(dirname "$0")"',
    ]
    if root is not None and script_dir is not None:
        rel = os.path.relpath(Path(root).resolve(), Path(script_dir).resolve())
        lines.append(f'{ROOT_VARIABLE}="$(cd "{rel}" && pwd)"   # the configuration root, relative to this script')
    for phase in ExecutionLifecyclePhase:
        executables = (ctx.get_finalization_executables_for_phase(phase) if lifecycle is None
                       else ctx.get_finalization_executables_for_phase(phase, lifecycle))
        if not executables:
            continue
        lines.append("")
        lines.append(f"# --- phase: {phase.value} ---")
        base = getattr(ctx, "generation_path", None) if lifecycle is not None else None
        for executable in executables:
            lines.append(render_executable_line(executable, Path(base) if base else None,
                                                Path(root) if root is not None else None))
    return lines


def write_script(script: Path, lines: list[str]) -> Path:
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o755)
    return script


def get_files_by_extensions(
    path: Path,
    extensions: list[str] | None = None,
    recursive: bool = True,
) -> list[Path]:
    """Read all files from a directory path and return files with specified extensions.

    Args:
        path: Directory path to search for files
        extensions: List of file extensions to filter by (default: ['.yaml', '.yml'])
        recursive: Whether to search subdirectories recursively (default: True)

    Returns:
        List of Path objects for files matching the specified extensions

    Raises:
        ValueError: If path is not a directory or doesn't exist
    """
    if extensions is None:
        extensions = [".yaml", ".yml"]

    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")

    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {path}")

    # Normalize extensions to lowercase and ensure they start with a dot
    normalized_extensions = []
    for ext in extensions:
        if not ext.startswith("."):
            ext = "." + ext
        normalized_extensions.append(ext)

    files = []

    if recursive:
        # Use recursive glob pattern
        for file_path in path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in normalized_extensions:
                files.append(file_path)
    else:
        # Only search immediate directory
        for file_path in path.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in normalized_extensions:
                files.append(file_path)

    return sorted(files)


# def validate_initial_cycled(cycled: str) -> None:
#     """Perform some basic validation on the cycled YAML to catch common mistakes early."""
#     try:
#         dct = yaml.safe_load(cycled)
#         if not isinstance(dct, dict):
#             raise ValueError("Cycled YAML must be a dictionary at the top level.")
#         if not "runtime_builders" in dct:
#             raise ValueError(
#                 "Cycled YAML must contain at least one 'runtime_builders' key."
#             )
#         q = dct.get("config", {})
#         if not isinstance(q, dict):
#             raise ValueError(
#                 "Cycled YAML 'config' key must be a dictionary if present."
#             )
#         if any(k.lower() in q for k in INVALID_CONFIG_KEYS):
#             raise ValueError(
#                 "Cycled YAML 'config' cannot contain any key in the invalid keys list,"
#                 f" {INVALID_CONFIG_KEYS}, as it may cause issues with templating."
#             )
#     except yaml.YAMLError as e:
#         log.error(f"Validation failed for cycled YAML: {e}")
#         raise ValueError(f"Validation failed for cycled YAML: {e}")

def apply_overlays(ctx: Any, spec: ItemKind, read_dict: dict[str, Any]) -> None:
    """Merge every overlay's entries for this kind over the tree's: a named
    entry that exists is updated key by key (``state: destroyed`` on a
    declared storage), a new one is appended (a cycle's instance). The tree
    on disk is never touched -- that is the point (stage 8). A context
    without overlays (unit-test stand-ins included) is a no-op."""
    overlays = getattr(ctx, "overlays", None) or []
    data_list = getattr(ctx, "_overlay_data", None) or []
    key = spec.model_cls.klazz_yaml_key() if hasattr(spec.model_cls, "klazz_yaml_key") else spec.name
    for path, data in zip(overlays, data_list):
        for item in data.get(key) or []:
            name = item.get("name")
            if item.get("undeclare"):
                # ledger 68: an overlay can also UNDECLARE a tree entry for one
                # invocation -- the instance decommissions / the storage is
                # destroyed exactly as if its entry had left the YAML
                if read_dict.pop(name, None) is not None:
                    log.info(f"Overlay {path.name}: {spec.name} '{name}' undeclared for this invocation")
                else:
                    log.warning(f"Overlay {path.name}: {spec.name} '{name}' is not declared; nothing to undeclare")
                continue
            if name in read_dict:
                read_dict[name] = {**read_dict[name], **item}
                log.info(f"Overlay {path.name}: {spec.name} '{name}' updated ({', '.join(k for k in item if k != 'name')})")
            else:
                read_dict[name] = dict(item)
                # transient: declared by an overlay, not by the tree (stage 10.15)
                getattr(ctx, "overlay_declared", set()).add((key, name))
                log.info(f"Overlay {path.name}: {spec.name} '{name}' declared (transient)")
    # stage 28: the same undeclare, from `--undeclare <kind>:<name>` (no file)
    for kind_key, name in getattr(ctx, "undeclared", None) or []:
        if kind_key != key:
            continue
        if read_dict.pop(name, None) is not None:
            log.info(f"--undeclare: {spec.name} '{name}' undeclared for this invocation")
        else:
            log.warning(f"--undeclare: {spec.name} '{name}' is not declared; nothing to undeclare")


def parse_undeclare(specs: list[str] | None) -> list[tuple[str, str]]:
    """``--undeclare <kind>:<name>`` (stage 28) -> ``[(yaml key, name)]``.
    The kind is an overlay collection key (``instances``, ``storages``, ...);
    the singular is accepted. Refused up front, like a malformed overlay."""
    allowed = {
        (k.model_cls.klazz_yaml_key() if hasattr(k.model_cls, "klazz_yaml_key") else k.name)
        for k in item_kinds()}
    out: list[tuple[str, str]] = []
    for spec in specs or []:
        kind, sep, name = spec.partition(":")
        if not sep or not kind or not name:
            raise ValueError(f"--undeclare {spec!r}: expected <kind>:<name> (e.g. instance:gce-test)")
        key = kind if kind in allowed else kind + "s"
        if key not in allowed:
            raise ValueError(f"--undeclare {spec!r}: unknown kind {kind!r}; allowed: {sorted(allowed)}")
        out.append((key, name))
    return out


def load_overlay(path: Path) -> dict[str, Any]:
    """Read one overlay file (stage 8): a mapping whose keys are ``config``
    and/or the domain-item collections (``instances``, ``storages``, ...),
    each a list of named entries. Anything else is refused up front."""
    allowed = {"config"} | {
        (k.model_cls.klazz_yaml_key() if hasattr(k.model_cls, "klazz_yaml_key") else k.name)
        for k in item_kinds()}
    if not path.is_file():
        raise ValueError(f"Overlay {path} does not exist")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Overlay {path} must be a mapping at the top level")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"Overlay {path}: unknown top-level key(s) {unknown}; allowed: {sorted(allowed)}")
    for key, value in data.items():
        if key == "config":
            if not isinstance(value, dict):
                raise ValueError(f"Overlay {path}: 'config' must be a mapping")
            continue
        if not isinstance(value, list) or any(not isinstance(i, dict) or not i.get("name") for i in value):
            raise ValueError(f"Overlay {path}: '{key}' must be a list of named entries")
    return data


def read_config_and_transform(
    typer_cntx: typer.Context,
    root_dir: Path,
            # config_file: str,
    verbose: bool = False,  # We eventually set verbose in the typer_cntx.obj
    *,
    dry_run: bool = True,
    overlays: list[Path] | None = None,
    undeclare: list[str] | None = None,
) -> GlobalTypeContext:
    """Read the global configuration from a file.

    Parameters
    ----------
    root_dir : Path
        The root directory containing the configuration files.

    Returns
    -------
        The global configuration instance.
    """
    run_start_time = datetime.now()
    typer_cntx.obj = {"run_start_time": run_start_time}   # the CLI sets "base_only" itself
    env = os.environ.copy()
    reg = registry.Registry()
    if not root_dir:
        raise ValueError("Root directory must be provided")
    _config_dir = root_dir / "cfg"
    orig = read_and_process(_config_dir)
    if not orig:
        raise ValueError(f"Failed to read configuration from {_config_dir}")
    # Here, we know that none of the "name" elements collide
    original_str = yaml.dump(orig)
    from .models.ia_config import DEFAULT_DATEFORMAT
    dtfmt = orig.get("dateformat", DEFAULT_DATEFORMAT)     # stage 63: the model's one default
    run_start_date = run_start_time.date()
    timestamp = run_start_time.strftime(dtfmt)
    # TODO: figure out some more runtime values to inject here, like git commit hash, branch, etc
    addl: dict[str, Any] = {
        "execution": {
            "timestamp": timestamp,
            "dateformat": dtfmt,
            "date": run_start_date.isoformat(),
        },
        "ENV": env,
    }


    processed_str = cycle_main_yaml(original_str, addl=addl)
    orig = yaml.safe_load(processed_str)
    log.debug("cycle_main_yaml result:\n%s", pformat(orig, indent=2,width=163))

    template_resolver = TemplateResolver(addl=addl)
    # cycled = cycle_main_yaml(processed_str, addl=addl)
    cycled = processed_str  # skip the cycling for now, as it is causing some issues and we want to get the basic flow working.  We can re-enable it once we have a better handle on the process and have added some more safeguards around it.
    if verbose:
        with open("./YAML_DUMP.yaml", "w+") as f:
            f.write(cycled)
    # validate_initial_cycled(cycled)  # Raises errors if things go awry

    # generic_yaml = template_utils.process_keys( yaml.unsafe_load(config_str))
    # _ddd: dict = {}
    # _ddd = template_utils.extend_with_envdata({},include_ENV=True)
    # config_str = template_utils.render_j2_template_string(config_str, **_ddd)
    generic_yaml = yaml.safe_load(cycled)
    # stage 49: any value in the base document may be an ENC[age:...] marker.
    # HERE, after the dump/render/re-parse above, not in read_and_process: a
    # Decrypted dumps as its plain text, so decrypting before that round-trip
    # would lose every ciphertext the emission has to write back, feed the
    # plaintext to Jinja as template SOURCE, and put it in YAML_DUMP.yaml.
    # This one call covers IAConfig and the plugin builder models, whose dicts
    # are popped out of generic_yaml below and structured from these objects.
    generic_yaml = decrypt_tree(generic_yaml, source=str(_config_dir),
                                collect=decrypted_plaintexts())
    if isinstance(generic_yaml, list):
        if len(generic_yaml) != 1:
            raise ValueError(f"Expected single config, got {len(generic_yaml)}")
        generic_yaml = generic_yaml[0]
    if not isinstance(generic_yaml, dict):
        raise ValueError(
            f"Expected config to be a dictionary at the top level, got {type(generic_yaml)}"
        )

    cycled_generic_yaml = copy.deepcopy(generic_yaml)
    original_yaml_strings: dict[str, str] = {}
    original_yaml_dictionary_lists: dict[str, list[dict[str, Any]]] = {}
    original_yaml_strings_by_plugin_type: dict[str, dict[str, str]] = {}
    for plugin_name, plugin_key in PLUGIN_TYPES:
        if plugin_key in generic_yaml:
            items = generic_yaml.pop(plugin_key)
            if not isinstance(items, list):
                raise ValueError(
                    f"Expected a list for key '{plugin_key}', got {type(items)}"
                )
            original_yaml_strings[plugin_key] = yaml.dump(items)
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"Expected each item in '{plugin_key}' to be a dictionary, got {type(item)}"
                    )
                name = item.get("name", None)
                if not name:
                    raise ValueError(
                        f"Each item in '{plugin_key}' must have a 'name' field. "
                        f"Item at index {idx} is missing a name."
                    )
                original_yaml_strings_by_plugin_type.setdefault(plugin_key, {})[
                    name
                ] = yaml.dump(item)
            original_yaml_dictionary_lists[plugin_key] = items

    # generic_yaml no longer contains the plugin-typed builder models
    try:
        # cattrs.resolve_types(IAConfig)
        config_data = Orchestrator().get_converter().structure(generic_yaml, IAConfig)
    except Exception as e:
        log.error(f"Failed to parse configuration: {e}")
        raise
    assert (
        config_data.working_directory is not None
    ), "working_directory is required in config"
    if isinstance(config_data, list):
        if len(config_data) != 1:
            raise ValueError(f"Expected single config, got {len(config_data)}")
        config_data = config_data[0]

    cvt = Orchestrator().get_converter()


    for plugin_name, plugin_key in PLUGIN_TYPES:
        typemap_type: type = PLUGIN_TYPEMAP.get(plugin_name, None)  # type: ignore
        assert (
            typemap_type
        ), f"No class found for plugin key '{plugin_key}' in PLUGIN_TYPEMAP. Please add an entry for this plugin type."
        if plugin_key in original_yaml_dictionary_lists:
            for item in original_yaml_dictionary_lists[plugin_key]:
                name = item.get("name", None)
                _type = item.get("type", None)
                if not name or not _type:
                    raise ValueError(
                        f"Each item in '{plugin_key}' must have a 'name' and 'type' field. "
                        f"Item {item} is missing a name or type."
                    )
                try:
                    named_obj = cvt.structure(item, typemap_type)
                    if named_obj and isinstance(named_obj, BuilderModelProtocol):
                        bmp: BuilderModelProtocol = named_obj
                        bmpname = bmp.get_name()
                        vct = registry.sanitize_classifier(bmp.get_classification())
                        if bmpname and vct and bmp.get_is_default():
                            if reg.get_default_for(vct) != None:
                                log.warning(
                                    f"Default {vct.value} builder already registered: {reg.get_default_for(vct)}. Overwriting with {bmpname} from config."
                                )
                            reg.set_default_for(vct, bmpname)
                    template_resolver.flatten_dataclass(named_obj)
                except Exception as e:
                    log.error(
                        f"Failed to structure item {item} for plugin key '{plugin_key}': {e}"
                    )
                    raise
                # The structure call registers the object into the registry

    template_resolver.resolve_all()

    # template_resolver holds everything in it's map at the moment
    config_data.runtime_builders = reg.get_all_instances_by_classification(VCT.RUNTIME_BUILDER_MODEL)  # type: ignore
    config_data.state_backends = reg.get_all_instances_by_classification(VCT.STATE_BACKEND_MODEL)  # type: ignore
    config_data.os_builders = reg.get_all_instances_by_classification(VCT.OS_BUILDER_MODEL)  # type: ignore
    config_data.group_builders = reg.get_all_instances_by_classification(VCT.GROUP_BUILDER_MODEL)  # type: ignore
    config_data.user_builders = reg.get_all_instances_by_classification(VCT.USER_BUILDER_MODEL)  # type: ignore
    config_data.mod_builders = reg.get_all_instances_by_classification(VCT.MOD_BUILDER_MODEL)  # type: ignore
    config_data.storage_builders = reg.get_all_instances_by_classification(VCT.STORAGE_BUILDER_MODEL)  # type: ignore
    config_data.image_builders = reg.get_all_instances_by_classification(VCT.IMAGE_BUILDER_MODEL)  # type: ignore
    config_data.instance_builders = reg.get_all_instances_by_classification(VCT.INSTANCE_BUILDER_MODEL)  # type: ignore
    configured_runtime_builders: dict[str, RuntimeBuilderBase] = {}
    if not config_data.runtime_builders:
        raise ValueError("No runtime providers configured.")

    default_runtime_builder = reg.get_default_for(VCT.RUNTIME_BUILDER_MODEL)

    # TODO:
    #  1. cycle_yaml using the local value of "runtime" including a timestamp and
    #     date to allow for dynamic values in the config file based on the current run.
    #     This produces a finalized yaml
    #  2. Load the finalized yaml into a dict
    #  3. Use RuntimeModel.from_dict to produce final runtime models for all types
    #  4. Fill in any defaults that are possible to fill
    #  5. Use the registry to lookup the actual type and instantiate the list
    #     of runtimes, returning that list.  Keep the original yaml in the runtime_builder's
    #     config for reference and debugging.
    # NOTE that this process is RELOADING THE YAML FOR EACH BUILDER TYPE INDIVIDUALLY
    if not config_data.config:
        log.warning("No configuration data found in config file.")
        config_data.config = {}
    addl_config = copy.deepcopy(addl)
    addl_config.update(config_data.config)


    if not config_data.runtime_builders:
        log.error("No runtime builders found in config file.")
        raise ValueError("No runtime builders found in config file.")

    log.debug(f"Original runtime builders config: {config_data.runtime_builders}")

    # config_data.runtime_builders = reprocess_a(config_data.runtime_builders, addl_config)  # type: ignore
    # config_data.state_backends = reprocess_a(config_data.state_backends, addl_config) if config_data.state_backends else []  # type: ignore

    # # for q in config_data.os_builders or []:
    # #     log.debug(f"OS builder {q.name} runtime provider before reprocessing")
    # #     scan_for_trouble(q)
    # #     # d = Orchestrator().get_converter().unstructure(q)
    # config_data.os_builders = reprocess_a(config_data.os_builders, addl_config) if config_data.os_builders else []  # type: ignore
    # config_data.group_builders = reprocess_a(config_data.group_builders, addl_config) if config_data.group_builders else []  # type: ignore
    # config_data.user_builders = reprocess_a(config_data.user_builders, addl_config) if config_data.user_builders else []  # type: ignore
    # config_data.storage_builders = reprocess_a(config_data.storage_builders, addl_config) if config_data.storage_builders else []  # type: ignore
    # config_data.image_builders = reprocess_a(config_data.image_builders, addl_config) if config_data.image_builders else []  # type: ignore
    # config_data.instance_builders = reprocess_a(config_data.instance_builders, addl_config) if config_data.instance_builders else []  # type: ignore

    configured_runtime_builders: dict[str, RuntimeBuilderBase] = process_and_register_builders(
        config_data, VCT.RUNTIME_BUILDER, "runtime_builders", addl_config
    )  # type: ignore
    configured_state_builders = {}
    if config_data.state_backends:
        configured_state_builders = process_and_register_builders(
            config_data, VCT.STATE_BACKEND, "state_backends", addl_config
        )
    configured_os_builders = {}
    if config_data.os_builders:
        configured_os_builders = process_and_register_builders(
            config_data, VCT.OS_BUILDER, "os_builders", addl_config
        )
    configured_group_builders = {}
    if config_data.group_builders:
        configured_group_builders = process_and_register_builders(
            config_data, VCT.GROUP_BUILDER, "group_builders", addl_config
        )
    configured_user_builders = {}
    if config_data.user_builders:
        configured_user_builders = process_and_register_builders(
            config_data, VCT.USER_BUILDER, "user_builders", addl_config
        )
    configured_image_builders: dict[str, ImageBuilderBase] = {}
    if config_data.image_builders:
        configured_image_builders = process_and_register_builders(
            config_data, VCT.IMAGE_BUILDER, "image_builders", addl_config
        )  # type: ignore
    configured_instance_builders: dict[str, InstanceBuilderBase] = {}
    if config_data.instance_builders:
        configured_instance_builders = process_and_register_builders(
            config_data, VCT.INSTANCE_BUILDER, "instance_builders", addl_config
        )  # type: ignore
        # for instb_name, instancebuilder in configured_instance_builders.items():

    configured_mod_builders: dict[str, ModBuilderBase] = {}
    if config_data.mod_builders:
        configured_mod_builders = process_and_register_builders(
            config_data, VCT.MOD_BUILDER, "mod_builders", addl_config
        )  # type: ignore
    configured_storage_builders = {}
    if config_data.storage_builders:
        configured_storage_builders = process_and_register_builders(
            config_data, VCT.STORAGE_BUILDER, "storage_builders", addl_config
        )


    builders: list[BuilderBase] = []

    for d in [
        configured_runtime_builders,
        configured_state_builders,
        configured_group_builders,
        configured_user_builders,
        configured_os_builders,
        configured_mod_builders,
        configured_storage_builders,
        configured_image_builders,
        configured_instance_builders,

    ]:
        for k in sorted(d.keys()):
            builders.append(d[k])

    # If a root_dir is supplied
    if root_dir:
        # Use the supplied root_dir
        working_dir = root_dir
    else:
        # Use the root_dir from the config file, or default to "."
        working_dir = (
            config_data.working_directory if config_data.working_directory else "."
        )
    wpath = Path(working_dir).resolve()
    if not wpath.exists():
        raise FileNotFoundError(f"Working directory {wpath} does not exist.")
    os.chdir(wpath)
    gen_path = (
        wpath / config_data.generation_directory
        if config_data.generation_directory
        else wpath / "generated"
    )
    ctx = GlobalTypeContext(
        verbose,
        root_dir,
        config_data,
        wpath,
        gen_path,
        builders, # type: ignore
        dry_run=dry_run,
        overlays=overlays,
        undeclare=undeclare,
        ).__post_init__()
    # Final action
    return ctx


def process_and_register_builders(
    config_data: IAConfig,
    classification: VCT,
    property: str,
    addl_config: dict[str, Any],
) -> dict[str, BuilderBase]:
    """
    Reprocess a list of builders of a given classification to resolve references and defaults.
    This function MIGHT ALSO mutate the builder model objects.
    """
    reg = registry.Registry()
    ret: dict[str, BuilderBase] = {}
    builder_models: dict[str,BuilderModel] = getattr(config_data, property, {})

    default: str | None = None
    default_classifier: VCT | None = None
    names: set[str] = set()
    for name, model in builder_models.items():
        if not isinstance(model, BuilderModel):
            raise ValueError(
                f"Expected builder model for {name} in {property} to be an instance of BuilderModel, got {type(model)}"
            )

        if model.name in OOPS_DEFAULTS:
            raise ValueError(
                f"Builder with default name found:{model.name}"
            )
        else:
            model.name = name.strip()
        if hasattr(model,"aliases"):
            aliases = getattr(model, "aliases", [])
            if model.name in aliases:
                aliases.remove(model.name)
            reg.register_aliases(classification, model.name,aliases) # Keeps aliases from colliding
        if model.name in names:
            raise ValueError(f"Duplicate builder name found: {model.name}")

        names.add(model.name)
        if model.is_default:
            if default is not None:
                raise ValueError(
                    f"Multiple default builders found: {default} and {model.name}"
                )
            default = model.name
            default_classifier = model.csis_classifier()
        if hasattr(model,"runtime"):
            rt = reg.get_registered_name_by_name_or_alias(VCT.RUNTIME_BUILDER, model.runtime) # type: ignore
            assert rt, f"Runtime provider '{rt}' not found for builder '{model.name}'"
            model.runtime = rt  # type: ignore
        try:
            model.finalize()  # This didn't happen in reprocess_a
        except Exception as e:
            log.error(
                f"Failed to finalize builder model {model.name} of type {classification}: {e}"
            )
            raise
        builder_models[name] = model

        model_type = type(model)
        model_name_type = model_type.csis_name()
        bc: type[BuilderBase] = reg.get_builder_for_model(model_name_type, classification) # type: ignore
        assert (
            bc is not None
        ), f"No builder class registered for model class {model.__class__}"
        prov = bc(model=model)  # type: ignore
        if not is_dataclass(prov):
            # We don't call __post_init__ for dataclasses
            # the system does that for us when we instantiate them,
            # but for non-dataclass builders we need to call it manually
            if hasattr(prov, "__post_init__"):
                if callable(getattr(prov, "__post_init__")):
                    prov.__post_init__()  # type: ignore
        prov.finalize()
        if issubclass(bc, PluginArtifactProtocol) or issubclass(bc,NameTypedProtocol):
            reg.register_built_instance( prov)  # type: ignore
        if model.name in ret:
            raise ValueError(
                f"Duplicate builder name '{model.name}' found for classification {classification} after reprocessing. Builder names must be unique."
            )
        ret[model.name] = prov # type: ignore
    if default is None:
        raise ValueError(f"No default builder found in {classification} list.")

    reg.set_default_for(classification, default)
    # Also register the default under the default builder's own model-level
    # classification (e.g. RUNTIME_BUILDER *and* RUNTIME_BUILDER_MODEL), taken from
    # the default model itself rather than whichever model happened to iterate last.
    if default_classifier is not None:
        reg.set_default_for(default_classifier, default)

    return ret



def read_and_process(dir: Path) -> dict[str, Any] | None:
    """Read and process YAML files in the given directory."""
    if not dir.exists() or not dir.is_dir():
        return None
    f:list[Path] = get_files_by_extensions(dir, recursive=False)
    ret: dict[str, Any] = {}
    for file in f:
        try:
            with open(file, "r") as stream:
                # safe_load: a PUBLIC configuration tree constructs no Python object
                # (stage 63 item 13; unsafe_load stood here alone, every other
                # reader of the tree is safe_load, and no tree carries a tag)
                data = yaml.safe_load(stream)
                if isinstance(data, dict):
                    # stage 49: needs NO identity -- a structural check, so it
                    # still runs where nothing could be decrypted
                    refuse_markers_at(data, str(file))
                    ret = _extend_lists(ret, data)
        except Exception as e:
            log.error(f"Error reading or processing file {file}: {e}")
            raise
    if not ret:
        log.warning(f"No valid YAML files found in directory {dir}")
        return None
    # Check for name collisions on lists of dicts
    for key, value in ret.items():
        if isinstance(value, list):
            names_seen: set[str] = set()
            for item in value:
                if isinstance(item, dict):
                    if "name" in item:
                        name = item["name"]
                        if "{{" in name or "}}" in name:
                            errstr = (f"Name '{name}' in list for key '{key}' contains template markers. ")
                            log.error(errstr)
                            raise ValueError(errstr)
                        if name in names_seen:
                            raise ValueError(
                                f"Duplicate name '{name}' found in list for key '{key}'"
                            )
                        names_seen.add(name)
                    if "type" in item:
                        type_value = item["type"]
                        if "{{" in type_value or "}}" in type_value:
                            errstr = (f"Type '{type_value}' in list for key '{key}' contains template markers. ")
                            log.error(errstr)
                            raise ValueError(errstr)

    log.debug("read_and_process result:\n%s", pformat(ret))
    return ret

def _extend_lists(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Extend lists in the old dictionary with lists from the new dictionary by name."""
    for key, value in new.items():
        if isinstance(value, list):
            if key in old and isinstance(old[key], list):
                old[key].extend(value)
            else:
                old[key] = value
        else:
            old[key] = value
    return old


def _validate_groups(ctx: GlobalTypeContext, groups: list[Group]) -> None:
    """Post-read validation for the ``groups`` kind: exactly one root group
    (marked ``is_root: true``), and every group member must be a defined user."""
    rgrp = [g for g in groups if g.is_root]
    if len(rgrp) != 1:
        raise ValueError(f"Expected exactly one root group (is_root: true), found {len(rgrp)}")
    ctx._root_group = rgrp[0]
    user_names = {u.get_name() for u in ctx.users}
    for g in groups:
        for u in g.members:
            if u not in user_names:
                raise ValueError(
                    f"Group {g.get_name()} has member {u} which is not in the list of "
                    "defined users"
                )


# --- Built-in domain-item kinds (read in this order during __post_init__).
# Users are read before groups so group-member validation can see them.
register_item_kind(ItemKind(
    "users", GROUPS, User, VCT.USER_BUILDER,
    attach=lambda b, it: b.add_user_to_builder(it),
))
register_item_kind(ItemKind(
    "groups", GROUPS, Group, VCT.GROUP_BUILDER,
    attach=lambda b, it: b.add_group_to_builder(it),
    validate=_validate_groups,
))
register_item_kind(ItemKind(
    "storages", STORAGES, Storage, VCT.STORAGE_BUILDER,
    attach=lambda b, it: b.add_storage(it),
))
def _attach_image(builder: Any, image: Any) -> None:
    """An image attaches to its ``type`` builder (the primary) and, EXPLORE
    GCP, to every other image builder its ``runtimes`` name -- one bake per
    runtime of the same logical image."""
    builder.add_image(image)
    reg = registry.Registry()
    primary_runtime = builder.model.get_runtime_provider()
    for sub in getattr(image, "runtimes", None) or []:
        name = getattr(sub, "image_builder", None)
        if not name or name in OOPS_DEFAULTS:
            continue
        other = reg.get_instance_by_name_or_alias(VCT.IMAGE_BUILDER, name)
        if other is None or other is builder:
            continue
        if other.model.get_runtime_provider() == primary_runtime:
            continue  # same runtime: the primary builder's bake is the bake
        other.add_image(image)


register_item_kind(ItemKind(
    "images", IMAGES, Image, VCT.IMAGE_BUILDER,
    attach=_attach_image,
    default_missing_type_to=VCT.IMAGE_BUILDER_MODEL,
))
register_item_kind(ItemKind(
    "instances", INSTANCES, Instance, VCT.INSTANCE_BUILDER,
    attach=lambda b, it: b.add_instance(it),
))
# Base images are read in base-only mode (the normal-flow kinds are skipped then).
register_item_kind(ItemKind(
    "base_images", BASE_IMAGES, BaseImage, VCT.IMAGE_BUILDER,
    attach=lambda b, it: b.add_image(it),
    default_missing_type_to=VCT.IMAGE_BUILDER_MODEL,
    base_only=True,
))