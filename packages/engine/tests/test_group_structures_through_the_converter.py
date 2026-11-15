# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A Group structures through the run's converter.

The kit normalizes a gid (``packages/base/tests/test_group_gid.py``); the
engine's converter, with the installed plugins loaded, structures the
mapping a YAML file holds into a Group: a gid of each accepted spelling, an
absent gid, a refused gid, and a valueless collection key.
"""
import pytest

from cs_image_system.base.models.group import Group
from cs_image_system.contract.constants import DEFAULT

# ---------------------------------------------------------------------------
# Converter hooks: gid's `str | int | None` union and empty YAML collections.
# Both of these blew up inside cattrs before __post_init__ ever ran.
# ---------------------------------------------------------------------------


@pytest.fixture
def converter(clean_registry):
    """The converter of a registry of the test's own, the installed plugins
    loaded into it (`clean_registry`, see conftest)."""
    from cs_image_system.engine.loader import load_plugins

    load_plugins(clean_registry.reg)
    return clean_registry.converter


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, None), (0, None), ("0", None), (DEFAULT, None), (2048, 2048), ("2048", 2048)],
)
def test_gid_structures_through_converter(converter, raw, expected):
    """Regression: `str | int | None` had no structure hook, so Group wouldn't structure."""
    grp = converter.structure({"name": "tcmet", "gid": raw}, Group)
    assert grp.gid == expected


def test_gid_absent_structures_through_converter(converter):
    assert converter.structure({"name": "tcmet"}, Group).gid is None


@pytest.mark.parametrize("bad", [500, "nope"])
def test_converter_rejects_invalid_gid(converter, bad):
    # the contract is that the converter REFUSES and says why, not
    # which library's wrapper carries it. The mapper is pydantic now, so the
    # model's own message arrives inside a ValidationError; assert the message.
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="gid"):
        converter.structure({"name": "tcmet", "gid": bad}, Group)


def test_valueless_yaml_collection_keys_structure_as_empty(converter):
    """A bare `members:` in YAML parses to None; it must read as the empty set."""
    grp = converter.structure(
        {"name": "tcmet", "members": None, "admins": ["avery.alpha"]}, Group
    )
    assert grp.members == set()
    assert grp.admins == {"avery.alpha"}
