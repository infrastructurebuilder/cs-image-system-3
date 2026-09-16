# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins OktaTFUser's live okta_user emission (formerly commented oktapam_user)."""

from cs_image_system.base.models.user import User
from cs_image_system.okta_opa_plugin.okta_tf_models import OktaTFUser

PROVIDER = "okta.okta_tf_users"


def _user(**kw) -> User:
    kw.setdefault("name", "alice.smith@x.com")
    kw.setdefault("email", "alice.smith@x.com")
    kw.setdefault("first_name", "Alice")
    kw.setdefault("last_name", "Smith")
    return User(**kw)


def test_resource_shape():
    hcl = "\n".join(OktaTFUser(_user(), provider=PROVIDER).generate_terraform())
    # label must be a valid terraform label: no '.', no '@'
    assert 'resource "okta_user" "alice_smith_x_com" {' in hcl
    assert "provider = okta.okta_tf_users" in hcl  # raw, unquoted
    assert 'first_name = "Alice"' in hcl
    assert 'last_name = "Smith"' in hcl
    assert 'login = "alice.smith@x.com"' in hcl
    assert 'email = "alice.smith@x.com"' in hcl
    assert 'status = "ACTIVE"' in hcl
    # live blocks: nothing commented except the leading comment line
    lines = hcl.splitlines()
    assert sum(1 for line in lines if line.startswith("#")) == 1


def test_no_user_type_and_no_public_keys():
    """okta_user.user_type is a User Type id, not human/service; public_keys
    have no home on this resource."""
    u = _user(is_service_account=True, public_keys=["ssh-rsa AAA"])
    hcl = "\n".join(OktaTFUser(u, provider=PROVIDER).generate_terraform())
    assert "user_type" not in hcl
    assert "public_keys" not in hcl and "ssh-rsa" not in hcl


def test_status_mapping():
    assert 'status = "SUSPENDED"' in "\n".join(
        OktaTFUser(_user(is_enabled=False), provider=PROVIDER).generate_terraform())
    assert 'status = "STAGED"' in "\n".join(
        OktaTFUser(_user(), provider=PROVIDER, status="STAGED").generate_terraform())
    # disabled wins over a passed status
    assert 'status = "SUSPENDED"' in "\n".join(
        OktaTFUser(_user(is_enabled=False), provider=PROVIDER,
                   status="STAGED").generate_terraform())


def test_set_optionals_emitted_unset_omitted():
    u = _user(mobile_phone="555", title="Dr", cost_center="cc1")
    hcl = "\n".join(OktaTFUser(u, provider=PROVIDER).generate_terraform())
    assert 'mobile_phone = "555"' in hcl
    assert 'title = "Dr"' in hcl
    assert 'cost_center = "cc1"' in hcl
    for absent in ("department", "manager_id", "zip_code", "middle_name"):
        assert absent not in hcl


def test_resource_address_and_label():
    otf = OktaTFUser(_user())
    assert otf.get_resource_name() == "okta_user.alice_smith_x_com"


def test_data_lookup_with_depends_on():
    lines = OktaTFUser(_user(), provider=PROVIDER).generate_terraform_data()
    hcl = "\n".join(lines)
    assert 'data "okta_user" "alice_smith_x_com" {' in hcl
    assert "depends_on" in hcl
    assert "okta_user.alice_smith_x_com," in hcl  # raw address, unquoted
    assert "search {" in hcl
    assert 'name = "profile.login"' in hcl
    assert 'value = "alice.smith@x.com"' in hcl
    assert 'comparison = "eq"' in hcl


def test_data_lookup_without_depends_on():
    hcl = "\n".join(OktaTFUser(_user(), provider=PROVIDER,
                               lookup_depends_on=False).generate_terraform_data())
    assert "depends_on" not in hcl


def test_login_from_bare_name_when_disabled():
    u = _user()
    hcl = "\n".join(OktaTFUser(u, provider=PROVIDER,
                               login_from_email=False).generate_terraform())
    assert 'login = "alice.smith@x.com"' in hcl  # name == email here anyway


def test_no_provider_omits_meta_argument():
    hcl = "\n".join(OktaTFUser(_user()).generate_terraform())
    assert "provider =" not in hcl
