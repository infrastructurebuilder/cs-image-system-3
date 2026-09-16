# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins User.first_name / last_name as required data.

They are never derived from ``name`` (the old split_name() parser is gone --
it corrupted email-shaped names into e.g. last_name='alvis@noaa gov' and had
no readers), so a User cannot exist without both being explicitly provided
and non-blank.
"""
import pytest

from cs_image_system.base.models.user import User


def test_user_with_both_names_constructs():
    u = User(name="alice.smith", first_name="Alice", last_name="Smith")
    assert (u.first_name, u.last_name) == ("Alice", "Smith")


def test_missing_names_raise_at_construction():
    # stage 23: the contract is that construction FAILS, not which exception
    # class carries it. A dataclass raised TypeError for a missing argument;
    # pydantic raises its own ValidationError. Both are accepted so the test
    # asserts the behaviour rather than the framework.
    from pydantic import ValidationError
    for kwargs in ({"name": "alice.smith"}, {"name": "alice.smith", "first_name": "Alice"}):
        with pytest.raises((TypeError, ValidationError)):
            User(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_blank_names_are_rejected(bad):
    with pytest.raises(ValueError, match="non-blank first_name"):
        User(name="alice.smith", first_name=bad, last_name="Smith")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-blank last_name"):
        User(name="alice.smith", first_name="Alice", last_name=bad)  # type: ignore[arg-type]


def test_names_are_not_derived_from_dotted_name():
    """A separator-less name is now legal; nothing parses `name` anymore."""
    u = User(name="jdoe", first_name="John", last_name="Doe")
    assert u.name == "jdoe"
    assert (u.first_name, u.last_name) == ("John", "Doe")


def test_email_shaped_name_cannot_corrupt_last_name():
    """The regression the old parser caused: last_name='alpha@example invalid'."""
    u = User(
        name="avery.alpha@example.invalid",
        first_name="avery",
        last_name="alpha",
        email="avery.alpha@example.invalid",
    )
    assert "@" not in u.last_name
    assert u.last_name == "alpha"


def test_user_missing_names_fails_to_structure(converter_ready):
    """YAML without first_name/last_name must fail structuring (stage 23: the
    mapper is pydantic, so the refusal arrives as its ValidationError)."""
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError):
        converter_ready.structure({"name": "alice.smith"}, User)


def test_user_structures_with_names(converter_ready):
    u = converter_ready.structure(
        {"name": "alice.smith", "first_name": "Alice", "last_name": "Smith"}, User
    )
    assert (u.first_name, u.last_name) == ("Alice", "Smith")


@pytest.fixture
def converter_ready(clean_registry):
    """A converter built against a freshly-loaded registry (see test_group_gid)."""
    from cs_image_system.base.loader import load_plugins
    from cs_image_system.base.orchestrator import Orchestrator

    load_plugins()
    return Orchestrator().get_converter()
