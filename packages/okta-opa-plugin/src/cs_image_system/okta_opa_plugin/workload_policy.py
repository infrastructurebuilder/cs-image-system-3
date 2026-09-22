# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 56: the CI login policy is a COPY of the group's user policy.

CI logs into a group's servers as a workload -- GitHub's own OIDC token,
presented to the team's workload connection and mapped to the team's one
workload role (both made by hand once, WORKLOAD_CONNECTION.md). What grants
the role reach is a security policy per group, ``<group>_v1_security_policy_ci``,
kept beside the user policy the terraform module emits
(``<group>_v1_security_policy_user``). The provider cannot name a workload
role as a principal (okta/oktapam 0.7.1 accepts only groups), so the policy
travels through the OPA API, and it is DERIVED from the standing user policy
record on every reconcile: same resource group, the rule verbatim, admin-level
forced off, the role as the only principal. That is what makes "mirrors the
user policy" structural rather than a promise -- a rule change in the module
propagates on the next identity run.

Pure functions over API records; the builder does the reading and writing.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

USER_POLICY_SUFFIX = "_v1_security_policy_user"
CI_POLICY_SUFFIX = "_v1_security_policy_ci"


def user_policy_name(group: str) -> str:
    return f"{group}{USER_POLICY_SUFFIX}"


def ci_policy_name(group: str) -> str:
    return f"{group}{CI_POLICY_SUFFIX}"


@dataclass
class WorkloadSnapshot:
    """The three listings one reconcile or state read needs, read once."""
    policies: list[dict[str, Any]] = field(default_factory=list)
    roles: list[dict[str, Any]] = field(default_factory=list)
    connections: list[dict[str, Any]] | None = None   # None: could not be read


def by_name(records: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for rec in records:
        if str(rec.get("name") or "") == name:
            return rec
    return None


def _without_ids(value: Any) -> Any:
    """The record with every ``id`` key removed at every depth, so a copy
    posts as a new object and two records compare by content."""
    if isinstance(value, dict):
        return {k: _without_ids(v) for k, v in value.items() if k != "id"}
    if isinstance(value, list):
        return [_without_ids(v) for v in value]
    return value


def _admin_off(value: Any) -> Any:
    """The same record with every ``admin_level_permissions`` forced False:
    CI gets user-level access and never more, whatever the source says."""
    if isinstance(value, dict):
        return {k: (False if k == "admin_level_permissions" else _admin_off(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_admin_off(v) for v in value]
    return value


def ci_policy_from(user_policy: dict[str, Any], group: str, role_id: str) -> dict[str, Any]:
    """The CI policy body derived from the standing user policy record."""
    rg = user_policy.get("resource_group")
    resource_group = {"id": rg["id"]} if isinstance(rg, dict) and rg.get("id") else rg
    return {
        "name": ci_policy_name(group),
        "description": (f"CI login policy for the servers of Okta group {group} -- a copy of "
                        f"{user_policy_name(group)} with the workload role as its only principal "
                        "(cs-image-system stage 56; system-managed, do not edit by hand)"),
        "active": True,
        "resource_group": resource_group,
        "principals": {"user_groups": [], "workload_roles": [{"id": role_id}]},
        "rules": _admin_off(_without_ids(copy.deepcopy(user_policy.get("rules") or []))),
    }


def _comparable(policy: dict[str, Any]) -> dict[str, Any]:
    principals = policy.get("principals") or {}
    rg = policy.get("resource_group")
    return {
        "active": bool(policy.get("active", True)),
        "resource_group": str(rg.get("id")) if isinstance(rg, dict) else rg,
        "user_groups": sorted(str(g.get("id") if isinstance(g, dict) else g) for g in principals.get("user_groups") or []),
        "workload_roles": sorted(str(r.get("id") if isinstance(r, dict) else r) for r in principals.get("workload_roles") or []),
        "rules": _without_ids(policy.get("rules") or []),
    }


def policies_equal(standing: dict[str, Any], desired: dict[str, Any]) -> bool:
    """Same reach: active, resource group, principals and rules by content
    (ids and descriptions aside)."""
    return _comparable(standing) == _comparable(desired)


def connection_active(connection: dict[str, Any] | None) -> bool | None:
    """True/False from whichever status field the record carries; None when
    the record is absent or names its status in a way this code does not
    know (reported, never guessed)."""
    if connection is None:
        return None
    status = connection.get("status")
    if isinstance(status, str):
        if status.upper() == "ACTIVE":
            return True
        if status.upper() == "DRAFT":
            return False
    active = connection.get("active")
    if isinstance(active, bool):
        return active
    return None


def workload_state(snapshot: WorkloadSnapshot, group: str, connection_name: str,
                   role_name: str) -> dict[str, Any]:
    """Reality for one group, from one snapshot: the connection's presence
    and activation, the role's presence and id, and whether the standing CI
    policy is present and still mirrors the user policy."""
    role = by_name(snapshot.roles, role_name)
    user = by_name(snapshot.policies, user_policy_name(group))
    ci = by_name(snapshot.policies, ci_policy_name(group))
    mirrors: bool | None = None
    if ci is not None and user is not None and role is not None and role.get("id"):
        mirrors = policies_equal(ci, ci_policy_from(user, group, str(role["id"])))
    out: dict[str, Any] = {
        "role": {"present": role is not None, "id": str(role.get("id") or "") if role else None},
        "policy": {"present": ci is not None, "id": str(ci.get("id") or "") if ci else None,
                   "mirrors": mirrors, "user_policy_present": user is not None},
    }
    if snapshot.connections is not None:
        conn = by_name(snapshot.connections, connection_name)
        out["connection"] = {"present": conn is not None, "active": connection_active(conn)}
    return out
