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
terraform template variables: ``group_gid``, one map per storage kind
that reads values at launch (storage name -> the values the instance root
binds; each storage builder names its own in ``launch_variables``) and
the enrollment token (``launch_params.ENROLLMENT_TOKEN_VARIABLE``) --
:func:`extra_vars` lists them for a configuration. Nothing here reads meta-state or the cloud; it is a pure
rendering of what ``compute_launch_params`` already produced, each
mount's tasks being its storage builder's ``launch_tasks``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml

from .launch_enrollment import enrollment_kind_for
from .launch_params import launch_variables, mount_tasks

if TYPE_CHECKING:
    from .run_context import RunContext


def extra_vars(ctx: "RunContext") -> tuple[str, ...]:
    """The extra-vars a playbook takes: the launch template's variables,
    in the same order (``group_gid``, the storage builders' own in
    declaration order, the enrollment token)."""
    return launch_variables(ctx)


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


def launch_playbook(params: dict[str, Any], inventory_name: str | None = None,
                    ctx: "RunContext | None" = None) -> str:
    """The playbook equivalent of ``user_data_template(params)``.
    ``inventory_name`` is the instance's declared name -- the key
    ``launch_inventory`` uses -- and is what the play TARGETS;
    ``params["hostname"]`` is the canonical name the machine is GIVEN (the
    two differ: ``test`` versus ``test-001``). Without it the play targets
    the hostname, as it did when they coincided.
    ``ctx`` is the configured context unless given (it names each mount's
    storage builder)."""
    host = params["hostname"]
    target = inventory_name or host
    group = params.get("group")
    tasks: list[dict[str, Any]] = [
        {"name": f"hostname {host}", "ansible.builtin.hostname": {"name": host}},
    ]
    for m in params.get("mounts", []):
        tasks += mount_tasks(m, group, ctx)        # the mount's whole task list is the storage's
    # the identity plugin that issued the enrollment renders its tasks
    kind = enrollment_kind_for(params)
    if kind is not None:
        tasks += kind.ansible_tasks(params)
    play = {
        "name": f"cs-image-system launch parameters for {host} (N26; immutable after launch)",
        "hosts": target,
        "become": True,
        "vars": {"csis_image": params.get("image"), "csis_build": params.get("build"),
                 "csis_group": group, "csis_session": params.get("session")},
        "tasks": tasks,
    }
    return yaml.safe_dump([play], sort_keys=False, width=120)
