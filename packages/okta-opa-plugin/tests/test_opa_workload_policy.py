# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 56: the CI login policy is a copy of the user policy with the
workload role as its only principal, derived from the standing record and
compared by content; the resolver reads policies and roles and writes
policies through an injected transport -- no network.
"""
from __future__ import annotations

import json
import urllib.error
from email.message import Message

from typing import Any

from cs_image_system.okta_opa_plugin.opa_gids import OpaGidResolver
from cs_image_system.okta_opa_plugin.workload_policy import (
    WorkloadSnapshot, ci_policy_from, ci_policy_name, connection_active, policies_equal, workload_state)

TEAM = "/v1/teams/t"

USER_RULE = {
    "id": "rule-1", "name": "allow_login_coops",
    "conditions": [{"condition_type": "gateway",
                    "condition_value": {"traffic_forwarding": True, "session_recording": False}}],
    "privileges": [{"privilege_type": "principal_account_ssh",
                    "privilege_value": {"enabled": True, "admin_level_permissions": False}}],
    "resource_selector": {"selector_type": "server_based_resource",
                          "selector": {"selectors": [{"selector_type": "server_label",
                                                      "selector": {"server_selector": {"labels": {"sftd.tx.group": "coops"}},
                                                                   "account_selector_type": "none",
                                                                   "account_selector": {}}}]}},
}
USER_POLICY = {"id": "pol-user", "name": "coops_v1_security_policy_user", "description": "Security policy for coops_user",
               "active": True, "resource_group": {"id": "rg-1", "name": "coops_rg"},
               "principals": {"user_groups": [{"id": "grp-1", "name": "coops_user"}]}, "rules": [USER_RULE]}
ROLE = {"id": "role-1", "name": "cs-image-system-ci"}


def test_the_ci_policy_is_the_user_policy_with_the_role_as_its_only_principal():
    body = ci_policy_from(USER_POLICY, "coops", "role-1")
    assert body["name"] == ci_policy_name("coops") == "coops_v1_security_policy_ci"
    assert body["active"] is True
    assert body["resource_group"] == {"id": "rg-1"}
    assert body["principals"] == {"user_groups": [], "workload_roles": [{"id": "role-1"}]}
    assert len(body["rules"]) == 1
    rule = body["rules"][0]
    assert "id" not in rule, "a copy posts as a new object"
    assert rule["resource_selector"] == USER_RULE["resource_selector"]
    assert rule["privileges"][0]["privilege_value"]["admin_level_permissions"] is False
    assert "do not edit by hand" in body["description"]


def test_admin_level_is_forced_off_even_when_the_source_grants_it():
    admin = json.loads(json.dumps(USER_POLICY))
    admin["rules"][0]["privileges"][0]["privilege_value"]["admin_level_permissions"] = True
    body = ci_policy_from(admin, "coops", "role-1")
    assert body["rules"][0]["privileges"][0]["privilege_value"]["admin_level_permissions"] is False


def test_policies_compare_by_reach_not_by_ids_or_descriptions():
    desired = ci_policy_from(USER_POLICY, "coops", "role-1")
    standing = json.loads(json.dumps(desired))
    standing["id"] = "pol-ci"
    standing["description"] = "edited in the console"
    standing["rules"][0]["id"] = "rule-9"
    standing["rules"][0]["security_policy_id"] = "pol-ci"     # OPA's back-reference on a stored rule (live 2026-09-22)
    standing["resource_group"] = {"id": "rg-1", "name": "coops_rg"}
    assert policies_equal(standing, desired)
    standing["rules"][0]["resource_selector"]["selector"]["selectors"][0]["selector"]["server_selector"]["labels"]["sftd.tx.group"] = "other"
    assert not policies_equal(standing, desired)
    standing = json.loads(json.dumps(desired))
    standing["principals"]["user_groups"] = [{"id": "grp-1"}]
    assert not policies_equal(standing, desired), "a human group added to the CI policy is a change"


def test_workload_state_reports_presence_mirroring_and_the_connection():
    ci = ci_policy_from(USER_POLICY, "coops", "role-1")
    ci["id"] = "pol-ci"
    snap = WorkloadSnapshot(policies=[USER_POLICY, ci], roles=[ROLE],
                            connections=[{"id": "c-1", "name": "github-cs-image-system", "status": "DRAFT"}])
    st = workload_state(snap, "coops", "github-cs-image-system", "cs-image-system-ci")
    assert st["role"] == {"present": True, "id": "role-1"}
    assert st["policy"] == {"present": True, "id": "pol-ci", "mirrors": True, "user_policy_present": True}
    assert st["connection"] == {"present": True, "active": False}
    # diverged: the console changed the CI policy's rule -- and the record says WHERE
    ci["rules"][0]["privileges"][0]["privilege_value"]["admin_level_permissions"] = True
    diverged = workload_state(snap, "coops", "github-cs-image-system", "cs-image-system-ci")["policy"]
    assert diverged["mirrors"] is False
    assert diverged["diff"] == ["rules[0].privileges[0].privilege_value.admin_level_permissions: True != False"]
    # absent role: nothing to mirror against, and the role is reported absent
    st = workload_state(WorkloadSnapshot(policies=[USER_POLICY], roles=[], connections=None),
                        "coops", "github-cs-image-system", "cs-image-system-ci")
    assert st["role"] == {"present": False, "id": None}
    assert st["policy"]["present"] is False and st["policy"]["mirrors"] is None
    assert "connection" not in st, "a connections listing that could not be read says nothing"


def test_connection_status_is_read_not_guessed():
    assert connection_active({"status": "ACTIVE"}) is True
    assert connection_active({"status": "draft"}) is False
    assert connection_active({"active": True}) is True
    assert connection_active({"status": "SOMETHING_NEW"}) is None
    assert connection_active({}) is None
    assert connection_active(None) is None


class FakeOpa:
    def __init__(self, policies=None, roles=None, *, fail_policies=False):
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.policies = list(policies or [])
        self.roles = list(roles or [])
        self.fail_policies = fail_policies

    def __call__(self, method, url, headers, body):
        path = url.split("https://h", 1)[1]
        parsed: dict[str, Any] = json.loads(body) if body else {}
        self.calls.append((method, path, parsed))
        if path.endswith("/service_token"):
            return {"bearer_token": "tok"}
        if path == f"{TEAM}/security_policy" and method == "GET":
            if self.fail_policies:
                raise urllib.error.HTTPError(url, 503, "unavailable", Message(), None)
            return {"list": self.policies}
        if path == f"{TEAM}/security_policy" and method == "POST":
            assert headers["Content-Type"] == "application/json"
            created: dict[str, Any] = dict(parsed) | {"id": f"pol-{len(self.policies) + 1}"}
            self.policies.append(created)
            return created
        if path.startswith(f"{TEAM}/security_policy/") and method == "PUT":
            pid = path.rsplit("/", 1)[1]
            self.policies = [dict(parsed) | {"id": pid} if p["id"] == pid else p for p in self.policies]
            return {}
        if path == f"{TEAM}/workload-roles" and method == "GET":   # the SDK's hyphenated path
            return {"list": self.roles}
        if path == f"{TEAM}/connections/workloads" and method == "GET":
            return {"list": [{"id": "c-1", "name": "github-cs-image-system", "status": "ACTIVE"}]}
        raise AssertionError(f"unexpected {method} {path}")


def _r(fake) -> OpaGidResolver:
    return OpaGidResolver("https://h", "t", "k", "s", transport=fake)


def test_the_resolver_reads_listings_and_writes_policies():
    fake = FakeOpa([USER_POLICY], [ROLE])
    r = _r(fake)
    assert [p["name"] for p in (r.security_policies() or [])] == ["coops_v1_security_policy_user"]
    assert [x["name"] for x in (r.workload_roles() or [])] == ["cs-image-system-ci"]
    assert (r.workload_connections() or [])[0]["status"] == "ACTIVE"
    created = r.create_security_policy(ci_policy_from(USER_POLICY, "coops", "role-1"))
    assert created["id"] == "pol-2"
    posted = next(b for m, p, b in fake.calls if m == "POST" and p.endswith("/security_policy"))
    assert posted is not None
    assert "id" not in posted, "the body carries no id: a copy posts as a new object"
    assert posted["principals"]["workload_roles"] == [{"id": "role-1"}]
    r.update_security_policy("pol-2", posted | {"active": False})
    assert any(m == "PUT" and p.endswith("/security_policy/pol-2") for m, p, _ in fake.calls)
    assert next(p for p in fake.policies if p["id"] == "pol-2")["active"] is False


def test_a_silent_service_reads_as_none_never_as_no_policies():
    fake = FakeOpa(fail_policies=True)
    assert _r(fake).security_policies() is None
