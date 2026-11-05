# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The AWS storage roots: the provider-neutral storage root of
hashicorp-utils with the ``aws`` provider, and one subclass per service --
EBS volumes, EFS filesystems and S3 buckets -- each against its
tfmodules/ module, looked up and re-tagged through the runtime's boto3
session and archived or wiped by generated AWS CLI scripts.
"""
import json
import subprocess
from typing import Any, TypeVar, cast

from cs_image_system.base.basic.abstract_version_checker import AbstractVersionChecker
from cs_image_system.base.basic.builder_base_storage import CARDINALITY_MANY, CARDINALITY_SINGLE
from cs_image_system.base.models.executable import ExecutableModel
from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
from cs_image_system.contract.operating_system import PACKAGE_LOCK_TIMEOUT
from cs_image_system.base.models.storage import STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED, STORAGE_STATE_DESTROYED, Storage
from cs_image_system.tofu_roots.tofu_storage_builder import (
    RecordedStorage,
    TofuStorageBuilderBase,
    storage_groups,
    storage_public_read,
)

from .tf_storage_models import (
    TF_AWS, TF_AWS_EBS, TF_AWS_EFS, TF_AWS_S3,
    TofuEbsStorageBuilderModel, TofuEfsStorageBuilderModel, TofuS3StorageBuilderModel, TofuStorageBuilderModel,
)
from cs_image_system.aws_runtime.aws_utils import aws_client
from cs_image_system.base.lineage import config_tags, belongs_to_another_configuration, owner_of
from cs_image_system.base.os_types import os_type_for_family

__all__ = [
    "EBS_DEVICES", "RecordedStorage", "TofuEbsStorageBuilder", "TofuEfsStorageBuilder", "TofuS3StorageBuilder",
    "TofuStorageBuilder", "TofuStorageVersionChecker", "storage_groups", "storage_public_read",
]

Q = TypeVar("Q", bound=TofuStorageBuilderModel)

#: Device names handed to EBS attachments in declaration order; the
#: seventh volume onwards continues the alphabet (``/dev/xvdl``...).
EBS_DEVICES = ["/dev/xvdf", "/dev/xvdg", "/dev/xvdh", "/dev/xvdi", "/dev/xvdj", "/dev/xvdk"]


def ebs_device(index: int) -> str:
    """The device name of an instance's ``index``-th EBS mount (0-based)."""
    if index < len(EBS_DEVICES):
        return EBS_DEVICES[index]
    return f"/dev/xvd{chr(ord('l') + index - len(EBS_DEVICES))}"


class TofuStorageBuilder(TofuStorageBuilderBase[Q]):
    """The AWS storage root (``type: tf-aws`` is the shared base of the three
    services and emits nothing of its own); see the module docstring."""

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS

    # ------------------------------------------------------------ the hooks
    def _provider_name(self) -> str:
        return "aws"

    def _provider_source(self) -> str:
        return "hashicorp/aws"

    def _provider_config(self, rtb: Any) -> dict[str, Any] | None:
        """The region and, when the runtime names one, the profile; no
        provider block without a region."""
        region = self._region()
        if not region:
            return None
        config: dict[str, Any] = {"region": region}
        creds = rtb.model.get_credentials() if rtb else None
        profile = (creds or {}).get("profile_name")
        if profile:
            config["profile"] = profile
        return config

    def _region(self) -> str | None:
        ctx = self._get_context()
        rtb = ctx.runtime_builders.get(self.model.get_runtime_provider(), None)
        get_region = getattr(rtb.model, "get_region", None) if rtb else None
        return str(get_region()) if callable(get_region) else None

    # ------------------------------------------- AWS CLI transition scripts
    def _aws_cli_flags(self) -> str:
        """``--region … --profile …`` for the runtime's session, as the S3
        wipe passes them (credentials stay in the environment)."""
        ctx = self._get_context()
        rtb = ctx.runtime_builders.get(self.model.get_runtime_provider(), None)
        getter = getattr(getattr(rtb, "model", None), "get_credentials", None)
        creds = (getter() if callable(getter) else None) or {}
        profile = creds.get("profile_name") if isinstance(creds, dict) else None
        flags = ""
        region = self._region()
        if region:
            flags += f' --region "{region}"'
        if profile:
            flags += f' --profile "{profile}"'
        return flags

    # ------------------------------------------------------- state query
    def _aws_client(self, service: str) -> Any:
        ctx = self._get_context()
        rtb = ctx.runtime_builders.get(self.model.get_runtime_provider(), None)
        session: dict[str, Any] = {"region_name": self._region()}
        cfg: Any = getattr(rtb.model, "self_to_aws_client_config", None) if rtb else None
        if callable(cfg):
            session = cast(dict[str, Any], cfg())
        return aws_client(service, session)


def _tags_for(builder: Any, storage: Storage) -> dict[str, str]:
    """The tags a storage's module call carries: the builder's defaults
    under the item's own, and the configuration's id last. A stand-in
    without a context (the module-call tests) gets no id."""
    merged = dict(builder.model.variables.merged_tags(storage.tags) or {})
    get_ctx: Any = getattr(builder, "_get_context", None)
    if callable(get_ctx):
        merged.update(config_tags(cast(Any, get_ctx())))
    return merged


R = TypeVar("R", bound=TofuEbsStorageBuilderModel)
class TofuEbsStorageBuilder(TofuStorageBuilder[R]):
    """OpenTofu IaC provider implementation for EBS volumes."""

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_EBS

    @classmethod
    def capability_type(cls) -> str:
        return "ebs"

    def is_zonal(self) -> bool:
        return True     # stage 52: an EBS volume lives in one zone; changing it replaces the volume

    def attachment_cardinality(self) -> str:
        # A volume attaches to one instance at a time (the forcing argument of N16).
        return CARDINALITY_SINGLE

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]:
        # No tooling to bake (N4: still must be declared to be used).
        return [f"# storage type 'ebs' declared: no prerequisites to bake ({self.get_name()})"]

    # ------------------------------------------------------- launch hooks
    def launch_mount(self, storage: Storage, mapping: Any, index: int) -> dict[str, Any]:
        """The device the volume is attached under: ``/dev/xvdf`` onwards in
        declaration order; the instance root attaches with the same name."""
        return {"device": ebs_device(index)}

    def launch_script_lines(self, mount: dict[str, Any], group: str | None) -> list[str]:
        """Wait for the device, format it when blank, mount it, make the
        group's subtree. On Nitro instances (t3 and later) EBS volumes
        surface as ``/dev/nvme*`` and RHEL-family vendor images create no
        legacy symlinks (found live: user-data died at mkfs and everything
        after never ran), so the block waits for the legacy name OR the
        stable by-id name built from the volume id, which the root passes
        by reference as ``ebs["<storage>"].volume_id``."""
        name = mount["storage"]
        return [
            *self.mount_header_lines(mount),
            f"DEV='{mount['device']}'",
            f"VOL=\"${{ebs[\"{name}\"].volume_id}}\"",
            "BYID=\"/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_$(printf '%s' \"$VOL\" | tr -d -)\"",
            *self.block_device_lines(mount),
            *self.group_subtree_lines(mount, group),
        ]

    def launch_tasks(self, mount: dict[str, Any], group: str | None) -> list[dict[str, Any]]:
        tasks = [self.mount_directory_task(mount), *self.block_device_tasks(mount, str(mount["device"]))]
        if group:
            tasks.append(self.group_subtree_task(mount, group))
        return tasks

    def launch_variables(self) -> tuple[str, ...]:
        return ("ebs",)

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
        tags_of = lambda v: {t["Key"]: t["Value"] for t in v.get("Tags", []) if "Key" in t}  # noqa: E731
        vols, elsewhere = self._owned(vols, tags_of)     # stage 93: another configuration's `data` is not ours
        if not vols:
            return self._elsewhere(elsewhere, "an EBS volume") if elsewhere else None
        v = vols[0]
        return {"id": v.get("VolumeId"), "state": v.get("State"), "size": v.get("Size"), "tags": tags_of(v)}

    def module_dirname(self) -> str:
        return "aws_storage_ebs"

    def retag_storage(self, storage: Storage, tags: dict[str, str]) -> bool:
        rec = self._lookup(storage)
        if not rec or not rec.get("present", True) or not rec.get("id"):
            return False
        self._aws_client("ec2").create_tags(Resources=[str(rec["id"])],
                                            Tags=[{"Key": k, "Value": str(v)} for k, v in tags.items()])
        return True

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
        # stage 52: the storage's OWN zone wins, then the runtime's, and only
        # then the subnet the module derives one from. A declared zone has to
        # pin, or declaring it would decorate the configuration without
        # changing where the volume goes -- and validate would be checking a
        # value the emission ignores.
        az = (getattr(storage, "availability_zone", None)
              or (getattr(networking, "default_availability_zone", None) if networking else None))
        if az:
            args["availability_zone"] = az
        else:
            subnet = getattr(networking, "default_subnet_id", None) if networking else None
            if subnet:
                args["subnet_id"] = subnet
        tags = _tags_for(self, storage)
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
        # the packages that carry an NFS client per package format (the
        # EFS helper exists only as an rpm, and only on Amazon's own
        # distribution: the plain NFS client is the fallback); the lines are the OS type's
        os_type = os_type_for_family(os_family)
        packages = {"deb": ["nfs-common"], "rpm": ["amazon-efs-utils", "nfs-utils"], "apk": ["nfs-utils"]}
        pkg = " || ".join(os_type.package_install_command([p], lock_timeout=PACKAGE_LOCK_TIMEOUT)
                          for p in packages[os_type.package_format()])
        return [f"# storage type 'efs' prerequisites ({self.get_name()}): NFS/EFS mount tooling", pkg]

    def verify_commands(self, os_family: str | None = None) -> list[str]:
        return ["# verify: EFS/NFS mount tooling present",
                "command -v mount.efs >/dev/null 2>&1 || command -v mount.nfs >/dev/null 2>&1 || command -v mount.nfs4 >/dev/null 2>&1"]

    # ------------------------------------------------------- launch hooks
    def launch_script_lines(self, mount: dict[str, Any], group: str | None) -> list[str]:
        """Mount the filesystem through the group's access point (both ids by
        reference as ``efs["<storage>"]``), TLS on. No subtree lines: the
        access point creates the group's subtree itself (Q3)."""
        name, mp = mount["storage"], mount["mount_point"]
        return [
            *self.mount_header_lines(mount),
            f"EFS_ID=\"${{efs[\"{name}\"].file_system_id}}\"",
            f"EFS_AP=\"${{efs[\"{name}\"].access_point_id}}\"",
            *self.fstab_mount_lines(mount, f"$EFS_ID:/ {mp} efs _netdev,tls,accesspoint=$EFS_AP,nofail 0 0"),
        ]

    def launch_tasks(self, mount: dict[str, Any], group: str | None) -> list[dict[str, Any]]:
        name, mp = mount["storage"], mount["mount_point"]
        return [self.mount_directory_task(mount),
                {"name": f"mount EFS {name} at {mp}",
                 "ansible.posix.mount": {
                     "path": mp, "fstype": "efs",
                     "src": "{{ efs['" + name + "'].file_system_id }}:/",
                     "opts": "_netdev,tls,accesspoint={{ efs['" + name + "'].access_point_id }},nofail",
                     "state": "mounted"}}]

    def launch_variables(self) -> tuple[str, ...]:
        return ("efs",)

    def _lookup(self, storage: Storage) -> dict[str, Any] | None:
        efs = self._aws_client("efs")
        tags_of = lambda fs: {t["Key"]: t["Value"] for t in fs.get("Tags", []) if "Key" in t}  # noqa: E731
        named = [fs for fs in efs.describe_file_systems().get("FileSystems", [])
                 if tags_of(fs).get("Name") == storage.get_name() or fs.get("Name") == storage.get_name()]
        named, elsewhere = self._owned(named, tags_of)       # stage 93
        if not named and elsewhere:
            return self._elsewhere(elsewhere, "an EFS filesystem")
        for fs in named:
            tags = tags_of(fs)
            if True:
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

    def retag_storage(self, storage: Storage, tags: dict[str, str]) -> bool:
        rec = self._lookup(storage)
        if not rec or not rec.get("present", True) or not rec.get("id"):
            return False
        self._aws_client("efs").tag_resource(ResourceId=str(rec["id"]),
                                             Tags=[{"Key": k, "Value": str(v)} for k, v in tags.items()])
        return True

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
        if storage_groups(storage):
            # EFS access points realize gid-owned subtrees natively (Q3).
            args["access_points"] = self.group_subtrees(storage)
        if storage_public_read(storage):
            args["public_read"] = True
        # Mount targets (stage 19): an EFS filesystem is reachable only through
        # an ENI in the VPC, one per availability zone, and without them
        # `mount.efs` cannot resolve the filesystem at all. Only the PRIVATE
        # subnets are named: EFS permits one mount target per zone, and the
        # public subnets of this VPC share the zones the private ones use.
        # The clients are named as security GROUPS, so the module grants NFS by
        # reference and opens no CIDR -- the standing rule for a shared network.
        rtb = self._get_context().runtime_builders.get(self.model.get_runtime_provider(), None)
        networking = getattr(rtb.model, "networking", None) if rtb else None
        if networking is not None:
            seen: set[str] = set()
            subnets: list[str] = []
            for subnet in getattr(networking, "subnets", None) or []:
                zone = subnet.get_availability_zone() or subnet.get_subnet_id()
                if subnet.get_public() or zone in seen:
                    continue
                seen.add(zone)
                subnets.append(subnet.get_subnet_id())
            clients = [str(sg) for sg in getattr(networking, "addl_security_groups", None) or []]
            if subnets and clients:
                args["vpc_id"] = networking.network
                args["mount_target_subnet_ids"] = subnets
                args["client_security_group_ids"] = clients
        tags = _tags_for(self, storage)
        if tags:
            args["tags"] = tags
        return args


B = TypeVar("B", bound=TofuS3StorageBuilderModel)
class TofuS3StorageBuilder(TofuStorageBuilder[B]):
    """OpenTofu IaC provider implementation for S3 buckets."""

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_S3

    @classmethod
    def capability_type(cls) -> str:
        return "s3"

    def attachment_cardinality(self) -> str:
        return CARDINALITY_MANY

    def _bucket_for(self, storage: Storage) -> str:
        """The bucket a storage lives in, one rule for the module call, the
        state lookup and the wipe (stage 67): the storage's own `bucket_name`,
        else the BUILDER's `bucket_name` (the default for storages that name
        none; since stage 63 it was read by nothing), else the storage's name."""
        return (getattr(storage, "bucket_name", None) or getattr(self.model, "bucket_name", None)
                or storage.get_name())

    def is_posix(self) -> bool:
        # Object store: "readable by all" maps to a same-account read policy
        # (plugin-owned semantics, N3); groups map to per-group prefixes (N13).
        return False

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]:
        # what the CLI's installer needs per package format: curl ships on
        # the rpm families, not on the deb or apk ones; unzip on none (found live)
        os_type = os_type_for_family(os_family)
        needed = {"deb": ["curl", "unzip"], "rpm": ["unzip"], "apk": ["curl", "unzip"]}
        tooling = os_type.package_install_command(needed[os_type.package_format()], lock_timeout=PACKAGE_LOCK_TIMEOUT)
        return [f"# storage type 's3' prerequisites ({self.get_name()}): AWS CLI for object access",
                f"command -v aws >/dev/null 2>&1 || {{ command -v unzip >/dev/null 2>&1 || {tooling}; "
                "curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscliv2.zip && "
                "cd /tmp && unzip -q awscliv2.zip && sudo ./aws/install; }"]

    def verify_commands(self, os_family: str | None = None) -> list[str]:
        return ["# verify: AWS CLI present", "command -v aws >/dev/null 2>&1"]

    # ------------------------------------------------------- launch hooks
    def launch_script_lines(self, mount: dict[str, Any], group: str | None) -> list[str]:
        """An object store is reached through the AWS CLI: the mount point
        is made and a comment says there is no mount (and no mark)."""
        return [*self.mount_header_lines(mount),
                f"# s3 storage {mount['storage']}: object access via the cloud CLI; no mount"]

    def launch_tasks(self, mount: dict[str, Any], group: str | None) -> list[dict[str, Any]]:
        name = mount["storage"]
        return [{"name": f"storage {name} (s3): object access via the cloud's CLI, no mount",
                 "ansible.builtin.debug": {"msg": f"s3 storage {name} is not mounted"}}]

    def _lookup(self, storage: Storage) -> dict[str, Any] | None:
        s3 = self._aws_client("s3")
        # stage 63: the STORAGE's bucket, the one its module call creates
        # (bucket_name, else the storage's name); the builder's bucket_name
        # made two S3 storages on one builder report the same bucket
        bucket = self._bucket_for(storage)
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
        if belongs_to_another_configuration(self._get_context(), tags):
            return self._elsewhere(owner_of(tags), "an S3 bucket")      # stage 93: the name is theirs
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

    def retag_storage(self, storage: Storage, tags: dict[str, str]) -> bool:
        rec = self._lookup(storage)
        if not rec or not rec.get("present", True):
            return False
        merged = {**(rec.get("tags") or {}), **{k: str(v) for k, v in tags.items()}}   # a bucket's tag set is replaced whole
        self._aws_client("s3").put_bucket_tagging(Bucket=self._bucket_for(storage),
                                                  Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in merged.items()]})
        return True

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
        args["bucket_name"] = self._bucket_for(storage)
        spec = getattr(storage, "lifecycle", None) or {}
        if spec:
            args["lifecycle_rules"] = [{
                "id": "csis", "prefix": str(spec.get("prefix") or ""),
                "transition_days": int(spec.get("transition_days") or 0),
                "storage_class": str(spec.get("storage_class") or ""),
                "expire_days": int(spec.get("expire_days") or 0)}]
        if storage_groups(storage):
            args["group_prefixes"] = sorted(storage_groups(storage))
        if storage_public_read(storage):
            args["public_read"] = True
        tags = _tags_for(self, storage)
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
        bucket = self._bucket_for(storage)
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
