# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from typing import TYPE_CHECKING, Any, TypeVar


from cs_image_system.contract.constants import VCT
from .builder_base import BuilderBase
from cs_image_system.contract.storage import StorageBuilderProtocol
from ..models.storage import Storage
from ..models.storage_builder import StorageBuilderModel

if TYPE_CHECKING:
    from ..models.executable import ExecutableModel

# The attachment cardinalities a storage plugin declares and the mount mark
# the startup script writes are the contract's vocabulary; this path keeps them.
from cs_image_system.contract.storage_vocabulary import CARDINALITY_MANY, CARDINALITY_SINGLE  # noqa: F401, E402
from cs_image_system.contract.launch_vocabulary import MOUNT_MARK  # noqa: F401, E402


def mount_mark_line(mount_point: str) -> str:
    """The script line that reports one mount point's state, after the mount.
    A storage whose block carries this line is one the script mounts; the
    verification reads the declared mount points off exactly that."""
    return (f"findmnt -rn '{mount_point}' >/dev/null 2>&1 && echo '{MOUNT_MARK} {mount_point} mounted' "
            f"|| echo '{MOUNT_MARK} {mount_point} NOT mounted'")


TSTORAGE = TypeVar("TSTORAGE", bound=StorageBuilderModel)
class StorageBuilderBase(BuilderBase[TSTORAGE], StorageBuilderProtocol):
    """Base of every storage plugin.

    V2 contract (DESIGN §3E): a storage plugin owns

    * a **capability type name** -- the token a base image declares in
      ``storage_types`` to say it carries this type's prerequisites;
    * its **attachment cardinality** (a block store single, a shared
      filesystem or an object store many);
    * whether the store is **POSIX** (gid-governed subtrees) or maps
      "readable by all" its own way;
    * the **type-level prerequisites** baked into declaring base images;
    * the **transition actions** run when one of its storages changes state;
    * its **device and mount lines** at launch: the storage-specific keys of
      an instance's mount record, the mount's block of the launch script and
      of its ansible playbook, and the template variables those read by
      reference (the ``launch_*`` hooks; the core only assembles).

    The pieces every mount's block shares -- the header with its ``mkdir``,
    the mount mark, the group's subtree, the block-device sequence, an
    fstab entry, and their ansible counterparts -- are the static helpers
    below, so a plugin composes its block rather than copying it.
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
        """The storage type token base images declare (a plugin's short
        name for its kind of store). Defaults to the plugin's canonical name."""
        try:
            return str(cls.csis_name())
        except NotImplementedError:             # a base that names no type (stage 30)
            return cls.__name__

    def attachment_cardinality(self) -> str:
        return CARDINALITY_MANY

    def is_zonal(self) -> bool:
        """Whether this storage type lives in ONE availability zone (stage 52).

        A zonal storage constrains where its instance may run, and changing its
        zone REPLACES it. A regional one (a shared filesystem, an object
        store) constrains nothing --
        which is why the compatibility rule is "compatible", not "identical":
        a regional storage and an unset declaration both agree with any zone.
        Regional is the safe default: a plugin that says nothing constrains
        nothing."""
        return False

    def is_posix(self) -> bool:
        """POSIX filesystems realize group access with gid-owned subtrees
        (N13/N15); non-POSIX stores define their own mapping (N3)."""
        return True

    def platform_mounts(self) -> bool:
        """Whether the platform attaches AND mounts this storage before the
        machine's first command (stage 103 branch 2: a container's platform
        mounts its storage at the declared path), so the launch script
        has nothing to format or mount and only makes the group's subtree.
        Default: no -- the launch script mounts a cloud's storage itself."""
        return False

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]:
        """Shell commands baked into a base image that declares this storage
        type (Q1/N10): drivers, agents, mount tooling. Empty = no prerequisites
        (a plain block store), which must still be declared to be usable (N4)."""
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
        builders that do (an object store, a shared filesystem with tiers)
        validate their own keys."""
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

    def retag_storage(self, storage: "Storage", tags: dict[str, str]) -> bool:
        """Add ``tags`` to the storage's cloud resource in place (stage 93:
        `lineage relabel` gives a standing disk, filesystem or bucket
        the configuration's id). False when the resource is absent; a builder
        that cannot retag raises NotImplementedError and relabel says so."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot retag a storage")

    # ------------------------------------------------------- launch hooks
    def launch_mount(self, storage: Any, mapping: Any, index: int) -> dict[str, Any]:
        """The storage-specific keys of an instance's mount record, beside
        the universal ones the core writes (storage, type, builder, mount
        point, group, share mode, public read). A block store answers its
        device name here; ``index`` is how many earlier mounts on the same
        instance have a builder of the same capability type, for a device
        table in declaration order. The record is a launch parameter and so
        immutable after launch: a key added here changes what a launched
        instance compares against. Default: ``platform_mounted`` when the
        platform mounts the storage before the first command, else nothing."""
        return {"platform_mounted": True} if self.platform_mounts() else {}

    def launch_script_lines(self, mount: dict[str, Any], group: str | None) -> list[str]:
        """The mount's WHOLE block of the launch shell script, from the
        ``# mount storage ...`` header to the group's subtree lines. Every
        line is a terraform ``templatefile`` template line: a runtime value
        enters as ``${var["name"].key}`` by reference and shell expansion is
        written ``$${...}``. Default: the header (which makes the mount
        point) and, for a platform-mounted storage, the mount mark and the
        group's subtree -- nothing to format or mount."""
        lines = self.mount_header_lines(mount)
        if mount.get("platform_mounted"):
            lines.append(mount_mark_line(str(mount["mount_point"])))
            lines += self.group_subtree_lines(mount, group)
        return lines

    def launch_tasks(self, mount: dict[str, Any], group: str | None) -> list[dict[str, Any]]:
        """The mount's whole ansible task list, the playbook's counterpart of
        ``launch_script_lines``. Default: the mount-point directory task
        alone."""
        return [self.mount_directory_task(mount)]

    def launch_variables(self) -> tuple[str, ...]:
        """The launch template variables (ansible extra-vars) this storage
        kind's blocks read by reference, each a map ``storage name -> the
        values the instance root binds``. Default: none."""
        return ()

    # ------------------------------------------- the shared launch pieces
    @staticmethod
    def mount_header_lines(mount: dict[str, Any]) -> list[str]:
        """The two lines every mount's block starts with: the header naming
        the storage, its type and the mount point, and the ``mkdir``."""
        mp = mount["mount_point"]
        return [f"# mount storage {mount['storage']} ({mount['type']}) at {mp}", f"mkdir -p '{mp}'"]

    @staticmethod
    def mount_mark_line(mount_point: str) -> str:
        return mount_mark_line(mount_point)

    @staticmethod
    def group_subtree_lines(mount: dict[str, Any], group: str | None) -> list[str]:
        """The per-group private subtree (N13/N15): made, given to the gid
        by reference, and set to the storage's share mode. Empty without a
        group; a storage whose service makes the subtree itself leaves these
        out."""
        if not group:
            return []
        mp = mount["mount_point"]
        return [f"mkdir -p '{mp}/{group}'", f"chgrp \"$GID\" '{mp}/{group}'", f"chmod {mount['share_mode']} '{mp}/{group}'"]

    @staticmethod
    def block_device_lines(mount: dict[str, Any]) -> list[str]:
        """A block store's sequence once ``DEV`` and ``BYID`` are set: wait
        for either name (the attachment lands after boot), format when
        blank, the fstab entry, the mount, the mark."""
        mp = mount["mount_point"]
        return [
            "# the attachment lands after boot: wait for either name",
            'for i in $(seq 1 60); do [ -e "$DEV" ] && break;'
            ' [ -e "$BYID" ] && DEV="$BYID" && break; sleep 2; done',
            'if ! blkid "$DEV" >/dev/null 2>&1; then mkfs -t xfs "$DEV"; fi',
            f"grep -q ' {mp} ' /etc/fstab || echo \"$DEV {mp} xfs defaults,nofail 0 2\" >> /etc/fstab",
            f"mount '{mp}' || mount \"$DEV\" '{mp}'",
            mount_mark_line(mp),
        ]

    @staticmethod
    def fstab_mount_lines(mount: dict[str, Any], entry: str) -> list[str]:
        """A shared filesystem's sequence: the fstab ``entry`` (source, mount
        point, type, options, the two numbers) added once, the mount that
        may fail without failing the script, the mark."""
        mp = mount["mount_point"]
        return [f"grep -q ' {mp} ' /etc/fstab || echo \"{entry}\" >> /etc/fstab",
                f"mount '{mp}' || true",
                mount_mark_line(mp)]

    @staticmethod
    def mount_directory_task(mount: dict[str, Any]) -> dict[str, Any]:
        return {"name": f"mount point {mount['mount_point']} for storage {mount['storage']} ({mount['type']})",
                "ansible.builtin.file": {"path": mount["mount_point"], "state": "directory"}}

    @staticmethod
    def group_subtree_task(mount: dict[str, Any], group: str) -> dict[str, Any]:
        mp = mount["mount_point"]
        return {"name": f"private subtree {mp}/{group} (gid by reference)",
                "ansible.builtin.file": {"path": f"{mp}/{group}", "state": "directory",
                                         "group": "{{ group_gid }}", "mode": str(mount["share_mode"])}}

    @staticmethod
    def block_device_tasks(mount: dict[str, Any], device: str) -> list[dict[str, Any]]:
        """The filesystem and the mount of a block device, as tasks."""
        mp = mount["mount_point"]
        return [{"name": f"filesystem on {device} ({mount['storage']})",
                 "community.general.filesystem": {"fstype": "xfs", "dev": device}},
                {"name": f"mount {device} at {mp}",
                 "ansible.posix.mount": {"path": mp, "src": device, "fstype": "xfs",
                                         "opts": "defaults,nofail", "state": "mounted"}}]
