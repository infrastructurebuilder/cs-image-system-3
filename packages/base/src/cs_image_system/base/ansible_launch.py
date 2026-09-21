# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Prototype: launch parameters as an ansible inventory + playbook
(EXPLORE "Possible Other Infra-as-Code tools", step 2 -- investigation).

The instance root feeds :func:`launch_params.user_data_template` through
``templatefile`` so cloud-init runs the mounts / group subtree / enrollment
at first boot. The same *structural* launch parameters can be rendered as
an ansible playbook for targets that have no user-data (metal, containers,
an already-running host): identical decisions, a different executor.

Runtime values still arrive by reference, as extra-vars rather than
terraform template variables: ``group_gid``, ``efs`` (storage ->
{file_system_id, access_point_id}) and ``sft_enrollment_token``. Nothing
here reads meta-state or the cloud; it is a pure rendering of what
``compute_launch_params`` already produced.
"""
from __future__ import annotations

from typing import Any

import yaml

EXTRA_VARS = ("group_gid", "efs", "sft_enrollment_token")


def launch_inventory(params_by_instance: dict[str, dict[str, Any]]) -> str:
    """One host per instance, grouped by owning group and identity type."""
    hosts = {name: {"csis_image": p.get("image"), "csis_build": p.get("build")}
             for name, p in sorted(params_by_instance.items())}
    children: dict[str, dict[str, Any]] = {}
    for name, p in sorted(params_by_instance.items()):
        for key in (p.get("group"), p.get("identity_type")):
            if key:
                children.setdefault(f"csis_{key}", {"hosts": {}})["hosts"][name] = {}
    inv: dict[str, Any] = {"all": {"hosts": hosts, "children": children}}
    return yaml.safe_dump(inv, sort_keys=False)


def launch_playbook(params: dict[str, Any], name: str | None = None) -> str:
    """The playbook equivalent of ``user_data_template(params)``. ``name`` is
    the instance's declared name -- the inventory key ``launch_inventory``
    uses -- and is what the play TARGETS; ``params["hostname"]`` is the
    canonical name the machine is GIVEN (since stage 55 step 4 the two
    differ: ``test`` versus ``test-001``). Without ``name`` the play targets
    the hostname, as it did when they coincided."""
    host = params["hostname"]
    target = name or host
    group = params.get("group")
    tasks: list[dict[str, Any]] = [
        {"name": f"hostname {host}", "ansible.builtin.hostname": {"name": host}},
    ]
    for m in params.get("mounts", []):
        mp, name, stype = m["mount_point"], m["storage"], m["type"]
        if stype == "s3":
            tasks.append({"name": f"storage {name} (s3): object access via the AWS CLI, no mount",
                          "ansible.builtin.debug": {"msg": f"s3 storage {name} is not mounted"}})
            continue
        tasks.append({"name": f"mount point {mp} for storage {name} ({stype})",
                      "ansible.builtin.file": {"path": mp, "state": "directory"}})
        if stype == "ebs":
            dev = m["device"]
            tasks.append({"name": f"filesystem on {dev} ({name})",
                          "community.general.filesystem": {"fstype": "xfs", "dev": dev}})
            tasks.append({"name": f"mount {dev} at {mp}",
                          "ansible.posix.mount": {"path": mp, "src": dev, "fstype": "xfs",
                                                  "opts": "defaults,nofail", "state": "mounted"}})
            if group:
                tasks.append({"name": f"private subtree {mp}/{group} (gid by reference)",
                              "ansible.builtin.file": {"path": f"{mp}/{group}", "state": "directory",
                                                       "group": "{{ group_gid }}",
                                                       "mode": str(m["share_mode"])}})
        elif stype == "efs":
            tasks.append({"name": f"mount EFS {name} at {mp}",
                          "ansible.posix.mount": {
                              "path": mp, "fstype": "efs",
                              "src": "{{ efs['" + name + "'].file_system_id }}:/",
                              "opts": "_netdev,tls,accesspoint={{ efs['" + name + "'].access_point_id }},nofail",
                              "state": "mounted"}})
    enrollment = params.get("enrollment") or {}
    if enrollment.get("enrollment") == "sftd-token":
        tasks += [
            {"name": "sftd enrollment token (supplied at run time, never recorded)",
             "ansible.builtin.copy": {"dest": "/var/lib/sftd/enrollment.token",
                                      "content": "{{ sft_enrollment_token }}", "mode": "0600"},
             "when": "sft_enrollment_token | default('') | length > 0", "no_log": True},
            {"name": "start sftd", "ansible.builtin.service": {"name": "sftd", "state": "restarted"},
             "when": "sft_enrollment_token | default('') | length > 0"},
        ]
    play = {
        "name": f"cs-image-system launch parameters for {host} (N26; immutable after launch)",
        "hosts": target,
        "become": True,
        "vars": {"csis_image": params.get("image"), "csis_build": params.get("build"),
                 "csis_group": group, "csis_session": params.get("session")},
        "tasks": tasks,
    }
    return yaml.safe_dump([play], sort_keys=False, width=120)
