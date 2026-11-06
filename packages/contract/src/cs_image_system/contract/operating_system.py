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
and a contradiction between the two refused.

Stage 105: ``output_image_name`` is the declared PREFIX of every build's
name (the run's timestamp is appended); unset, the core names a build
``<image>-<image builder>`` (a base image: ``<OS builder>-<runtime>``). A
runtime entry's value overrides the OS builder's.

The package manager is the OS type's. A type answers, as classmethods,
what its manager's lines are (install, refresh, a presence test, enabling
a service, the python ansible needs); every plugin that bakes a package
asks the type that serves the image's family (the core resolves the type
from the family) and never names a manager itself."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .assets import AssetSet
from .core import BuilderModelProtocol, BuilderProtocol
from .lifecycle import ExecutionLifecyclePhase

#: How long a bake's package line waits for the package database when the
#: machine's own first-boot updater holds it (seconds). A type whose
#: manager takes no such option ignores it; a caller that passes nothing
#: gets the manager's own default.
PACKAGE_LOCK_TIMEOUT = 600


class OsBuilderModelProtocol(BuilderModelProtocol, Protocol):
    """An entry under ``os_builders:``."""

    def get_command_to_update(self) -> list[str]: ...

    def commands_for_policy(self, policy: Any) -> list[str]: ...

    @classmethod
    def families(cls) -> tuple[str, ...]: ...

    # --- the package manager: the type's lines, never a caller's
    @classmethod
    def package_format(cls) -> str:
        """The package format the type's manager installs, by the
        format's own short name (``deb``, ``rpm``, alpine's): what a
        plugin reads to choose which vendor artifact or repository recipe
        to fetch."""
        ...

    @classmethod
    def package_install_command(cls, packages: Sequence[str], *, lock_timeout: int | None = None) -> str:
        """One shell line that installs the named packages (a package may
        be a path or URL the manager accepts), waiting ``lock_timeout``
        seconds for the package database where the manager can."""
        ...

    @classmethod
    def package_update_command(cls, *, lock_timeout: int | None = None) -> str:
        """One shell line that refreshes the manager's package lists."""
        ...

    @classmethod
    def package_present_check(cls, package: str) -> str:
        """One shell line that exits non-zero, naming the package on
        stderr, unless the package is installed. It must exit for itself:
        ``set -e`` ignores a command in an AND-OR list, so a bare
        ``query || fail`` cannot stop a bake."""
        ...

    @classmethod
    def service_enable_command(cls, service: str) -> str:
        """One shell line that enables a service at boot."""
        ...

    @classmethod
    def ansible_python_install_command(cls) -> str:
        """One shell line that leaves a python ansible's modules can run
        under on a bare image of this type (the newest the type offers);
        the interpreter is then found by a generic lookup."""
        ...

    def get_owners(self) -> Sequence[str]: ...

    def get_vendor_family(self) -> str: ...

    def get_family_version(self) -> str: ...

    def get_architecture(self) -> str: ...

    def get_default_primary_disk_size(self) -> str | int: ...

    def get_auto_update(self) -> bool: ...

    def get_query(self) -> Mapping[str, Any]: ...

    def get_runtimes(self) -> Sequence[Any]: ...

    def effective_update_policy(self) -> Any: ...

    def get_identity_types(self) -> list[str]: ...

    def get_storage_types(self) -> list[str]: ...

    def get_admin_user(self) -> str: ...

    def get_admin_public_keys(self) -> list[str] | None: ...


class OsBuilderProtocol(BuilderProtocol, Protocol):
    """An OS builder: the family facts, the vendor query per runtime, and the
    resolved base image it generates from a query's result."""

    def get_family(self) -> str: ...

    def generate_items_for_os_update(self, image: Any, image_builder: Any, phase: Any, build_path: Any) -> AssetSet: ...

    def get_family_version(self) -> str: ...

    def get_architecture(self) -> str: ...

    def get_config_username(self) -> str | None: ...

    def generate_resolved_image(self, phase: ExecutionLifecyclePhase, image_id: Any, owners: list[str],
                                query_result: Mapping[str, Any], resolved: bool = True,
                                resolutions: Mapping[str, tuple[Any, list[str]]] | None = None) -> Any | None: ...

    def get_configs_for_image_builders(self) -> dict[str, Any]: ...


