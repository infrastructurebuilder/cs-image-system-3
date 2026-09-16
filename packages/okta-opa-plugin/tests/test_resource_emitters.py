# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the OktaTF* resource emitters (now rendered via hashicorp_utils.blocks)."""
from types import SimpleNamespace
from typing import Any, cast

from cs_image_system.okta_opa_plugin.okta_tf_models import (
    OktaTFGroup,
    OktaTFGroupLookup,
    OktaTFResourceGroup,
    OktaTFSecurityPolicyV1,
    OktaTFUser,
    OktaTFUserToGroup,
)


def _group(name="devs", include_root=False):
    return cast(Any, SimpleNamespace(
        name=name, include_root_group_in_admins=include_root))


def _user(name="alice", service=False, enabled=True):
    return cast(Any, SimpleNamespace(
        name=name, email=f"{name}@example.com", first_name=name,
        last_name="example", is_service_account=service, is_enabled=enabled))


def test_group_emits_resource():
    hcl = "\n".join(OktaTFGroup(_group()).generate_terraform())
    assert 'resource "oktapam_group" "devs_user" {' in hcl
    assert 'name = "devs_user"' in hcl


def test_group_lookup_emits_data_only():
    lookup = OktaTFGroupLookup(_group("Dev Team"), provider="okta.okta_ro_groups")
    hcl = "\n".join(lookup.generate_terraform_data())
    assert 'data "okta_group" "dev_team" {' in hcl
    assert "provider = okta.okta_ro_groups" in hcl
    assert 'name = "Dev Team"' in hcl
    assert lookup.get_resource_name() == "data.okta_group.dev_team"
    assert lookup.generate_terraform() == []


def test_group_lookup_without_provider():
    hcl = "\n".join(OktaTFGroupLookup(_group()).generate_terraform_data())
    assert 'data "okta_group" "devs" {' in hcl
    assert "provider" not in hcl


def test_user_to_group_attachment_raw_reference():
    g, u = OktaTFGroup(_group()), OktaTFUser(_user())
    hcl = "\n".join(OktaTFUserToGroup(g, u).generate_terraform())
    assert 'resource "oktapam_user_group_attachment" "devs_alice"' in hcl
    assert "group = oktapam_group.devs_user.name" in hcl  # raw address
    assert 'username = "alice"' in hcl


def test_resource_group_emits_both_resources():
    g = OktaTFGroup(_group(), admin=True)
    rg = OktaTFResourceGroup(g, admin_groups=[g], account_discovery=True,
                             gateway_selector="environment=staging")
    hcl = "\n".join(rg.generate_terraform())
    assert 'resource "oktapam_resource_group" "devs_rg"' in hcl
    assert "[oktapam_group.devs_admin.id]" in hcl.replace("\n", "") or \
           "oktapam_group.devs_admin.id" in hcl
    assert 'resource "oktapam_resource_group_project" "devs_rg_login"' in hcl
    assert "resource_group = oktapam_resource_group.devs_rg.id" in hcl
    assert "account_discovery = true" in hcl
    assert 'gateway_selector = "environment=staging"' in hcl


def test_security_policy_nested_structure():
    g = OktaTFGroup(_group())
    rg = OktaTFResourceGroup(g)
    pol = OktaTFSecurityPolicyV1(rg, g)
    hcl = "\n".join(pol.generate_terraform())
    assert 'resource "oktapam_security_policy"' in hcl
    assert "resource_group = oktapam_resource_group.devs_rg.id" in hcl
    assert "principals {" in hcl
    assert "groups = [oktapam_group.devs_user.id]" in hcl
    assert "rule {" in hcl and "conditions {" in hcl and "gateway {" in hcl
    assert "traffic_forwarding = true" in hcl and "session_recording = false" in hcl
    assert "privileges {" in hcl and "principal_account_ssh {" in hcl
    assert "admin_level_permissions = false" in hcl
    assert "label_selectors {" in hcl
    squeezed = " ".join(hcl.split())
    assert '"system.os_type" = "linux"' in squeezed
    assert '"sftd.tx.group" = "devs"' in squeezed
