# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XIV item 6: what the identity module makes for a group, read back.

On 2026-10-19 another configuration rewrote three of `basic`'s OPA objects in
place, keeping their ids: the resource group's delegated admin and the user
and admin policies' rule name and descriptions. The strict state query saw
only the side effect (the CI policy no longer mirroring the user policy); only
a `tofu plan` of the identity root saw the rest. A plan cannot run in CI's
`live` job -- the read role holds no state object, by design -- so the query
compares OPA's records with what `tfmodules/okta_opa_module` makes, which is
fixed by the group's id alone (the builder passes no delegated admins and no
extra labels): the resource group's description and delegated admin, and each
policy's description, activity, principal, rule name, privilege, gateway
conditions and server labels. A test holds these to the module's text.

Pure functions over API records; the builder does the reading.
"""
from __future__ import annotations

from typing import Any

from .workload_policy import USER_POLICY_SUFFIX, by_name

ADMIN_POLICY_SUFFIX = "_v1_security_policy_admin"


def admin_policy_name(group_id: str) -> str:
    return f"{group_id}{ADMIN_POLICY_SUFFIX}"


def expected(group_id: str) -> dict[str, dict[str, Any]]:
    """The module's objects for ``group_id`` (tfmodules/okta_opa_module/main.tf)."""
    g = group_id
    labels = _label_set({"system.os_type": "linux", "sftd.tx.group": g})

    def policy(kind: str, admin_level: bool) -> dict[str, Any]:
        return {"description": f"Security policy for Okta group {g}_{kind}", "active": True,
                "principals": [f"{g}_{kind}"],
                "rules": [{"name": f"allow_login_{g}", "admin_level_permissions": admin_level,
                           "traffic_forwarding": True, "session_recording": False, "labels": labels}]}
    return {
        "resource_group": {"name": f"{g}_rg", "description": f"Resource group for Okta group {g}",
                           "delegated_admins": [f"{g}_admin"]},
        "user_policy": {"name": f"{g}{USER_POLICY_SUFFIX}", **policy("user", False)},
        "admin_policy": {"name": admin_policy_name(g), **policy("admin", True)},
    }


def _label_set(labels: dict[str, Any]) -> list[str]:
    """Server labels as one sorted ``key=value`` list: compared whole, so a label
    another tool ADDED (which narrows who may log in) is a difference too."""
    return sorted(f"{k}={v}" for k, v in labels.items())


def _names(items: Any) -> list[str] | None:
    """The names of a list of {id, name} references; None when a name is absent
    (a record that carries ids alone is not compared, never guessed)."""
    out = []
    for it in items or []:
        name = it.get("name") if isinstance(it, dict) else None
        if not name:
            return None
        out.append(str(name))
    return sorted(out)


def resource_group_facts(record: dict[str, Any]) -> dict[str, Any]:
    return {"name": record.get("name"), "description": record.get("description"),
            "delegated_admins": _names(record.get("delegated_resource_admin_groups"))}


def _rule_facts(rule: dict[str, Any]) -> dict[str, Any]:
    ssh = next((p.get("privilege_value") or {} for p in rule.get("privileges") or []
                if isinstance(p, dict) and p.get("privilege_type") == "principal_account_ssh"), {})
    gateway = next((c.get("condition_value") or {} for c in rule.get("conditions") or []
                    if isinstance(c, dict) and c.get("condition_type") == "gateway"), {})
    labels: dict[str, Any] = {}
    # the live API keeps the list at resource_selector.selectors (2026-10-23); the documented
    # shape nests it under resource_selector.selector -- both are read
    rs = rule.get("resource_selector") or {}
    selectors = rs.get("selectors") or (rs.get("selector") or {}).get("selectors") or []
    for s in selectors:
        labels.update((((s or {}).get("selector") or {}).get("server_selector") or {}).get("labels") or {})
    return {"name": rule.get("name"), "admin_level_permissions": ssh.get("admin_level_permissions"),
            "traffic_forwarding": gateway.get("traffic_forwarding"),
            "session_recording": gateway.get("session_recording"), "labels": _label_set(labels)}


def policy_facts(record: dict[str, Any]) -> dict[str, Any]:
    return {"name": record.get("name"), "description": record.get("description"),
            "active": bool(record.get("active", True)),
            "principals": _names((record.get("principals") or {}).get("user_groups")),
            "rules": [_rule_facts(r) for r in record.get("rules") or [] if isinstance(r, dict)]}


def _diff(have: Any, want: Any, path: str = "") -> list[str]:
    """Every leaf where OPA's record (have) and the module (want) disagree, as
    ``path: have != want``; a fact OPA's record leaves unnamed (None) is not
    compared."""
    if isinstance(want, dict):
        have = have if isinstance(have, dict) else {}
        return [d for k in want for d in _diff(have.get(k), want[k], f"{path}.{k}" if path else k)]
    if isinstance(want, list) and want and isinstance(want[0], dict):
        have = have if isinstance(have, list) else []
        out = [] if len(have) == len(want) else [f"{path}: {len(have)} rule(s) != {len(want)}"]
        return out + [d for i, (h, w) in enumerate(zip(have, want)) for d in _diff(h, w, f"{path}[{i}]")]
    if have is None:
        return []
    return [] if have == want else [f"{path}: {have!r} != {want!r}"]


def module_objects_state(group_id: str, resource_group: dict[str, Any] | None,
                         policies: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """For each module object: present, and -- when it differs -- the
    differences. ``resource_group`` is the group's full record (its listing
    entry carries no delegated admins), or None when there is none."""
    want = expected(group_id)
    out: dict[str, dict[str, Any]] = {}
    rg_want = {k: v for k, v in want["resource_group"].items() if k != "name"}
    if resource_group is None:
        out["resource_group"] = {"name": want["resource_group"]["name"], "present": False}
    else:
        diff = _diff(resource_group_facts(resource_group), rg_want)
        out["resource_group"] = {"name": want["resource_group"]["name"], "present": True, **({"diff": diff} if diff else {})}
    for key in ("user_policy", "admin_policy"):
        name = want[key]["name"]
        record = by_name(policies, name)
        if record is None:
            out[key] = {"name": name, "present": False}
            continue
        diff = _diff(policy_facts(record), {k: v for k, v in want[key].items() if k != "name"})
        out[key] = {"name": name, "present": True, **({"diff": diff} if diff else {})}
    return out
