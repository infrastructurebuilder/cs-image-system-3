# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from typing import TYPE_CHECKING, Any, TypeVar


from ..constants import VCT
from .builder_base import BuilderBase
from ..models.storage import Storage
from ..models.storage_builder import StorageBuilderModel

if TYPE_CHECKING:
    from ..models.executable import ExecutableModel

# Attachment cardinality a storage plugin declares (N10/N16): how many
# instances may mount one storage instance at a time.
CARDINALITY_SINGLE = "single"
CARDINALITY_MANY = "many"


TSTORAGE = TypeVar("TSTORAGE", bound=StorageBuilderModel)
class StorageBuilderBase(BuilderBase[TSTORAGE]):
    """Base of every storage plugin.

    V2 contract (DESIGN §3E): a storage plugin owns

    * a **capability type name** -- the token a base image declares in
      ``storage_types`` to say it carries this type's prerequisites;
    * its **attachment cardinality** (EBS single, EFS/S3 many);
    * whether the store is **POSIX** (gid-governed subtrees) or maps
      "readable by all" its own way;
    * the **type-level prerequisites** baked into declaring base images;
    * the **transition actions** run when one of its storages changes state.
    """

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STORAGE_BUILDER
    def add_storage(self, storage: "Storage") -> None:
        """Add a storage to the builder's configuration."""
        self.model._storages.append(storage)

    # ---------------------------------------------------------- V2 contract
    @classmethod
    def capability_type(cls) -> str:
        """The storage type token base images declare (e.g. ``efs``).
        Defaults to the plugin's canonical name."""
        name = getattr(cls, "csis_name", None)
        return str(name()) if callable(name) else cls.__name__

    def attachment_cardinality(self) -> str:
        return CARDINALITY_MANY

    def is_posix(self) -> bool:
        """POSIX filesystems realize group access with gid-owned subtrees
        (N13/N15); non-POSIX stores define their own mapping (N3)."""
        return True

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]:
        """Shell commands baked into a base image that declares this storage
        type (Q1/N10): drivers, agents, mount tooling. Empty = no prerequisites
        (e.g. EBS), which must still be declared to be usable (N4)."""
        return []

    def verify_commands(self, os_family: str | None = None) -> list[str]:
        """Shell assertions proving this storage type's prerequisites are
        present on a base image that declares it."""
        return []

    def transition_actions(self, storage: Storage, from_state: str | None,
                           to_state: str) -> list["ExecutableModel"]:
        """Commands the plugin runs for a state transition (N21). Default: none;
        terraform handles the resource-shaped part of the transition."""
        return []

    def validate_lifecycle(self, storage: Storage) -> list[str]:
        """Errors for a ``lifecycle:`` declaration (stage 15). Default: the
        builder realizes no data lifecycle, so any declaration is refused;
        builders that do (S3, EFS) validate their own keys."""
        if getattr(storage, "lifecycle", None):
            return [f"storage '{storage.get_name()}' ({storage.type_}) declares a data lifecycle, which its "
                    f"builder does not realize (no lifecycle on {self.capability_type()} storages)"]
        return []

    def query_state(self) -> dict[str, dict[str, Any]]:
        """Reality check (EXPLORE state query): ``{storage name: {present,
        type, id?, state?, tags?}}`` for every storage this builder owns --
        live ones and tombstones alike -- read-only. Optional."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot query storage state")

    def destroy_whitelist(self, storage: Storage) -> list[str]:
        """Terraform addresses whose destruction the apply gate whitelists when
        this storage's requested state is ``destroyed`` (N19)."""
        return []
