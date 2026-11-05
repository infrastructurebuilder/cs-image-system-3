# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The storage kind (stage 30): volumes, filesystems and buckets an instance
mounts, each with a lifecycle (standing, archived, restored, transient,
destroyed). The storage item is the core's model and ``Any`` here."""
from __future__ import annotations

from typing import Any, Protocol

from .core import BuilderProtocol, RuntimeEnabledBuilderModelProtocol


class StorageBuilderModelProtocol(RuntimeEnabledBuilderModelProtocol, Protocol):
    """An entry under ``storage_builders:``: a runtime and the universal
    fields; the plugin declares the rest."""


class StorageBuilderProtocol(BuilderProtocol, Protocol):
    """A storage builder: what kind of capability it provides to the images
    that mount it, how many instances may attach one, the prerequisites an
    image bakes, the verification an instance runs, and the state
    transitions it can carry out. ``platform_mounts`` (stage 103 branch 2)
    says the platform attaches AND mounts the storage before the machine's
    first command (a container volume), so the launch script neither
    formats nor mounts it and only makes the group's subtree.

    The launch hooks: a storage owns its device and mount lines. The
    core computes an instance's mount records and assembles the launch
    script and its ansible equivalent; what each mount contributes is the
    storage builder's answer. ``launch_mount(storage, mapping, index)``
    is the storage-specific keys of the mount record (a device name for
    a block store; ``index`` counts the earlier mounts of the same
    capability type on the instance); ``launch_script_lines(mount,
    group)`` is the mount's whole block of the launch shell script, from
    its header to the group's subtree; ``launch_tasks(mount, group)`` is
    the whole ansible task list for the mount; ``launch_variables()``
    names the template variables (extra-vars) the blocks read by
    reference, which the core lists after ``group_gid`` and before the
    enrollment token."""

    def add_storage(self, storage: Any) -> None: ...

    @classmethod
    def capability_type(cls) -> str: ...

    def attachment_cardinality(self) -> str: ...

    def is_zonal(self) -> bool: ...

    def is_posix(self) -> bool: ...

    def platform_mounts(self) -> bool: ...

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]: ...

    def verify_commands(self, os_family: str | None = None) -> list[str]: ...

    def transition_actions(self, storage: Any, from_state: str | None, to_state: str) -> list[Any]: ...

    def validate_lifecycle(self, storage: Any) -> list[str]: ...

    def query_state(self) -> dict[str, dict[str, Any]]: ...

    def destroy_whitelist(self, storage: Any) -> list[str]: ...

    def retag_storage(self, storage: Any, tags: dict[str, str]) -> bool: ...

    def launch_mount(self, storage: Any, mapping: Any, index: int) -> dict[str, Any]: ...

    def launch_script_lines(self, mount: dict[str, Any], group: str | None) -> list[str]: ...

    def launch_tasks(self, mount: dict[str, Any], group: str | None) -> list[dict[str, Any]]: ...

    def launch_variables(self) -> tuple[str, ...]: ...
