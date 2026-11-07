# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import field
from typing import Any, Sequence

from packaging.version import Version, parse
from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.contract.constants import DEFAULT, VCT
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.contract.operating_system import OsBuilderModelProtocol

from ..image_sources import current_catalog
from .builder_model import BuilderModel
from .os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
from .update_policy import POLICY_FULL, POLICY_NONE, UpdatePolicy

log = logging.getLogger(__name__)

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OsBuilderModel(BuilderModel, OsBuilderModelProtocol):
    """
    OS/Source configuration data object.
    Base class for specific OS builder configurations.
    Attributes:
    """
    family: str
    family_version: str 
    # the declared PREFIX of this base image's build names on
    # every runtime whose entry names none (a template: `this` is this
    # builder); the run's timestamp is always appended, never excluded.
    # Unset: `<name>-<runtime>`, the shape every build carried before.
    output_image_name: str | None = None
    architecture: str = DEFAULT
    default_primary_disk_size: str | int = DEFAULT # in Gb
    tags: dict[str, str] = field(default_factory=dict)
    owners: list[str] = field(default_factory=list)
    query: dict[str, Any] = field(default_factory=dict)
    # image_builder: str = fk_field(target = VCT.IMAGE_BUILDER_MODEL,
    #                               default=DEFAULT, metadata={
    #     "description": "Image builder for this OS builder",
    #     "required": True,
    # })
    runtimes: list[OSBuilderBaseImageBuilderSubconfig] = field(default_factory=list)

    # Sudo-capable user on the image to use for provisioning.
    config_username: str | None = None # Username to use for provisioning
    # Apply the OS-provided package update during base-image builds; runtime
    # subconfigs may override per image builder. Alias for update.policy: full.
    auto_update: bool = False
    # EXPLORE targeted updates: the declarative update policy (see
    # models/update_policy.py); takes precedence over auto_update.
    update: dict[str, Any] | None = None
    # V2 (DESIGN §3F1, Q1/N4): a base image declares capability on two
    # symmetric axes. For each declared type the owning plugin bakes its
    # prerequisites (installed but dormant); anything undeclared is unusable
    # downstream even where post-hoc attachment would be easy -- declared
    # capability, not technical possibility, is the contract.
    identity_types: list[str] = field(default_factory=list)
    storage_types: list[str] = field(default_factory=list)
    # The mandatory local admin user (Q2 sliver, N9/N12): operator-supplied
    # PUBLIC keys only; None = the global config.admin_public_keys list.
    admin_user: str = "csisadmin"
    admin_public_keys: list[str] | None = None
    # EXPLORE mod tests: the container image standing in for this OS when
    # modifications are tested locally (default: derived from family/version).
    local_test_image: str | None = None
    # EXPLORE image tests: in-bake assertions for this base image.
    tests: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.OS_BUILDER_MODEL

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.runtimes:
            raise ValueError(
                f"OS builder {self.name} must have at least one runtime configuration."
            )
        nameset: set[str] = set()
        for r in self.runtimes:
            if r.get_image_builder() in nameset:
                raise ValueError(
                    f"OS builder {self.name}: two `runtimes` entries name image builder "
                    f"{r.get_image_builder()}; one entry per image builder"
                )
            nameset.add(r.get_image_builder())
            # the runtime subconfigs are parented ONCE, by the OS builder
            # that wraps this model (OsBuilderBase.__post_init__, "self-registers");
            # a claim of the model's own here used to be overwritten there on every load
        if self.default_primary_disk_size == DEFAULT:
            self.default_primary_disk_size = 200
        self.family = str(self.family).strip().lower()
        # a type that does not serve what the family IS is a
        # contradiction between the entry and the catalog; refused when the
        # family is one some registered type serves (a token nobody serves
        # is only a token)
        real = self.get_family()
        served = tuple(f.lower() for f in type(self).families())
        if real not in served:
            others = sorted(name for name, cls in self._reg.models_under(VCT.OS_BUILDER_MODEL).items()
                            if real in tuple(f.lower() for f in getattr(cls, "families", lambda: ())()))
            if others:
                raise ValueError(
                    f"OS builder {self.name}: family {self.family!r} is {real!r} (the image-source catalog), "
                    f"which type {self.type_!r} does not serve (it serves {', '.join(served)}); "
                    f"{', '.join(others)} serve(s) it: declare that type, or fix `is` in the catalog")
            
    def version(self) -> Version  | None:
        try :
            return parse(self.family_version)
        except Exception as e:
            log.error(f"Error parsing version from family_version '{self.family_version}' "
                      f"in OS builder {self.name}: {e}")
            return None

    def get_owners(self) -> Sequence[str]:
        return self.owners
    def get_family(self) -> str:
        """What the declared family IS: the image-source
        catalog's ``is`` for it, else the token itself. Everything that
        branches on a family reads this one."""
        return current_catalog().effective_family(self.family, self.family_version)  # a model holds no context
    def get_vendor_family(self) -> str:
        """The family token as written (``rhel-from-jerry``): the catalog's key."""
        return self.family
    def get_family_version(self) -> str:
        return self.family_version
    @classmethod
    def families(cls) -> tuple[str, ...]:
        """The families this type serves: its own key, unless a
        subclass names more (the rhel type serves the rebuilds)."""
        return (cls.csis_name(),)
    def get_output_image_name(self) -> str | None:
        return self.output_image_name or None
    def get_architecture(self) -> str:
        return self.architecture
    def get_default_primary_disk_size(self) -> str | int:
        return self.default_primary_disk_size
    # def get_image_builder(self) -> str:
    #     return self.image_builder
    def get_config_username(self) -> str | None:
        return self.config_username
    def get_auto_update(self) -> bool:
        return self.auto_update
    def get_query(self) -> Mapping[str, Any]:
        return self.query
    def get_runtimes(self) -> Sequence[OSBuilderBaseImageBuilderSubconfig]:
        return self.runtimes
    def get_modifications(self) -> list:
        return []
    def get_osrtconfig_by_type(self, runtime_type: str) -> OSBuilderBaseImageBuilderSubconfig | None:
        for rt in self.get_runtimes():
            if rt.get_image_builder() == runtime_type:
                return rt
        return None
    def get_command_to_update(self) -> list[str]:
        """The full update for a family without a package-manager policy
        model: alpine's one path (every family with a policy
        model answers through ``commands_for_policy`` and never reaches
        this)."""
        return []

    def effective_update_policy(self) -> UpdatePolicy:
        return UpdatePolicy.from_config(self.update, auto_update=bool(self.auto_update))

    def commands_for_policy(self, policy: UpdatePolicy) -> list[str]:
        """Family-specific commands realizing an update policy. The base
        implementation knows only 'none' and 'full'; the types with a
        policy model implement the targeted policies."""
        if policy.policy == POLICY_NONE and not policy.pin:
            return []
        if policy.policy == POLICY_FULL and not policy.exclude and not policy.pin:
            return self.get_command_to_update()
        raise NotImplementedError(
            f"OS builder {self.name} ({self.type_}) does not implement update policy {policy.policy!r} "
            "with exclude/pin; use a family whose type has a policy model, or policy: full")
    # ------------------------------------------------ the package manager
    # The type's, never the core's: the base answers nothing, by name, so a
    # type that forgets one hook fails at the first bake that asks, not
    # with a line for some other family's manager.
    @classmethod
    def _no_package_manager(cls, hook: str) -> NotImplementedError:
        try:
            name = cls.csis_name()
        except NotImplementedError:
            name = cls.__name__
        return NotImplementedError(f"OS type {name!r} declares no package manager: it does not implement {hook}()")

    @classmethod
    def package_format(cls) -> str:
        raise cls._no_package_manager("package_format")

    @classmethod
    def package_install_command(cls, packages: Sequence[str], *, lock_timeout: int | None = None) -> str:
        raise cls._no_package_manager("package_install_command")

    @classmethod
    def package_update_command(cls, *, lock_timeout: int | None = None) -> str:
        raise cls._no_package_manager("package_update_command")

    @classmethod
    def package_present_check(cls, package: str) -> str:
        raise cls._no_package_manager("package_present_check")

    @classmethod
    def service_enable_command(cls, service: str) -> str:
        raise cls._no_package_manager("service_enable_command")

    @classmethod
    def ansible_python_install_command(cls) -> str:
        raise cls._no_package_manager("ansible_python_install_command")

    def get_identity_types(self) -> list[str]:
        return [str(t).strip().lower() for t in (self.identity_types or []) if str(t).strip()]
    def get_storage_types(self) -> list[str]:
        return [str(t).strip().lower() for t in (self.storage_types or []) if str(t).strip()]
    def get_admin_user(self) -> str:
        return self.admin_user
    def get_admin_public_keys(self) -> list[str] | None:
        return self.admin_public_keys
    # def get_modifications(self) -> Sequence[ModItemModel]:
    #     return self.modifications # type: ignore  # This will be OK after deferred_list_field is resolved
    def get_tags(self) -> dict[str, str]:
        return self.tags

