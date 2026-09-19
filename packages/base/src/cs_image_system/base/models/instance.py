# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
import logging
from typing import Annotated, TYPE_CHECKING, Any, cast


log = logging.getLogger(__name__)
from .model_config import CSIS_MODEL_CONFIG
from pydantic import Field, model_validator
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from ..helpers.field_helpers import deferred_list_field, fk_field
from ..protocols.name_typed_protocol import SelfInjectedNameProtocol, SubItemOverrideProtocol

STORAGE_MAPPING = "storage_mapping"
from ..constants import DEFAULT, VCT
from .root_item import RootItem, SubRootItem
if TYPE_CHECKING:
    from ..models.storage import Storage


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class StorageMapping(SubRootItem, SelfInjectedNameProtocol):
    """An instance's attachment of one named storage (N16: attachment is
    per instance). ``name`` is the systemwide-unique storage name; the group
    that governs access is the instance IMAGE's owning group, never declared
    here."""
    type_: Annotated[str, Field(alias="type")] = fk_field(target = VCT.STORAGE_BUILDER_MODEL, default=DEFAULT, metadata={
        "description": "The type of the storage mapping is a name of a builder",
        "required": True,
    })
    mount_point: str = "/mnt/storage"
    min_size: int = 100 # minumum size (will expand to size in actual storage moel if less)

    _model_id: str | None = fk_field(target = VCT.STORAGE_BUILDER_MODEL,
                                     init=False,
                                     default=None, metadata={
                                      "description": "The name of the model this property holding object is associated with",
    })

    @classmethod
    def csis_name(cls) -> str:
        return STORAGE_MAPPING
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STORAGE_MAPPING_ITEM_MODEL
    def get_classification(self) -> VCT | None:
        return self.csis_classifier()
    def get_mount_point(self) -> str:
        return self.mount_point
    def get_min_size(self) -> int:
        return self.min_size


    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.type_:
            log.error(f"StorageMapping '{self.get_display_name()}' must have a type specified.")
            raise ValueError(f"StorageMapping '{self.get_display_name()}' must have a type specified.")
        if self.aliases:
            log.warning(f"StorageMapping '{self.get_display_name()}' has aliases defined in configuration, but aliases are "
                        f"not currently supported for StorageMappings. Ignoring aliases: {self.aliases}")
        self.aliases = set()
        if not self.mount_point:
            log.error(f"StorageMapping '{self.get_display_name()}' must have a mount_point specified.")
            raise ValueError(f"StorageMapping '{self.get_display_name()}' must have a mount_point specified.")
        if self.min_size <= 0:
            log.error(f"StorageMapping '{self.get_display_name()}' must have a positive min_size specified. Got: {self.min_size}")
            raise ValueError(f"StorageMapping '{self.get_display_name()}' must have a positive min_size specified. Got: {self.min_size}")
        self._storage = None

    @property
    def storage(self) -> Storage:
        if self._storage is None:
            log.error(f"StorageMapping '{self.get_display_name()}' does not have an associated Storage instance. This should have been set during generation.")
            raise ValueError(f"StorageMapping '{self.get_display_name()}' does not have an associated Storage instance. This should have been set during generation.")
        return self._storage
    @storage.setter
    def storage(self, value: Storage) -> None:
        if not self._storage is None and self._storage is not value:
            log.error(f"StorageMapping '{self.get_display_name()}' already has an associated Storage instance.")
            raise ValueError(f"StorageMapping '{self.get_display_name()}' already has an associated Storage instance.")
        self._storage = value


@dataclass(config=CSIS_MODEL_CONFIG)
class Instance(RootItem, SubItemOverrideProtocol, SelfInjectedNameProtocol):
    """Represents a container instance with metadata and configuration.

    Parameters
    ----------:
    image: str - The existing Image to base this Instance on. Group ownership
        lives on the image (V2 Q4/§3F2): all instances of one image share its
        owning group by construction, so there is no per-instance ``groups``.
    storages: list[StorageMapping]
        The named storages this instance mounts (per-instance attachment,
        N16), validated against the image's pinned capabilities and each
        storage's allowed groups via the image's owning group.
    userdata: str
        User data script to be executed on instance initialization.
        This is sent through as a single string.
    availability_zone : str | None
        The zone this lives in, when it is bound to one. Declared, never
        inferred: absent means "no constraint", and a set that is not
        compatible -- more than one distinct zone across an instance, its
        zonal storages and its runtime's subnet -- is refused at validate
        (stage 52). Changing a zone REPLACES a zonal resource, so the
        refusal is cheaper than the plan that follows it.
    """

    type_: Annotated[str, Field(alias="type")] = fk_field(target = VCT.INSTANCE_BUILDER_MODEL,
                         default=DEFAULT,
                         metadata={
                            "description": "The type of the instance is a name of a builder",
                            "required": True,
                         })
    image: str = fk_field(target=VCT.IMAGE_MODEL, default=None, metadata={
        "description": "The name of the image to use for this instance. This should be the name of an existing image defined in the configuration. This is required for generation, but not necessarily for validation, since some builders might allow you to specify an instance without an image and then assign one during generation based on other criteria.",
        "required": False, # We might want to allow this to be optional for certain builders)
    })
    runtime: str = fk_field(target = VCT.RUNTIME_BUILDER_MODEL,
                            default=DEFAULT,
                            metadata={
                                "description": "The runtime provider to use for this instance",
                                "required": True,
                            })
    description: str | None = "Instance from {{ image.name }}"
    storages: list[dict[str, Any]] = deferred_list_field(builder_vct = VCT.STORAGE_BUILDER_MODEL,
                                                        item_vct=VCT.STORAGE_MAPPING_ITEM_MODEL,
                                                        default_factory=list) # list of storage mappings
    availability_zone: str | None = None      # stage 52
    userdata: str = ""
    # Convergent bakes (stage 9.5): pinned (default) keeps the launched build until an
    # explicit `upgrade instance`; follow plans the gated replacement whenever the
    # image's series head moves (recorded as op: follow).
    image_policy: str = "pinned"
    # Declared ephemerality (stage 10.1): the instance-image lifecycle launches it,
    # runs the runtime's verification, and destroys it in the same run; a failed
    # verification leaves it standing for inspection and fails the run.
    ephemeral: bool = False
    # Ephemeral failure policy (stage 11.3; DESIGN §3H): what happens when the
    # verification FAILS. on_failure: keep (default: left standing, the run
    # fails) | teardown (torn down anyway, the run still fails); teardown_after:
    # a duration ("2h", "30m", "1d") after a failed verification past which the
    # next run tears the standing instance down without re-verifying. None
    # inherits the runtime's defaults.
    on_failure: str | None = None
    teardown_after: str | None = None
    # Per-instance size; empty = the runtime's default machine type. The
    # default can be too small to run the image's services (a t2.micro's
    # 1 GB OOM-killed the SSM agent minutes after boot, found live).
    machine_type: str = ""

    @model_validator(mode="before")
    @classmethod
    def _per_instance_groups_are_retired(cls, data: Any) -> Any:
        """V1 declared `groups:` per instance (with an ALL magic value); V2
        moved ownership to the instance image (DESIGN §3F2, rev 12). The
        field was kept after stage 21 only so a stale declaration got this
        message rather than the generic unknown-key refusal; since
        2026-09-14 the message comes from here and the field is gone."""
        keys = data if isinstance(data, dict) else (getattr(data, "kwargs", None) or {})
        if "groups" in keys:
            raise ValueError(
                f"Instance '{keys.get('name', '<unnamed>')}' declares 'groups'; V2 removed per-instance "
                "groups (and the ALL magic value): the owning group lives on the instance image "
                "(DESIGN §3F2, rev 12). Set 'group:' on the image instead.")
        return data

    @classmethod
    def csis_name(cls) -> str:
        return "instance"
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.INSTANCE_MODEL

    def get_classification(self) -> VCT:
        return self.csis_classifier()

    def __post_init__(self) -> None:
        super().__post_init__() # validates name and aliases, sets name to safe_name, etc
        if not self.image:
            # This might blow up the default description
            log.warning(f"Instance '{self.get_display_name()}' does not have an image specified. This instance will be ignored during generation.")
            # raise ValueError("Instance must have an image specified.")

    def finalize(self):
        if self._finalized:
            return
        super().finalize()
        if not self.image:
            log.error(f"Instance '{self.get_display_name()}' cannot be finalized without an image specified.")
            raise ValueError(f"Instance '{self.get_display_name()}' cannot be finalized without an image specified.")
        seen: dict[str, StorageMapping] = {}
        for _storage_mapping in self.storages:
            storage_mapping = cast(StorageMapping, _storage_mapping)
            storage_name = storage_mapping.get_name()
            if not storage_name:
                log.warning(f"Instance '{self.get_display_name()}' has a storage mapping without a name; ignored")
                continue
            if storage_name in seen:
                log.warning(f"Instance '{self.get_display_name()}' attaches storage '{storage_name}' twice; "
                            "the later mapping wins")
            seen[storage_name] = storage_mapping
        self.storages = list(seen.values())  # type: ignore

    def storage_mappings(self) -> list[StorageMapping]:
        return [cast(StorageMapping, m) for m in self.storages if not isinstance(m, dict)]

    def get_subitem_overrides(self) -> dict[VCT, type[SubRootItem]] | None:
        return {
            VCT.STORAGE_MAPPING_ITEM_MODEL: StorageMapping,
        }
