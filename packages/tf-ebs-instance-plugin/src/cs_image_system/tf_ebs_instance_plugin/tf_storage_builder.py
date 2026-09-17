# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import json
import subprocess
from typing import Any, TypeVar, cast


from cs_image_system.base import utils
from cs_image_system.base.utils import HclRaw, render_module_call
from cs_image_system.base.basic.abstract_version_checker import AbstractVersionChecker
from cs_image_system.base.basic.asset import AssetSet
from cs_image_system.base.basic.builder_base_group import GroupBuilderBase
from cs_image_system.base.basic.builder_base_storage import (
    CARDINALITY_MANY,
    CARDINALITY_SINGLE,
    StorageBuilderBase,
)
from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
from cs_image_system.base.models.executable import ExecutableModel
from cs_image_system.base.models.executable_adds import CFExecutables
from cs_image_system.base.models.storage import STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED, STORAGE_STATE_DESTROYED, Storage
from cs_image_system.hashicorp_utils.blocks import OutputSpec, Raw, render_blocks
from cs_image_system.hashicorp_utils.collector import TerraformCollector
from cs_image_system.hashicorp_utils.roots import TerraformRootMixin

from .tf_storage_models import TF_AWS, TF_AWS_EBS, TF_AWS_EFS, TF_AWS_S3, TofuEbsStorageBuilderModel, TofuEfsStorageBuilderModel, TofuStorageBuilderModel

Q = TypeVar("Q", bound=TofuStorageBuilderModel)


# Duck-typed accessors: unit tests pass minimal storage stand-ins.
def _state(storage: Any) -> str:
    return getattr(storage, "state", "active")


class RecordedStorage:
    """A storage known only from meta-state (its entry left the YAML, TODO
    §10.11): enough of the Storage surface for a whitelist, a wipe and a
    state lookup."""

    def __init__(self, name: str, state: str | None, facts: dict[str, Any]) -> None:
        self.name = name
        self.recorded_state = state
        self.state = STORAGE_STATE_DESTROYED           # what the run requests
        self.type_ = str(facts.get("builder") or "")
        self.bucket_name = facts.get("bucket_name")
        self.groups: list[str] = []
        self.public_read = False
        self.share_mode = "2770"
        self.tags: dict[str, str] = {}
        self.undeclared = True

    def get_name(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"RecordedStorage({self.name!r}, {self.recorded_state!r})"


def _groups(storage: Any) -> list[str]:
    return list(getattr(storage, "groups", []) or [])


def _public_read(storage: Any) -> bool:
    return bool(getattr(storage, "public_read", False))


class TofuStorageBuilder(StorageBuilderBase[Q], TerraformRootMixin):
    """OpenTofu IaC provider implementation.

    Generates one ``module`` call per attached Storage item against the
    corresponding tfmodules/ module, plus a shared terraform/provider file.

    V2 (DESIGN §3E): group access is realized by gid REFERENCE -- the root
    reads the identity workspace's ``group_gids`` output through
    ``data.terraform_remote_state`` and never carries a literal gid; storages
    in requested state ``destroyed`` are omitted (their destruction is the
    only destroy the apply gate whitelists); every storage publishes its
    module outputs for the instance-image lifecycle to bind to.
    """

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS

    def module_dirname(self) -> str:
        """tfmodules/ directory this builder's storages map to."""
        raise NotImplementedError(f"{self.__class__.__name__} must name its terraform module")

    def module_args(self, storage: Storage) -> dict[str, Any]:
        """Module variables for one storage item."""
        raise NotImplementedError

    def _region(self) -> str | None:
        ctx = self._get_context()
        rtb = ctx.runtime_builders.get(self.model.get_runtime_provider(), None)
        get_region = getattr(rtb.model, "get_region", None) if rtb else None
        return str(get_region()) if callable(get_region) else None

    # ------------------------------------------------------------ helpers
    def live_storages(self) -> list[Storage]:
        """Storages emitted as module calls: everything but tombstones -- and,
        on a builder that supports archiving (stage 11.6), everything but
        archived ones too: archived = the live resource is gone, its data
        kept in the builder's archive (a snapshot)."""
        return [s for s in self.model._storages
                if _state(s) != STORAGE_STATE_DESTROYED
                and not (_state(s) == STORAGE_STATE_ARCHIVED and self.supports_archive())]

    def supports_archive(self) -> bool:
        """Whether this builder realizes the `archived` state (snapshot +
        delete, restore from the snapshot). Default: no -- `archived` is then
        a validation error for its storages."""
        return False

    def archived_storages(self) -> list[Storage]:
        return [s for s in self.model._storages if _state(s) == STORAGE_STATE_ARCHIVED]

    def post_transition_actions(self, storage: Storage, from_state: str | None, to_state: str) -> list[ExecutableModel]:
        """Commands the plugin runs AFTER the apply of a transition (TODO
        §11.6): e.g. delete the archive snapshot once the disk was restored
        from it. Default: none."""
        return []

    def tombstones(self) -> list[Storage]:
        return [s for s in self.model._storages if _state(s) == STORAGE_STATE_DESTROYED]

    def undeclared_storages(self) -> list[Any]:
        """Storages this root created that are recorded (not destroyed) but no
        longer declared (stage 10.11): their module call is simply absent, so
        the plan destroys them; the gate whitelists that as the demise. Each
        is a stand-in built from the record's facts (name, bucket)."""
        ctx = self._get_context()
        from cs_image_system.base.storage_state import undeclared_transitions
        out: list[Any] = []
        for t in undeclared_transitions(ctx):
            if t.builder != self.name:
                continue
            facts = (ctx.meta_state.storage_states().get(t.storage) or {}).get("facts") or {}
            out.append(RecordedStorage(t.storage, t.from_state, facts))
        return out

    def _has_work(self) -> bool:
        if not utils.root_in_runtime_scope(self.model.get_runtime_provider()):
            return False                                   # ledger 70: another runtime's root
        return bool(self.model._storages) or bool(self.undeclared_storages())

    @staticmethod
    def storage_label(storage: Storage) -> str:
        return utils.super_safe_name(storage.get_name())

    def _group_builder_for(self, group: str) -> GroupBuilderBase | None:
        ctx = self._get_context()
        for builder in ctx.group_builders.values():
            if any(g.get_name() == group for g in builder.get_groups_for_builder()):
                return builder
        return None

    def identity_workspaces(self) -> dict[str, GroupBuilderBase]:
        """Identity workspaces whose gids this root consumes, by workspace name."""
        out: dict[str, GroupBuilderBase] = {}
        for storage in self.live_storages():
            for group in _groups(storage):
                gb = self._group_builder_for(group)
                if gb is not None:
                    out[gb.get_name()] = gb
        return out

    def gid_reference(self, group: str) -> HclRaw:
        """``data.terraform_remote_state.<identity ws>.outputs.group_gids["<group>"]``
        -- the ONLY way a gid ever appears in generated storage IaC (N7)."""
        gb = self._group_builder_for(group)
        if gb is None:
            raise ValueError(f"Storage builder {self.name}: group {group!r} has no identity builder")
        ws = utils.super_safe_name(gb.get_name())
        return HclRaw(f'data.terraform_remote_state.{ws}.outputs.group_gids["{group}"]')

    def group_subtrees(self, storage: Storage) -> dict[str, dict[str, Any]]:
        """N13/N15: one root-level subtree per allowed group, gid by reference,
        mode from share_mode (2770 private / 2775 read-shared)."""
        return {
            group: {"gid": self.gid_reference(group), "path": f"/{group}",
                    "permissions": getattr(storage, "share_mode", "2770")}
            for group in sorted(_groups(storage))
        }

    def generate_items_before(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        items = AssetSet()
        # the root exists while it declares storages OR still owns undeclared
        # ones whose destroy must be planned (stage 10.11, the finding-52 shape)
        if phase != ExecutionLifecyclePhase.STORAGE_GENERATION or not self._has_work():
            return items
        rpath = self.get_path_for_phase(phase, suffix=".tf")
        items = items.with_default_path(rpath)
        items.add(f"# Terraform configuration for storages generated by "
                  f"{self.__class__.__name__} ({self.name})")
        col = TerraformCollector()
        ws = self.name
        if self.model.required_plugins:
            for plugin in self.model.required_plugins:
                col.require_provider(ws, plugin.name,
                                     source=getattr(plugin, "source", None),
                                     version=getattr(plugin, "version", None))
        else:
            col.require_provider(ws, "aws", source="hashicorp/aws")
        ctx = self._get_context()
        rtb = ctx.runtime_builders.get(self.model.get_runtime_provider(), None)
        region = self._region()
        if region:
            config = {"region": region}
            creds = rtb.model.get_credentials() if rtb else None
            profile = (creds or {}).get("profile_name")
            if profile:
                config["profile"] = profile
            col.configure_provider(ws, "aws", config)
        col.bind_workspace(ws, self.model.state_configuration, self.runtime_state_configuration())   # stage 46: own, runtime's, default
        # gids by reference: the identity workspace's state (applied before
        # storage in meta-workflow order) is read through remote state.
        for identity_ws in sorted(self.identity_workspaces()):
            col.reference_remote_state(ws, producer_workspace=identity_ws)
        items.add_list(col.generate_terraform_block(ws))
        items.add_list(col.generate_provider_blocks(ws))
        remote_lines = col.generate_remote_state_datasources(ws)
        if remote_lines:
            items.add_list(remote_lines)
        backend_lines = col.generate_backend_config(ws)
        if backend_lines:
            items.add_list(self._backend_config_path(phase), backend_lines)
        return items

    def generate_items_during(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        items = AssetSet()
        if phase != ExecutionLifecyclePhase.STORAGE_GENERATION or not self._has_work():
            return items                                    # ledger 70: outside --only-runtime, nothing
        src = utils.module_source(self.module_dirname(),
                                  self.get_path_for_phase(phase, suffix=".tf").parent)
        bindings = TerraformCollector().provider_bindings(self.name)
        for storage in self.live_storages():
            label = self.storage_label(storage)
            rpath = self.get_path_for_phase(phase, f"storage-{label}", suffix=".tf")
            items.add(rpath,
                      f"# Terraform module call for storage {storage.get_name()} "
                      f"generated by {self.__class__.__name__} ({self.name})")
            if _groups(storage):
                items.add(rpath, f"# allowed groups: {', '.join(_groups(storage))} "
                                 f"(gids by remote-state reference); public_read={str(_public_read(storage)).lower()}; "
                                 f"requested state: {_state(storage)}")
            items.add_list(rpath, render_module_call(
                f"storage_{label}", src, self.module_args(storage),
                providers=bindings))
            # Publish the module outputs for the instance-image lifecycle.
            items.add_list(rpath, render_blocks([OutputSpec(
                f"storage_{label}", Raw(f"module.storage_{label}"),
                description=f"Outputs of storage {storage.get_name()} for remote-state consumers")]))
        for storage in self.tombstones():
            label = self.storage_label(storage)
            rpath = self.get_path_for_phase(phase, f"storage-{label}", suffix=".tf")
            items.add(rpath, f"# Storage {storage.get_name()} is DESTROYED (tombstone): its resources are gone; "
                             "nothing is emitted (a re-declared name is a new generation, stage 10.12).")
        if self.supports_archive():
            for storage in self.archived_storages():
                label = self.storage_label(storage)
                rpath = self.get_path_for_phase(phase, f"storage-{label}", suffix=".tf")
                items.add(rpath, f"# Storage {storage.get_name()} is ARCHIVED (stage 11.6): the live resource is "
                                 f"gone, its data is kept in {self.archive_name(storage)}; nothing is emitted.")
        return items

    def archive_name(self, storage: Storage) -> str:
        """The builder's archive object for a storage (a snapshot name)."""
        return f"csis-{self.storage_label(storage).replace('_', '-')}-archive"

    def get_commands_to_run_after(self, phase: ExecutionLifecyclePhase) -> CFExecutables:
        commands: list[ExecutableModel] = []
        deferred: list[ExecutableModel] = []
        if phase == ExecutionLifecyclePhase.STORAGE_GENERATION and self._has_work():
            wd = self.get_path_for_phase(phase, suffix=".tf").parent
            # plan is deliberately not run at generation time: fixture data may
            # reference resources that do not exist yet (e.g. shared EFS ids).
            for cmd in [["fmt"], self._init_args(phase), ["validate"]]:
                e = self.get_executable_copy()
                e.args = cmd
                e.working_directory = wd
                commands.append(e)
            allow: list[str] = []
            after_apply: list[ExecutableModel] = []
            ms = self._get_context().meta_state
            # declared tombstones (state: destroyed) and undeclared storages
            # (their entry left the YAML, stage 10.11) are both a destroy
            # this run executes: plugin action first (wipe), then the
            # whitelisted destroy
            for storage in list(self.tombstones()) + list(self.undeclared_storages()):
                cur = ms.storage_state(storage.get_name())
                if cur is not None and cur != STORAGE_STATE_DESTROYED:
                    deferred.extend(self.transition_actions(storage, cur, STORAGE_STATE_DESTROYED))
                    if cur != STORAGE_STATE_ARCHIVED or not self.supports_archive():
                        allow.extend(self.destroy_whitelist(storage))   # an archived disk is already gone
            # archived (stage 11.6): snapshot first, then the whitelisted destroy
            # of the live resource; a restore (recorded archived, declared
            # active) recreates it from the snapshot and deletes the snapshot
            # after the apply
            if self.supports_archive():
                for storage in self.archived_storages():
                    cur = ms.storage_state(storage.get_name())
                    if cur == STORAGE_STATE_ACTIVE:
                        deferred.extend(self.transition_actions(storage, cur, STORAGE_STATE_ARCHIVED))
                        allow.extend(self.destroy_whitelist(storage))
                for storage in self.live_storages():
                    if ms.storage_state(storage.get_name()) == STORAGE_STATE_ARCHIVED:
                        after_apply.extend(self.post_transition_actions(storage, STORAGE_STATE_ARCHIVED, STORAGE_STATE_ACTIVE))
            # Per-root apply scoping (stage 7): builder name or runtime
            rt = str(self.model.get_runtime_provider())
            apply = utils.apply_enabled("storage", self.name, [rt])
            deferred.extend(self.gated_apply_commands(
                phase, wd, apply=apply, allow_destroy=allow,
                apply_flag_key="storage", apply_root=self.name, apply_root_aliases=[rt]))
            if apply:
                deferred.extend(after_apply)
        return CFExecutables(commands, deferred)

    # ------------------------------------------- AWS CLI transition scripts
    def _aws_cli_flags(self) -> str:
        """``--region … --profile …`` for the runtime's session, as the S3
        wipe passes them (credentials stay in the environment)."""
        ctx = self._get_context()
        rtb = ctx.runtime_builders.get(self.model.get_runtime_provider(), None)
        getter = getattr(getattr(rtb, "model", None), "get_credentials", None)   # stage 17
        creds = (getter() if callable(getter) else None) or {}
        profile = creds.get("profile_name") if isinstance(creds, dict) else None
        profile = profile or getattr(getattr(rtb, "model", None), "profile", None)
        flags = ""
        region = self._region()
        if region:
            flags += f' --region "{region}"'
        if profile:
            flags += f' --profile "{profile}"'
        return flags

    def _script(self, name: str, body: str) -> ExecutableModel:
        """A generated bash script beside the root, run as a deferred step (the
        pd builder's shape, stage 11.6)."""
        wd = self.get_path_for_phase(ExecutionLifecyclePhase.STORAGE_GENERATION, suffix=".tf").parent
        target = self._get_context().generation_path / wd / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/usr/bin/env bash\nset -uo pipefail\n" + body)
        e = ExecutableModel(name="bash", type_="executable", binary="bash")
        e.args = [name]
        e.working_directory = wd
        return e

    # ------------------------------------------------------- state query
    def _aws_client(self, service: str) -> Any:
        from cs_image_system.aws_runtime.aws_utils import aws_client
        ctx = self._get_context()
        rtb = ctx.runtime_builders.get(self.model.get_runtime_provider(), None)
        session: dict[str, Any] = {"region_name": self._region()}
        cfg: Any = getattr(rtb.model, "self_to_aws_client_config", None) if rtb else None
        if callable(cfg):
            session = cast(dict[str, Any], cfg())
        return aws_client(service, session)

    def _lookup(self, storage: Storage) -> dict[str, Any] | None:
        """Provider record for one storage by its ``Name`` tag, or ``None``.
        Subclasses answer per service."""
        raise NotImplementedError

    def query_state(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for storage in list(self.model._storages) + list(self.undeclared_storages()):
            rec = self._lookup(storage)
            out[storage.get_name()] = {"present": rec is not None, "type": self.capability_type(),
                                       **(rec or {})}
        return out

    def destroy_whitelist(self, storage: Storage) -> list[str]:
        return [f"module.storage_{self.storage_label(storage)}"]


R = TypeVar("R", bound=TofuEbsStorageBuilderModel)
class TofuEbsStorageBuilder(TofuStorageBuilder[R]):
    """OpenTofu IaC provider implementation for EBS volumes."""

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_EBS

    @classmethod
    def capability_type(cls) -> str:
        return "ebs"

    def attachment_cardinality(self) -> str:
        # A volume attaches to one instance at a time (the forcing argument of N16).
        return CARDINALITY_SINGLE

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]:
        # No tooling to bake (N4: still must be declared to be used).
        return [f"# storage type 'ebs' declared: no prerequisites to bake ({self.get_name()})"]

    def _lookup(self, storage: Storage) -> dict[str, Any] | None:
        ec2 = self._aws_client("ec2")
        if self._get_context().meta_state.storage_state(storage.get_name()) == STORAGE_STATE_ARCHIVED:
            # archived (stage 15): the volume is expected absent; the archive
            # snapshot -- addressed by its Name tag -- is what must exist
            snaps = ec2.describe_snapshots(OwnerIds=["self"], Filters=[
                {"Name": "tag:Name", "Values": [self.archive_name(storage)]}]).get("Snapshots", [])
            if not snaps:
                return None
            snap = snaps[0]
            return {"id": snap.get("SnapshotId"), "state": "archived", "size": snap.get("VolumeSize"),
                    "archive": snap.get("SnapshotId"), "snapshot_state": snap.get("State"),
                    "tags": {t["Key"]: t["Value"] for t in snap.get("Tags", []) if "Key" in t}}
        vols = ec2.describe_volumes(Filters=[{"Name": "tag:Name", "Values": [storage.get_name()]}]).get("Volumes", [])
        if not vols:
            return None
        v = vols[0]
        return {"id": v.get("VolumeId"), "state": v.get("State"), "size": v.get("Size"),
                "tags": {t["Key"]: t["Value"] for t in v.get("Tags", []) if "Key" in t}}

    def module_dirname(self) -> str:
        return "aws_storage_ebs"

    # ------------------------------------------------ archived (stage 15)
    def supports_archive(self) -> bool:
        return True

    def transition_actions(self, storage: Storage, from_state: str | None,
                           to_state: str) -> list[ExecutableModel]:
        """``active -> archived``: snapshot the volume BEFORE terraform destroys
        it (idempotent: a completed snapshot carrying the archive's Name tag is
        reused); ``archived -> destroyed``: the volume is already gone, the
        archive goes with the demise."""
        name, snap, flags = storage.get_name(), self.archive_name(storage), self._aws_cli_flags()
        label = self.storage_label(storage)
        find_snap = (f'aws ec2 describe-snapshots{flags} --owner-ids self --filters "Name=tag:Name,Values={snap}" '
                     f'--query "Snapshots[].SnapshotId" --output text')
        if to_state == STORAGE_STATE_ARCHIVED and from_state == STORAGE_STATE_ACTIVE:
            return [self._script(f"archive-{label}.sh",
                f'existing=$({find_snap})\n'
                f'if [ -n "$existing" ] && [ "$existing" != "None" ]; then\n'
                f'  echo "archive {snap} already exists: $existing"; '
                f'aws ec2 wait snapshot-completed{flags} --snapshot-ids $existing; exit 0\nfi\n'
                f'vol=$(aws ec2 describe-volumes{flags} --filters "Name=tag:Name,Values={name}" '
                f'--query "Volumes[0].VolumeId" --output text)\n'
                f'if [ -z "$vol" ] || [ "$vol" = "None" ]; then echo "no volume named {name} to archive" >&2; exit 1; fi\n'
                f'snap=$(aws ec2 create-snapshot{flags} --volume-id "$vol" --description "csis archive of {name}" '
                f'--tag-specifications "ResourceType=snapshot,Tags=[{{Key=Name,Value={snap}}},{{Key=csis_storage,Value={name}}}]" '
                f'--query SnapshotId --output text)\n'
                f'echo "archiving {name} ($vol) as {snap} ($snap)"\n'
                f'aws ec2 wait snapshot-completed{flags} --snapshot-ids "$snap"\n')]
        if to_state == STORAGE_STATE_DESTROYED and from_state == STORAGE_STATE_ARCHIVED:
            return [self._script(f"unarchive-{label}.sh",
                f'for s in $({find_snap}); do [ "$s" = "None" ] && continue; '
                f'aws ec2 delete-snapshot{flags} --snapshot-id "$s" && echo "deleted archive $s"; done\ntrue\n')]
        return []

    def post_transition_actions(self, storage: Storage, from_state: str | None,
                                to_state: str) -> list[ExecutableModel]:
        """Restored (archived -> active): the data is on the new volume; the
        archive snapshot is deleted after the apply."""
        snap, flags, label = self.archive_name(storage), self._aws_cli_flags(), self.storage_label(storage)
        if from_state == STORAGE_STATE_ARCHIVED and to_state == STORAGE_STATE_ACTIVE:
            return [self._script(f"restore-{label}.sh",
                f'for s in $(aws ec2 describe-snapshots{flags} --owner-ids self --filters "Name=tag:Name,Values={snap}" '
                f'--query "Snapshots[].SnapshotId" --output text); do [ "$s" = "None" ] && continue; '
                f'aws ec2 delete-snapshot{flags} --snapshot-id "$s" && echo "restored {storage.get_name()}; archive $s deleted"; done\ntrue\n')]
        return []

    def module_args(self, storage: Storage) -> dict[str, Any]:
        # stage 26: declared `variables:` first, then what the item decides
        args: dict[str, Any] = dict(self.model.variables.as_module_args())
        args.update({
            "name": storage.get_name(),
            "size": getattr(self.model, "size", 100),
        })
        # restore (stage 15): recorded archived, declared active -> the volume is
        # created FROM the archive snapshot (looked up by its Name tag at plan
        # time); the module ignores later drift of snapshot_id
        if self._get_context().meta_state.storage_state(storage.get_name()) == STORAGE_STATE_ARCHIVED:
            args["snapshot_name"] = self.archive_name(storage)
        ctx = self._get_context()
        rtb = ctx.runtime_builders.get(self.model.get_runtime_provider(), None)
        networking = getattr(rtb.model, "networking", None) if rtb else None
        az = getattr(networking, "default_availability_zone", None) if networking else None
        if az:
            args["availability_zone"] = az
        else:
            subnet = getattr(networking, "default_subnet_id", None) if networking else None
            if subnet:
                args["subnet_id"] = subnet
        tags = self.model.variables.merged_tags(storage.tags)
        if tags:
            args["tags"] = tags
        return args


S = TypeVar("S", bound=TofuEfsStorageBuilderModel)
class TofuEfsStorageBuilder(TofuStorageBuilder[S]):
    """OpenTofu IaC provider implementation for EFS filesystems."""

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_EFS

    @classmethod
    def capability_type(cls) -> str:
        return "efs"

    def attachment_cardinality(self) -> str:
        return CARDINALITY_MANY

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]:
        fam = (os_family or "").lower()
        pkg = "sudo apt-get -o DPkg::Lock::Timeout=600 install -y nfs-common" if fam in ("debian", "ubuntu") \
            else "sudo yum install -y amazon-efs-utils || sudo yum install -y nfs-utils"
        return [f"# storage type 'efs' prerequisites ({self.get_name()}): NFS/EFS mount tooling", pkg]

    def verify_commands(self, os_family: str | None = None) -> list[str]:
        return ["# verify: EFS/NFS mount tooling present",
                "command -v mount.efs >/dev/null 2>&1 || command -v mount.nfs >/dev/null 2>&1 || command -v mount.nfs4 >/dev/null 2>&1"]

    def _lookup(self, storage: Storage) -> dict[str, Any] | None:
        efs = self._aws_client("efs")
        for fs in efs.describe_file_systems().get("FileSystems", []):
            tags = {t["Key"]: t["Value"] for t in fs.get("Tags", []) if "Key" in t}
            if tags.get("Name") == storage.get_name() or fs.get("Name") == storage.get_name():
                rec: dict[str, Any] = {"id": fs.get("FileSystemId"), "state": fs.get("LifeCycleState"), "tags": tags}
                try:   # observed data lifecycle (stage 15); absent = no policy
                    pol = efs.describe_lifecycle_configuration(FileSystemId=fs.get("FileSystemId")).get("LifecyclePolicies", [])
                    rec["lifecycle"] = {k: v for p in pol for k, v in p.items()} if pol else {}
                except Exception:  # noqa: BLE001 - informational; presence is the claim
                    pass
                return rec
        return None

    def module_dirname(self) -> str:
        return "aws_storage_efs"

    # ------------------------------------------ data lifecycle (stage 15)
    IA_DAYS = (1, 7, 14, 30, 60, 90, 180, 270, 365)
    ARCHIVE_DAYS = (90, 180, 270, 365)

    def validate_lifecycle(self, storage: Storage) -> list[str]:
        spec = getattr(storage, "lifecycle", None)
        if not spec:
            return []
        errors: list[str] = []
        if not isinstance(spec, dict):
            return [f"storage '{storage.get_name()}': lifecycle must be a map"]
        unknown = sorted(set(spec) - {"ia_days", "archive_days"})
        if unknown:
            errors.append(f"storage '{storage.get_name()}': unknown lifecycle keys {unknown} (efs: ia_days, archive_days)")
        for key, allowed in (("ia_days", self.IA_DAYS), ("archive_days", self.ARCHIVE_DAYS)):
            v = spec.get(key)
            if v is not None and v not in allowed:
                errors.append(f"storage '{storage.get_name()}': lifecycle.{key} must be one of {list(allowed)}, got {v!r}")
        return errors

    def module_args(self, storage: Storage) -> dict[str, Any]:
        args: dict[str, Any] = dict(self.model.variables.as_module_args())   # stage 26
        args["name"] = storage.get_name()
        existing = storage.config.get("file_system_id")
        if existing:
            args["existing_file_system_id"] = existing
        spec = getattr(storage, "lifecycle", None) or {}
        if spec.get("ia_days"):
            args["transition_to_ia"] = f"AFTER_{int(spec['ia_days'])}_DAYS"
        if spec.get("archive_days"):
            args["transition_to_archive"] = f"AFTER_{int(spec['archive_days'])}_DAYS"
        if _groups(storage):
            # EFS access points realize gid-owned subtrees natively (Q3).
            args["access_points"] = self.group_subtrees(storage)
        if _public_read(storage):
            args["public_read"] = True
        tags = self.model.variables.merged_tags(storage.tags)
        if tags:
            args["tags"] = tags
        return args


class TofuS3StorageBuilder(TofuStorageBuilder[Q]):
    """OpenTofu IaC provider implementation for S3 buckets."""

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_S3

    @classmethod
    def capability_type(cls) -> str:
        return "s3"

    def attachment_cardinality(self) -> str:
        return CARDINALITY_MANY

    def is_posix(self) -> bool:
        # Object store: "readable by all" maps to a same-account read policy
        # (plugin-owned semantics, N3); groups map to per-group prefixes (N13).
        return False

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]:
        fam = (os_family or "").lower()
        tooling = ("sudo apt-get -o DPkg::Lock::Timeout=600 install -y curl unzip" if fam in ("debian", "ubuntu")
                   else "sudo yum install -y unzip")   # curl ships on RHEL; unzip does not (found live)
        return [f"# storage type 's3' prerequisites ({self.get_name()}): AWS CLI for object access",
                f"command -v aws >/dev/null 2>&1 || {{ command -v unzip >/dev/null 2>&1 || {tooling}; "
                "curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscliv2.zip && "
                "cd /tmp && unzip -q awscliv2.zip && sudo ./aws/install; }"]

    def verify_commands(self, os_family: str | None = None) -> list[str]:
        return ["# verify: AWS CLI present", "command -v aws >/dev/null 2>&1"]

    def _lookup(self, storage: Storage) -> dict[str, Any] | None:
        s3 = self._aws_client("s3")
        bucket = getattr(self.model, "bucket_name", None)
        if not bucket:
            return None
        # The bucket_name binding already scopes this lookup to one bucket, so
        # presence = the bucket is reachable (found live: our own bucket read
        # as HARD-missing because the module sets no Name tag).
        tags: dict[str, str] = {}
        try:
            tagset = s3.get_bucket_tagging(Bucket=bucket).get("TagSet", [])
            tags = {t["Key"]: t["Value"] for t in tagset if "Key" in t}
        except Exception as e:
            # Only "not there" means absent; a permission or transport failure
            # must surface as *unavailable*, never as a false "missing".
            code = str(getattr(e, "response", {}).get("Error", {}).get("Code", "")) if hasattr(e, "response") else ""
            if code in ("NoSuchBucket", "404"):
                return None
            if code not in ("NoSuchTagSet",):
                raise
        rec: dict[str, Any] = {"id": bucket, "state": "active", "tags": tags}
        try:   # observed data lifecycle (stage 15); absent = no rules
            rules = s3.get_bucket_lifecycle_configuration(Bucket=bucket).get("Rules", [])
            rec["lifecycle"] = {"rules": [str(r.get("ID") or "") for r in rules]} if rules else {}
        except Exception as e:  # noqa: BLE001
            code = str(getattr(e, "response", {}).get("Error", {}).get("Code", "")) if hasattr(e, "response") else ""
            if code == "NoSuchLifecycleConfiguration":
                rec["lifecycle"] = {}
        return rec

    def module_dirname(self) -> str:
        return "aws_storage_s3"

    # ------------------------------------------ data lifecycle (stage 15)
    STORAGE_CLASSES = ("STANDARD_IA", "ONEZONE_IA", "INTELLIGENT_TIERING", "GLACIER_IR", "GLACIER", "DEEP_ARCHIVE")

    def validate_lifecycle(self, storage: Storage) -> list[str]:
        spec = getattr(storage, "lifecycle", None)
        if not spec:
            return []
        if not isinstance(spec, dict):
            return [f"storage '{storage.get_name()}': lifecycle must be a map"]
        errors: list[str] = []
        unknown = sorted(set(spec) - {"transition_days", "storage_class", "expire_days", "prefix"})
        if unknown:
            errors.append(f"storage '{storage.get_name()}': unknown lifecycle keys {unknown} "
                          "(s3: transition_days, storage_class, expire_days, prefix)")
        for key in ("transition_days", "expire_days"):
            v = spec.get(key)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v <= 0):
                errors.append(f"storage '{storage.get_name()}': lifecycle.{key} must be a positive int, got {v!r}")
        if spec.get("transition_days") and spec.get("storage_class") not in self.STORAGE_CLASSES:
            errors.append(f"storage '{storage.get_name()}': lifecycle.storage_class must be one of "
                          f"{list(self.STORAGE_CLASSES)}, got {spec.get('storage_class')!r}")
        if spec.get("storage_class") and not spec.get("transition_days"):
            errors.append(f"storage '{storage.get_name()}': lifecycle.storage_class needs transition_days")
        if not spec.get("transition_days") and not spec.get("expire_days"):
            errors.append(f"storage '{storage.get_name()}': lifecycle declares neither transition_days nor expire_days")
        return errors

    def module_args(self, storage: Storage) -> dict[str, Any]:
        args: dict[str, Any] = dict(self.model.variables.as_module_args())   # stage 26
        args["bucket_name"] = storage.bucket_name or storage.get_name()
        spec = getattr(storage, "lifecycle", None) or {}
        if spec:
            args["lifecycle_rules"] = [{
                "id": "csis", "prefix": str(spec.get("prefix") or ""),
                "transition_days": int(spec.get("transition_days") or 0),
                "storage_class": str(spec.get("storage_class") or ""),
                "expire_days": int(spec.get("expire_days") or 0)}]
        if _groups(storage):
            args["group_prefixes"] = sorted(_groups(storage))
        if _public_read(storage):
            args["public_read"] = True
        tags = self.model.variables.merged_tags(storage.tags)
        if tags:
            args["tags"] = tags
        return args

    def transition_actions(self, storage: Storage, from_state: str | None,
                           to_state: str) -> list[ExecutableModel]:
        """``destroyed`` wipes the bucket clean before terraform removes it
        (N19: "wiped clean"); other transitions need no bucket-level action."""
        if to_state != STORAGE_STATE_DESTROYED:
            return []
        ctx = self._get_context()
        rtb = ctx.runtime_builders.get(self.model.get_runtime_provider(), None)
        creds = rtb.model.get_credentials() if rtb else None
        profile = (creds or {}).get("profile_name")
        bucket = storage.bucket_name or storage.get_name()
        args = ["s3", "rm", f"s3://{bucket}", "--recursive"]
        if profile:
            args += ["--profile", profile]
        e = ExecutableModel(name="aws", type_="executable", binary="aws")
        e.args = args
        e.working_directory = self.get_path_for_phase(
            ExecutionLifecyclePhase.STORAGE_GENERATION, suffix=".tf").parent
        return [e]


class TofuStorageVersionChecker(AbstractVersionChecker):
    """Version checker for OpenTofu."""

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS

    def get_version_params(self) -> list[str]:
        return ["--version", "-json"]

    def get_extracted_string(self, res: subprocess.CompletedProcess[str]) -> str | None:
        return json.loads(res.stdout.strip()).get("terraform_version", None)
