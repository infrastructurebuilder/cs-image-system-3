# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins module args and HCL rendering for the tf-aws storage builders."""
from types import SimpleNamespace
from typing import Any, cast

from cs_image_system.base.utils import render_module_call
from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import (
    TofuEfsStorageBuilder,
    TofuS3StorageBuilder,
)
from cs_image_system.tf_ebs_instance_plugin.tf_storage_models import (
    EbsVariables,
    EfsVariables,
    S3Variables,
    TofuEbsStorageBuilderModel,
)


def _subnet(name, subnet_id, zone, public=False) -> Any:
    return SimpleNamespace(get_name=lambda: name, get_subnet_id=lambda: subnet_id,
                           get_availability_zone=lambda: zone, get_public=lambda: public)


def _builder(variables=None, networking=None) -> Any:
    """A builder stand-in: ``module_args`` reads ``self.model.variables`` (stage 26)
    and, for EFS mount targets, the runtime's networking (stage 19)."""
    model = SimpleNamespace(variables=variables or EfsVariables(),
                            get_runtime_provider=lambda: "aws")
    rtb = SimpleNamespace(model=SimpleNamespace(networking=networking)) if networking else None
    ctx = SimpleNamespace(runtime_builders={"aws": rtb} if rtb else {})
    stub = SimpleNamespace(model=model, _get_context=lambda: ctx)
    # stage 67: the S3 module call asks the builder for the storage's bucket
    # (the storage's, else the builder's, else the name); this stub's model
    # names none, so the storage decides
    stub._bucket_for = lambda storage: TofuS3StorageBuilder._bucket_for(cast(Any, stub), storage)
    return stub


def _storage(name, *, tags=None, config=None, bucket_name=None) -> Any:
    return SimpleNamespace(
        get_name=lambda: name,
        tags=tags or {},
        config=config or {},
        bucket_name=bucket_name,
    )


def test_render_module_call_value_kinds():
    lines = render_module_call("m", "SRC", {
        "a_str": "plain",
        "a_ref": "module.other.id",
        "a_bool": True,
        "a_num": 42,
        "a_map": {"k": "v"},
    })
    hcl = "\n".join(lines)
    assert 'module "m" {' in hcl and hcl.endswith("}")
    assert 'source = "SRC"' in hcl
    assert 'a_str = "plain"' in hcl
    assert "a_ref = module.other.id" in hcl
    assert "a_bool = true" in hcl
    assert "a_num = 42" in hcl
    assert 'a_map = { "k" = "v" }' in hcl


def test_render_module_call_providers_meta_argument():
    lines = render_module_call("m", "SRC", {"name": "x"},
                               providers={"aws": "aws.open_tofu"})
    hcl = "\n".join(lines)
    # raw references on both sides, right after source
    assert "providers = { aws = aws.open_tofu }" in hcl
    assert hcl.index("source") < hcl.index("providers")


def test_s3_module_args_prefer_bucket_name():
    args = TofuS3StorageBuilder.module_args(
        cast(Any, _builder()), _storage("default-bucket", bucket_name="my-image-bucket",
                                    tags={"env": "production"}))
    assert args == {"bucket_name": "my-image-bucket", "tags": {"env": "production"}}


def test_s3_module_args_fall_back_to_storage_name():
    args = TofuS3StorageBuilder.module_args(cast(Any, _builder()), _storage("plain"))
    assert args == {"bucket_name": "plain"}


def test_efs_module_args_pass_existing_filesystem():
    args = TofuEfsStorageBuilder.module_args(
        cast(Any, _builder()), _storage("efs-storage", config={"file_system_id": "fs-12345678"}))
    assert args == {"name": "efs-storage", "existing_file_system_id": "fs-12345678"}


# ------------------------------------------------- variables (stage 26)

def test_declared_variables_reach_the_module_call_and_the_item_wins():
    """A builder's ``variables:`` are module inputs; what the item decides
    (name, existing filesystem, groups) is never overridden by them."""
    args = TofuEfsStorageBuilder.module_args(
        cast(Any, _builder(EfsVariables(performance_mode="maxIO", encrypted=True))),
        _storage("efs-storage", config={"file_system_id": "fs-1"}))
    assert args["performance_mode"] == "maxIO" and args["encrypted"] is True
    assert args["name"] == "efs-storage" and args["existing_file_system_id"] == "fs-1"


def test_undeclared_variables_are_absent_so_the_module_default_applies():
    args = TofuS3StorageBuilder.module_args(cast(Any, _builder(S3Variables())), _storage("b"))
    assert "force_destroy" not in args and "tags" not in args


def test_tags_merge_with_the_items_over_the_builders():
    args = TofuS3StorageBuilder.module_args(
        cast(Any, _builder(S3Variables(tags={"Project": "P", "env": "builder"}))),
        _storage("b", tags={"env": "item"}))
    assert args["tags"] == {"Project": "P", "env": "item"}


def test_variables_are_typed_per_provider():
    """The module's own variable names, exactly: the fixture's old
    `performance-mode` (hyphen) is refused rather than silently dropped."""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="performance-mode"):
        EfsVariables(**{"performance-mode": "generalPurpose"})   # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        EbsVariables(**{"size": 8})   # type: ignore[arg-type]   size is the builder's own field


def test_parameters_is_refused_with_the_replacement_named():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="retired .stage 26.*variables"):
        TofuEbsStorageBuilderModel(name="aws-ebs", type_="tf-aws-ebs", runtime="r",
                                   parameters={"volume_type": "gp2"})   # type: ignore[call-arg]


def test_efs_mount_targets_reach_the_module_by_private_subnet_and_group(_=None):
    """Stage 19: an EFS filesystem is unreachable without a mount target -- an
    ENI per availability zone -- which this module never made, so nothing in the
    account could mount EFS until 2026-09-20.

    One subnet per ZONE (EFS permits a single mount target each), PRIVATE only
    (the public subnets of this VPC share those zones), and the clients are
    named as security GROUPS so NFS is granted by reference and no CIDR of a
    shared network is opened."""
    networking = SimpleNamespace(
        network="vpc-123",
        addl_security_groups=["sg-clients"],
        subnets=[_subnet("az1-private", "subnet-a", "us-east-2a"),
                 _subnet("az2-private", "subnet-b", "us-east-2b"),
                 _subnet("az1-public", "subnet-c", "us-east-2a", public=True),
                 _subnet("az2-extra", "subnet-d", "us-east-2b")],
    )
    args = TofuEfsStorageBuilder.module_args(_builder(networking=networking), _storage("share"))
    assert args["vpc_id"] == "vpc-123"
    assert args["mount_target_subnet_ids"] == ["subnet-a", "subnet-b"], \
        "one per zone, private only -- a second in a zone is refused by EFS"
    assert args["client_security_group_ids"] == ["sg-clients"]
    assert not any("cidr" in str(k).lower() for k in args), "never a CIDR on a shared network"


def test_efs_without_networking_asks_for_no_mount_targets(_=None):
    """A runtime that declares no networking gets no mount target arguments,
    so the module's counts collapse to zero rather than half-configuring one."""
    args = TofuEfsStorageBuilder.module_args(_builder(), _storage("share"))
    for key in ("vpc_id", "mount_target_subnet_ids", "client_security_group_ids"):
        assert key not in args


# ------------------------------------------------- the launch hooks (device and mount lines)

def _mount(name, mp, stype, **extra) -> dict:
    return {"storage": name, "type": stype, "builder": f"aws-{stype}", "mount_point": mp,
            "group": "coops", "share_mode": "2770", "public_read": False, **extra}


def _hooks(cls) -> Any:
    """A builder with no model: the launch hooks read only the mount record."""
    return object.__new__(cls)


def test_the_ebs_builder_owns_the_device_table_and_the_nvme_fallback():
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuEbsStorageBuilder, ebs_device
    b = _hooks(TofuEbsStorageBuilder)
    assert [ebs_device(i) for i in range(8)] == ["/dev/xvdf", "/dev/xvdg", "/dev/xvdh", "/dev/xvdi",
                                                 "/dev/xvdj", "/dev/xvdk", "/dev/xvdl", "/dev/xvdm"]
    assert b.launch_mount(_storage("mnt_data"), None, 0) == {"device": "/dev/xvdf"}
    assert b.launch_mount(_storage("mnt_data"), None, 2) == {"device": "/dev/xvdh"}
    assert b.launch_variables() == ("ebs",)
    m = _mount("mnt_data", "/mnt/data", "ebs", device="/dev/xvdf")
    assert b.launch_script_lines(m, "coops") == [
        "# mount storage mnt_data (ebs) at /mnt/data",
        "mkdir -p '/mnt/data'",
        "DEV='/dev/xvdf'",
        'VOL="${ebs["mnt_data"].volume_id}"',
        'BYID="/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_$(printf \'%s\' "$VOL" | tr -d -)"',
        "# the attachment lands after boot: wait for either name",
        'for i in $(seq 1 60); do [ -e "$DEV" ] && break; [ -e "$BYID" ] && DEV="$BYID" && break; sleep 2; done',
        'if ! blkid "$DEV" >/dev/null 2>&1; then mkfs -t xfs "$DEV"; fi',
        "grep -q ' /mnt/data ' /etc/fstab || echo \"$DEV /mnt/data xfs defaults,nofail 0 2\" >> /etc/fstab",
        "mount '/mnt/data' || mount \"$DEV\" '/mnt/data'",
        "findmnt -rn '/mnt/data' >/dev/null 2>&1 && echo 'csis-mount: /mnt/data mounted' || echo 'csis-mount: /mnt/data NOT mounted'",
        "mkdir -p '/mnt/data/coops'",
        'chgrp "$GID" \'/mnt/data/coops\'',
        "chmod 2770 '/mnt/data/coops'",
    ]
    assert b.launch_script_lines(m, None)[-1].startswith("findmnt"), "no group, no subtree"
    assert b.launch_tasks(m, "coops") == [
        {"name": "mount point /mnt/data for storage mnt_data (ebs)",
         "ansible.builtin.file": {"path": "/mnt/data", "state": "directory"}},
        {"name": "filesystem on /dev/xvdf (mnt_data)", "community.general.filesystem": {"fstype": "xfs", "dev": "/dev/xvdf"}},
        {"name": "mount /dev/xvdf at /mnt/data",
         "ansible.posix.mount": {"path": "/mnt/data", "src": "/dev/xvdf", "fstype": "xfs",
                                 "opts": "defaults,nofail", "state": "mounted"}},
        {"name": "private subtree /mnt/data/coops (gid by reference)",
         "ansible.builtin.file": {"path": "/mnt/data/coops", "state": "directory",
                                  "group": "{{ group_gid }}", "mode": "2770"}},
    ]
    assert len(b.launch_tasks(m, None)) == 3


def test_the_efs_builder_mounts_through_the_access_point_and_makes_no_subtree():
    b = _hooks(TofuEfsStorageBuilder)
    m = _mount("share", "/mnt/share", "efs")
    assert b.launch_mount(_storage("share"), None, 0) == {} and b.launch_variables() == ("efs",)
    assert b.launch_script_lines(m, "coops") == [
        "# mount storage share (efs) at /mnt/share",
        "mkdir -p '/mnt/share'",
        'EFS_ID="${efs["share"].file_system_id}"',
        'EFS_AP="${efs["share"].access_point_id}"',
        "grep -q ' /mnt/share ' /etc/fstab || echo \"$EFS_ID:/ /mnt/share efs _netdev,tls,accesspoint=$EFS_AP,nofail 0 0\" >> /etc/fstab",
        "mount '/mnt/share' || true",
        "findmnt -rn '/mnt/share' >/dev/null 2>&1 && echo 'csis-mount: /mnt/share mounted' || echo 'csis-mount: /mnt/share NOT mounted'",
    ]
    assert b.launch_tasks(m, "coops") == [
        {"name": "mount point /mnt/share for storage share (efs)",
         "ansible.builtin.file": {"path": "/mnt/share", "state": "directory"}},
        {"name": "mount EFS share at /mnt/share",
         "ansible.posix.mount": {"path": "/mnt/share", "fstype": "efs", "src": "{{ efs['share'].file_system_id }}:/",
                                 "opts": "_netdev,tls,accesspoint={{ efs['share'].access_point_id }},nofail",
                                 "state": "mounted"}},
    ]


def test_the_s3_builder_mounts_nothing_and_says_so():
    b = _hooks(TofuS3StorageBuilder)
    m = _mount("bucket", "/mnt/bucket", "s3")
    assert b.launch_mount(_storage("bucket"), None, 0) == {} and b.launch_variables() == ()
    assert b.launch_script_lines(m, "coops") == [
        "# mount storage bucket (s3) at /mnt/bucket",
        "mkdir -p '/mnt/bucket'",
        "# s3 storage bucket: object access via the cloud CLI; no mount",
    ]
    assert b.launch_tasks(m, "coops") == [
        {"name": "storage bucket (s3): object access via the cloud's CLI, no mount",
         "ansible.builtin.debug": {"msg": "s3 storage bucket is not mounted"}}]
