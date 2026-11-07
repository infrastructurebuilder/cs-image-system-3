# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The run context as a plugin sees it: :class:`RunContextProtocol`
holds exactly the members the plugins, the terraform library and the
terraform roots read from the context, counted from their sources, and
nothing the kit's context has beyond them; :class:`MetaStateProtocol`
the members they read
of the run's meta-state; and the service protocols what they call of the
engine's knowledge, reached as ``ctx.services.<name>`` instead of by
module import: lineage, launch, secrets, files, commands, images, identity,
storage, workspaces, scope, cli, lifecycles and the meta-state.

The kit's ``RunContext`` lists :class:`RunContextProtocol` as a base, so
pyright compares every member, and ``testing.assert_conforms`` checks the
class and each service adapter at the bar. A plugin's test stubs one
service, not the world.

Items of the domain (an instance, a storage, a user, a group, an image)
are ``Any`` here as they are throughout the contract: their protocols are
a later stage. The global ``config:`` map and the meta-state's records are
YAML as read, ``Mapping[str, Any]`` because that is what they are.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from .constants import VCT
from .core import BuilderProtocol
from .enrollment import AnsibleTasks, ScriptLines
from .executables import ExecutableProtocol
from .group import GroupBuilderProtocol
from .image import ImageQuery, ProviderSpecificImageProtocol
from .lifecycle import ExecutionLifecyclePhase
from .lifecycles import LifecycleLike
from .modification import ModBuilderProtocol
from .operating_system import OsBuilderProtocol
from .runtime import RuntimeBuilderProtocol
from .state import StateBuilderProtocol
from .storage import StorageBuilderProtocol
from .user import UserBuilderProtocol

__all__ = ["AnsibleTasks", "ScriptLines"]   # the enrollment renderers' shapes, re-exported from .enrollment


class MetaStateProtocol(Protocol):
    """What the plugins read and write of the run's meta-state (the
    ``meta-state/`` ledgers beside the tree): the storage states, the
    instance generations and pins, the builds, the launch records and the
    state locations. Twelve members, counted from the sources."""

    # --- storages
    def storage_state(self, name: str) -> str | None: ...

    def storage_states(self) -> dict[str, dict[str, Any]]: ...

    # --- instances: generations, pins, launches
    def current_generation(self, name: str) -> dict[str, Any] | None: ...

    def instance_pin(self, instance: str) -> str | None: ...

    def instance_pins(self) -> dict[str, str]: ...

    def bind_instance(self, instance: str, build_id: str, run_id: str) -> None: ...

    def move_pin(self, kind: str, name: str, to_build: str, run_id: str,
                 op: str = "upgrade", pending: bool = True) -> str | None: ...

    def launch_params(self) -> dict[str, dict[str, Any]]: ...

    # --- builds
    def build(self, build_id: str) -> dict[str, Any] | None: ...

    # --- state locations
    def state_locations(self) -> dict[str, dict[str, Any]]: ...

    def record_state_locations(self, locations: dict[str, dict[str, Any]], run_id: str) -> None: ...

    @staticmethod
    def location_key(record: dict[str, Any]) -> str: ...


# ------------------------------------------------------------------ the services

class LineageServiceProtocol(Protocol):
    """The lineage of builds and instances: ownership tags, pins, records.
    Every member is bound to the run (the configuration id, the meta-state
    records); the plugins called them with the context as the first
    argument before this stage."""

    def owner_of(self, tags: dict[str, Any] | None) -> str: ...

    def belongs_to_another_configuration(self, tags: dict[str, Any]) -> bool: ...

    def ours_or_unlabelled(self, tags: dict[str, Any] | None) -> bool: ...

    def config_tags(self) -> dict[str, str]: ...

    def configuration_tag(self) -> str: ...

    def lineage_tags(self, image: Any, runtime: str | None = None) -> dict[str, str]: ...

    def series_of(self, image: Any) -> str: ...

    def mod_records(self, image: Any) -> list[dict[str, Any]]: ...

    def bake_disk_size(self, image: Any, runtime: str | None) -> int | str | None: ...

    def pinned_parent_build(self, image: Any, runtime: str | None = None) -> str | None: ...

    def record_build(self, image: Any, runtime: str, build_id: str, name: str | None,
                     resolve_parent: Callable[[str], str | None]) -> dict[str, Any]: ...

    def pinned_instance_build(self, instance: Any) -> str | None: ...

    def instance_follow_target(self, instance: Any) -> tuple[str, str] | None: ...

    def pending_instance_replacements(self, instances: list[Any]) -> set[str]: ...


class LaunchServiceProtocol(Protocol):
    """What an instance is launched with: its launch parameters, the launch
    script template, the mounts to detach, the hostname rules, the group
    builder that owns a group, and the enrollment kinds a launch script
    knows how to render."""

    def compute_launch_params(self, instance: Any) -> dict[str, Any]: ...

    def user_data_template(self, params: dict[str, Any]) -> str: ...

    def detachments(self, instance: Any) -> list[dict[str, Any]]: ...

    def hostname_problems(self, name: str) -> list[str]: ...

    def group_builder_of(self, group: str) -> GroupBuilderProtocol | None: ...

    def register_enrollment_kind(self, kind: str, *, script_lines: ScriptLines, ansible_tasks: AnsibleTasks) -> None: ...

    def failure_policy(self, instance: Any) -> tuple[str, int | None]:
        """``(on_failure, teardown_after seconds)`` for an ephemeral instance:
        its declaration, else its runtime's defaults, else keep / None."""
        ...

    def teardown_due(self, instance: Any, now: datetime | None = None) -> bool:
        """A standing ephemeral (last verification failed, launch record still
        present) whose ``teardown_after`` has elapsed."""
        ...


class SecretsServiceProtocol(Protocol):
    """Encrypted values: the ``ENC[age:...]`` marker test, its decryption,
    and the HCL emission of a value that may be one."""

    def is_marker(self, value: Any) -> bool: ...

    def decrypt_marker(self, marker: str, identities: Iterable[Any] | None = None) -> str: ...

    def emit(self, value: Any) -> Any: ...


class FilesServiceProtocol(Protocol):
    """Files the run materialises: the mirror of a path under the
    configuration root."""

    def mirror_path(self, config_root: Path, path: Path) -> Path: ...


class CommandsServiceProtocol(Protocol):
    """The shell fragments a bake runs its commands through."""

    def execute_command_line(self, indent: str = "    ") -> str: ...

    def settle_commands(self, runtime_commands: list[str] | None = None) -> list[str]: ...


class ImagesServiceProtocol(Protocol):
    """Images: the chain from an image to its root family, the user a bake
    logs in as, the OS type of a family, a runtime's packaged image
    sources, a container image reference, and the post-bake test commands
    a bake's provisioners carry."""

    def image_chain(self, image: Any) -> tuple[list[str], str | None]: ...

    def resolve_bake_user(self, image: Any, runtime: str) -> str: ...

    def os_type_for_family(self, family: str | None) -> type: ...

    def packaged_entries_of(self, package: str) -> list[Mapping[str, Any]]: ...

    def container_reference(self, query: ImageQuery) -> str | None: ...

    def base_image_verify_commands(self, base: Any, runtime_name: str) -> list[str]: ...

    def instance_image_verify_commands(self, image: Any, runtime_name: str | None = None) -> list[str]: ...

    def finalize_provisioner(self, source_label: str, runtime_name: str, os_family: str | None) -> list[str]: ...

    def verify_provisioner(self, source_label: str, cmds: list[str], what: str) -> list[str]: ...

    def admin_user(self, os_builder_name: str) -> str: ...

    def admin_public_keys(self, base: Any = None, os_builder_name: str | None = None) -> list[str]: ...


class IdentityServiceProtocol(Protocol):
    """Identity: the attributes the tree declares for its users, the
    launched instances a login proof can reach, and the group builders by
    the identity type they provide."""

    def declared_attributes(self) -> dict[str, dict[str, dict[str, Any]]]: ...

    def standing_instances(self, *, runtime: str | None = None, names: list[str] | None = None) -> list[Any]: ...

    def group_builders_by_identity_type(self) -> Mapping[str, Sequence[GroupBuilderProtocol]]: ...


class StorageServiceProtocol(Protocol):
    """Storage: the transitions of storages that left the tree, and the
    storage builders by the storage type they provide."""

    def undeclared_transitions(self) -> list[Any]: ...

    def storage_builders_by_type(self) -> Mapping[str, Sequence[StorageBuilderProtocol]]: ...


class WorkspacesServiceProtocol(Protocol):
    """The terraform workspaces of the tree: each root's state binding (its
    own ``state_configuration`` and its runtime's), and what the records say
    stands in a workspace's state."""

    def terraform_workspaces(self) -> dict[str, tuple[str | None, str | None]]: ...

    def deployed_in_workspace(self, workspace: str) -> list[str]: ...

    def backup_state(self, workspace: str, tofu: str, run_id: str, cwd: Path) -> int:
        """The same-day state backup a runner takes before its first ``state
        rm``: the state pulled from ``cwd`` (an initialised root) and kept
        under the configuration root. 0 when kept; 1 refuses the removal."""
        ...


class ScopeServiceProtocol(Protocol):
    """What of the tree THIS run acts on: the ``apply_<lifecycle>`` flags, a
    terraform root's place under ``--only-runtime``, and the module source
    a generated root calls its module by."""

    def apply_enabled(self, lifecycle_key: str, root: str | None = None, aliases: Iterable[str] = ()) -> bool: ...

    def root_in_runtime_scope(self, runtime: str | None) -> bool: ...

    def module_source(self, module_dirname: str, workspace_dir: Path | None = None) -> str: ...


class CliServiceProtocol(Protocol):
    """The system's own command line as a deferred step of a runner script:
    bare (the apply gate), or carrying the run's configuration root and
    overlays (verify instance, unmount, state migration)."""

    def system_cli_executable(self, args: list[str], working_directory: Path | None = None) -> ExecutableProtocol: ...

    def system_cli_executable_with_config(self, args: list[str],
                                          working_directory: Path | None = None) -> ExecutableProtocol: ...


class LifecyclesServiceProtocol(Protocol):
    """The lifecycles of this installation: the built-ins and every
    registered one in execution order, and the builder classifications a
    lifecycle owns."""

    def all_lifecycles(self) -> list[LifecycleLike]: ...

    def builder_vcts_of(self, lifecycle: LifecycleLike) -> set[VCT]: ...


class ServicesProtocol(Protocol):
    """The services behind the context, one attribute per service."""

    @property
    def lineage(self) -> LineageServiceProtocol: ...

    @property
    def launch(self) -> LaunchServiceProtocol: ...

    @property
    def secrets(self) -> SecretsServiceProtocol: ...

    @property
    def files(self) -> FilesServiceProtocol: ...

    @property
    def commands(self) -> CommandsServiceProtocol: ...

    @property
    def images(self) -> ImagesServiceProtocol: ...

    @property
    def identity(self) -> IdentityServiceProtocol: ...

    @property
    def storage(self) -> StorageServiceProtocol: ...

    @property
    def workspaces(self) -> WorkspacesServiceProtocol: ...

    @property
    def scope(self) -> ScopeServiceProtocol: ...

    @property
    def cli(self) -> CliServiceProtocol: ...

    @property
    def lifecycles(self) -> LifecyclesServiceProtocol: ...

    @property
    def meta_state(self) -> MetaStateProtocol: ...


# ------------------------------------------------------------------ the context

class RunContextProtocol(Protocol):
    """What one run knows, as a plugin may read it.

    The builder collections are keyed by builder name and typed by the
    contract's builder protocols; the domain items are ``Any``; the
    provider-specific image is :class:`~.image.ProviderSpecificImageProtocol`;
    the executables are :class:`~.executables.ExecutableProtocol`.
    """

    # --- the run
    @property
    def dry_run(self) -> bool: ...

    @property
    def run_id(self) -> str: ...

    @property
    def start_time(self) -> datetime: ...

    @property
    def dateformat(self) -> str: ...

    @property
    def current_lifecycle(self) -> LifecycleLike | None: ...

    # --- paths
    @property
    def working_path(self) -> Path: ...

    @property
    def generation_path(self) -> Path: ...

    # --- the configuration
    @property
    def config(self) -> Mapping[str, Any]: ...

    @property
    def executables(self) -> Mapping[str, ExecutableProtocol]: ...

    # --- the builders, by name
    @property
    def runtime_builders(self) -> Mapping[str, RuntimeBuilderProtocol]: ...

    @property
    def os_builders(self) -> Mapping[str, OsBuilderProtocol]: ...

    @property
    def mod_builders(self) -> Mapping[str, ModBuilderProtocol]: ...

    @property
    def storage_builders(self) -> Mapping[str, StorageBuilderProtocol]: ...

    @property
    def group_builders(self) -> Mapping[str, GroupBuilderProtocol]: ...

    @property
    def user_builders(self) -> Mapping[str, UserBuilderProtocol]: ...

    @property
    def state_backends(self) -> Mapping[str, StateBuilderProtocol]: ...

    @property
    def all_sorted_builders(self) -> Sequence[BuilderProtocol]: ...

    def get_provider_specific_image(self, source_name: str, runtime: str) -> ProviderSpecificImageProtocol | None: ...

    # --- the domain items (their protocols are a later stage)
    @property
    def instances(self) -> Sequence[Any]: ...

    @property
    def storages(self) -> Sequence[Any]: ...

    @property
    def users(self) -> Sequence[Any]: ...

    @property
    def images_map(self) -> Mapping[str, Any]: ...

    @property
    def root_group(self) -> Any: ...

    # --- the run's state and services
    @property
    def meta_state(self) -> MetaStateProtocol: ...

    @property
    def services(self) -> ServicesProtocol: ...

    def plugin_state(self, key: str, factory: Callable[[], Any]) -> Any: ...

    def extend_finalization_phase(self, phase: ExecutionLifecyclePhase,
                                  executables: Sequence[ExecutableProtocol]) -> None: ...
