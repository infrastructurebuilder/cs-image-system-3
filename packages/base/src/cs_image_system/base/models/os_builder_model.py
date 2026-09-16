# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from collections.abc import Mapping
import logging
from dataclasses import field
from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import  Any, Sequence
from packaging.version import Version, parse

from cs_image_system.base import registry

from .os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
from .update_policy import POLICY_FULL, POLICY_NONE, UpdatePolicy

from ..constants import DEFAULT,  VCT
from .builder_model import BuilderModel

log = logging.getLogger(__name__)

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OsBuilderModel(BuilderModel):
    """
    OS/Source configuration data object.
    Base class for specific OS builder configurations.
    Attributes:
    """
    family: str
    family_version: str 
    # output_image_name: str = "{{ builder.name }}-{{ this.family }}-{{ this.family_version }}" # REMOVED
    # exclude_timestamp_from_output_image_name: bool = False # Should never be set to true # Based on control logic
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
        reg = registry.Registry()
        for r in self.runtimes:
            if r.get_image_builder() in nameset:
                raise ValueError(
                    f"Duplicate runtime configuration name {r.get_image_builder()} in OS builder {self.name}"
                )
            nameset.add(r.get_image_builder())
            r.model_id = self.global_id
        if self.default_primary_disk_size == DEFAULT:
            self.default_primary_disk_size = 200
            
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
        return self.family
    def get_family_version(self) -> str:
        return self.family_version
    # def get_output_image_name(self) -> str:
    #     return self.output_image_name
    # def get_exclude_timestamp_from_output_image_name(self) -> bool:
    #     return self.exclude_timestamp_from_output_image_name
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
        """Full package-level update (legacy hook; policy 'full')."""
        return []

    def effective_update_policy(self) -> UpdatePolicy:
        return UpdatePolicy.from_config(self.update, auto_update=bool(self.auto_update))

    def commands_for_policy(self, policy: UpdatePolicy) -> list[str]:
        """Family-specific commands realizing an update policy. The base
        implementation knows only 'none' and 'full'; package-manager
        families (dnf, apt) implement the targeted policies."""
        if policy.policy == POLICY_NONE and not policy.pin:
            return []
        if policy.policy == POLICY_FULL and not policy.exclude and not policy.pin:
            return self.get_command_to_update()
        raise NotImplementedError(
            f"OS builder {self.name} ({self.type_}) does not implement update policy {policy.policy!r} "
            "with exclude/pin; use a dnf/apt family or policy: full")
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
    def get_tags(self) -> Mapping[str, str]:
        return self.tags

