# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins UserBuilderBase.add_user_to_builder's email_as_username enforcement.

When the flag is set (the default), user.name must equal user.email casefolded
so the name doubles as the identity's login everywhere; blank names adopt the
email; a non-blank mismatch aborts.
"""
import pytest

from cs_image_system.base.basic.builder_base_user import UserBuilderBase
from cs_image_system.base.models.user import User
from cs_image_system.base.models.user_builder import UserBuilderModel


class _Model(UserBuilderModel):
    @classmethod
    def csis_name(cls) -> str:
        return "test"


def _builder(email_as_username: bool = True) -> UserBuilderBase:
    model = _Model(name="test-users", type_="test", email_as_username=email_as_username)
    return UserBuilderBase(model)


def _user(name: str, email: str) -> User:
    return User(name=name, email=email, first_name="a", last_name="b")


def test_matching_name_and_email_attaches():
    b = _builder()
    u = _user("alice@x.com", "alice@x.com")
    b.add_user_to_builder(u)
    assert u in b.get_users_for_builder()


def test_comparison_is_casefolded():
    b = _builder()
    u = _user("pat.trip@x.com", "Pat.Trip@X.com")
    b.add_user_to_builder(u)  # must not raise
    assert u in b.get_users_for_builder()


def test_mismatch_aborts():
    b = _builder()
    with pytest.raises(ValueError, match="email_as_username"):
        b.add_user_to_builder(_user("alice@x.com", "bob@x.com"))


def test_blank_name_adopts_email():
    b = _builder()
    u = _user("alice@x.com", "alice@x.com")
    # RootItem.__post_init__ rejects blank names at construction, so the
    # blank-name branch is exercised by blanking after construction.
    u.name = ""
    b.add_user_to_builder(u)
    assert u.name == "alice@x.com"


def test_flag_off_absorbs_mismatch():
    b = _builder(email_as_username=False)
    u = _user("alice", "alice@x.com")
    b.add_user_to_builder(u)  # no enforcement
    assert u.name == "alice"


def test_builders_do_not_share_user_lists():
    """local_users must be per instance -- a class-level default list would
    make two user builders each emit ALL users (formerly the case)."""
    from cs_image_system.base.basic.builder_base_group import GroupBuilderBase

    a, b = _builder(), _builder()
    a.add_user_to_builder(_user("alice@x.com", "alice@x.com"))
    assert b.get_users_for_builder() == []
    assert UserBuilderBase.__dict__.get("local_users") is None  # no class default
    assert GroupBuilderBase.__dict__.get("local_users") is None
    assert GroupBuilderBase.__dict__.get("local_groups") is None
