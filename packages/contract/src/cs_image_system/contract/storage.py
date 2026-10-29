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
    transitions it can carry out."""

    def add_storage(self, storage: Any) -> None: ...

    @classmethod
    def capability_type(cls) -> str: ...

    def attachment_cardinality(self) -> str: ...

    def is_zonal(self) -> bool: ...

    def is_posix(self) -> bool: ...

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]: ...

    def verify_commands(self, os_family: str | None = None) -> list[str]: ...

    def transition_actions(self, storage: Any, from_state: str | None, to_state: str) -> list[Any]: ...

    def validate_lifecycle(self, storage: Any) -> list[str]: ...

    def query_state(self) -> dict[str, dict[str, Any]]: ...

    def destroy_whitelist(self, storage: Any) -> list[str]: ...

    def retag_storage(self, storage: Any, tags: dict[str, str]) -> bool: ...
