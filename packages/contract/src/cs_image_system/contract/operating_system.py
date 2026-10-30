# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The OS kind (stage 30): an OS family and version, the vendor image query
that finds it on each runtime, and the update policy a base image bakes
with. A runtime subconfig (one per runtime the OS builder serves) and the
resolved base image are the core's models and ``Any`` here.

Stage 106: ``family`` is the token a tree writes (``get_vendor_family``);
what the token IS, as the image-source catalog says, is ``get_family``,
which everything that branches on a family reads. A model class names the
families it serves (``families``), so a type may be defaulted from a family
and a contradiction between the two refused."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .assets import AssetSet
from .core import BuilderModelProtocol, BuilderProtocol
from .lifecycle import ExecutionLifecyclePhase


class OsBuilderModelProtocol(BuilderModelProtocol, Protocol):
    """An entry under ``os_builders:``."""

    family: str
    family_version: str
    architecture: str
    default_primary_disk_size: str | int
    owners: list[str]
    query: dict[str, Any]
    runtimes: list[Any]
    config_username: str | None
    auto_update: bool
    update: dict[str, Any] | None
    identity_types: list[str]
    storage_types: list[str]
    admin_user: str
    admin_public_keys: list[str] | None
    local_test_image: str | None
    tests: dict[str, Any]

    def get_owners(self) -> Sequence[str]: ...

    def get_family(self) -> str: ...

    def get_vendor_family(self) -> str: ...

    def get_family_version(self) -> str: ...

    def get_architecture(self) -> str: ...

    def get_default_primary_disk_size(self) -> str | int: ...

    def get_config_username(self) -> str | None: ...

    def get_auto_update(self) -> bool: ...

    def get_query(self) -> Mapping[str, Any]: ...

    def get_runtimes(self) -> Sequence[Any]: ...

    def get_modifications(self) -> list: ...

    def get_osrtconfig_by_type(self, runtime_type: str) -> Any | None: ...

    def get_command_to_update(self) -> list[str]: ...

    def effective_update_policy(self) -> Any: ...

    def commands_for_policy(self, policy: Any) -> list[str]: ...

    def get_identity_types(self) -> list[str]: ...

    def get_storage_types(self) -> list[str]: ...

    def get_admin_user(self) -> str: ...

    def get_admin_public_keys(self) -> list[str] | None: ...

    @classmethod
    def families(cls) -> tuple[str, ...]: ...


class OsBuilderProtocol(BuilderProtocol, Protocol):
    """An OS builder: the family facts, the vendor query per runtime, and the
    resolved base image it generates from a query's result."""

    def get_family(self) -> str: ...

    def get_vendor_family(self) -> str: ...

    def get_family_version(self) -> str: ...

    def get_architecture(self) -> str: ...

    def get_config_username(self) -> str | None: ...

    def get_auto_update(self) -> bool: ...

    def get_runtimes(self) -> Sequence[Any]: ...

    def get_owners(self) -> Sequence[str]: ...

    def get_query(self) -> Mapping[str, Any]: ...

    def generate_resolved_image(self, phase: ExecutionLifecyclePhase, image_id: Any, owners: list[str],
                                query_result: Mapping[str, Any], resolved: bool = True,
                                resolutions: Mapping[str, tuple[Any, list[str]]] | None = None) -> Any | None: ...

    def generate_items_for_os_update(self, image: Any, image_builder: Any, phase: Any, build_path: Any) -> AssetSet: ...

    def get_runtime_config_query_results(self, runtime: Any) -> Mapping[str, Any] | None: ...

    def get_configs_for_image_builders(self) -> dict[str, Any]: ...
