# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A GCP storage builder's ``variables:`` (default labels) reach
the module call under the item's own labels and the csis_* ones."""
from types import SimpleNamespace
from typing import Any, cast

from cs_image_system.tf_gcp_plugin.tf_gcp_models import GcpVariables
from cs_image_system.tf_gcp_plugin.tf_gcp_storage_builder import TofuGcpStorageBuilder


def _storage(name, *, tags=None, groups=None) -> Any:
    return SimpleNamespace(get_name=lambda: name, tags=tags or {}, groups=groups or [],
                           public_read=False)


def test_builder_default_labels_sit_under_the_items():
    me = SimpleNamespace(model=SimpleNamespace(variables=GcpVariables(tags={"team": "builder", "cost": "sandbox"})))
    labels = TofuGcpStorageBuilder._labels(cast(Any, me), _storage("gce_data", tags={"team": "item"}, groups=["coops"]))
    assert labels["cost"] == "sandbox" and labels["team"] == "item"
    assert labels["csis_storage"] == "gce_data" and labels["csis_group_coops"] == "true"


# ------------------------------------------------- the launch hooks (device and mount lines)

def _mount(name, mp, stype, **extra) -> dict:
    return {"storage": name, "type": stype, "builder": f"gcp-{stype}", "mount_point": mp,
            "group": "coops", "share_mode": "2770", "public_read": False, **extra}


def _hooks(cls) -> Any:
    """A builder with no model: the launch hooks read only the mount record."""
    return object.__new__(cls)


def test_the_pd_builder_owns_the_by_id_device_name_and_the_block_sequence():
    from cs_image_system.tf_gcp_plugin.tf_gcp_storage_builder import TofuPdStorageBuilder
    b = _hooks(TofuPdStorageBuilder)
    # one sanitisation for the attachment's device_name and the mounted path
    assert b.launch_mount(_storage("gce_data"), None, 0) == {"device": "/dev/disk/by-id/google-gce-data"}
    assert b.launch_mount(_storage("gce_data"), None, 3) == {"device": "/dev/disk/by-id/google-gce-data"}
    assert b.launch_variables() == ()
    m = _mount("gce_data", "/mnt/gce-data", "pd", device="/dev/disk/by-id/google-gce-data")
    assert b.launch_script_lines(m, "coops") == [
        "# mount storage gce_data (pd) at /mnt/gce-data",
        "mkdir -p '/mnt/gce-data'",
        "DEV='/dev/disk/by-id/google-gce-data'",
        'BYID="$DEV"',
        "# the attachment lands after boot: wait for either name",
        'for i in $(seq 1 60); do [ -e "$DEV" ] && break; [ -e "$BYID" ] && DEV="$BYID" && break; sleep 2; done',
        'if ! blkid "$DEV" >/dev/null 2>&1; then mkfs -t xfs "$DEV"; fi',
        "grep -q ' /mnt/gce-data ' /etc/fstab || echo \"$DEV /mnt/gce-data xfs defaults,nofail 0 2\" >> /etc/fstab",
        "mount '/mnt/gce-data' || mount \"$DEV\" '/mnt/gce-data'",
        "findmnt -rn '/mnt/gce-data' >/dev/null 2>&1 && echo 'csis-mount: /mnt/gce-data mounted' || echo 'csis-mount: /mnt/gce-data NOT mounted'",
        "mkdir -p '/mnt/gce-data/coops'",
        'chgrp "$GID" \'/mnt/gce-data/coops\'',
        "chmod 2770 '/mnt/gce-data/coops'",
    ]
    # the playbook: the directory task alone, as it always was for a disk
    assert b.launch_tasks(m, "coops") == [{"name": "mount point /mnt/gce-data for storage gce_data (pd)",
                                           "ansible.builtin.file": {"path": "/mnt/gce-data", "state": "directory"}}]


def test_the_filestore_builder_mounts_over_nfs_and_makes_the_subtree():
    from cs_image_system.tf_gcp_plugin.tf_gcp_storage_builder import TofuFilestoreStorageBuilder
    b = _hooks(TofuFilestoreStorageBuilder)
    m = _mount("share", "/mnt/share", "filestore")
    assert b.launch_mount(_storage("share"), None, 0) == {} and b.launch_variables() == ("filestore",)
    assert b.launch_script_lines(m, "coops") == [
        "# mount storage share (filestore) at /mnt/share",
        "mkdir -p '/mnt/share'",
        'FS_IP="${filestore["share"].ip_address}"',
        'FS_SHARE="${filestore["share"].share_name}"',
        "grep -q ' /mnt/share ' /etc/fstab || echo \"$FS_IP:/$FS_SHARE /mnt/share nfs defaults,_netdev,nofail 0 0\" >> /etc/fstab",
        "mount '/mnt/share' || true",
        "findmnt -rn '/mnt/share' >/dev/null 2>&1 && echo 'csis-mount: /mnt/share mounted' || echo 'csis-mount: /mnt/share NOT mounted'",
        "mkdir -p '/mnt/share/coops'",
        'chgrp "$GID" \'/mnt/share/coops\'',
        "chmod 2770 '/mnt/share/coops'",
    ]
    assert [t["name"] for t in b.launch_tasks(m, "coops")] == ["mount point /mnt/share for storage share (filestore)"]


def test_the_gcs_builder_mounts_nothing_and_says_so():
    from cs_image_system.tf_gcp_plugin.tf_gcp_storage_builder import TofuGcsStorageBuilder
    b = _hooks(TofuGcsStorageBuilder)
    m = _mount("gce_bucket", "/mnt/bucket", "gcs")
    assert b.launch_mount(_storage("gce_bucket"), None, 0) == {} and b.launch_variables() == ()
    assert b.launch_script_lines(m, "coops") == [
        "# mount storage gce_bucket (gcs) at /mnt/bucket",
        "mkdir -p '/mnt/bucket'",
        "# gcs storage gce_bucket: object access via the cloud CLI; no mount",
    ]
    # the playbook never special-cased this kind: the directory task, as before
    assert [t["name"] for t in b.launch_tasks(m, "coops")] == ["mount point /mnt/bucket for storage gce_bucket (gcs)"]
