# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for Group.gid normalization.

A gid of None, 0 or DEFAULT all mean "we create the group on the far side, so
adopt whatever gid it ends up with"; they normalize to None.  Anything else must
resolve to an int of at least Group.MIN_GID.
"""
import pytest

from cs_image_system.base.constants import DEFAULT
from cs_image_system.base.models.group import Group


def _group(**kwargs) -> Group:
    return Group(name="tcmet", **kwargs)


@pytest.mark.parametrize("raw", [None, 0, "0", DEFAULT, f"  {DEFAULT}  ", "", "   "])
def test_deferred_gids_normalize_to_none(raw):
    grp = _group(gid=raw)
    assert grp.gid is None
    assert grp.gid_is_deferred


def test_gid_defaults_to_deferred():
    assert _group().gid is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(1024, 1024), (2048, 2048), ("1024", 1024), ("2048", 2048), (" 2048 ", 2048)],
)
def test_valid_gids_coerce_to_int(raw, expected):
    grp = _group(gid=raw)
    assert grp.gid == expected
    assert isinstance(grp.gid, int)
    assert not grp.gid_is_deferred


@pytest.mark.parametrize("raw", [1, 1023, 500, "1023", "1"])
def test_gids_below_min_are_rejected(raw):
    with pytest.raises(ValueError, match="at least 1024"):
        _group(gid=raw)


@pytest.mark.parametrize("raw", [-1, -2048, "-2048"])
def test_negative_gids_are_rejected(raw):
    with pytest.raises(ValueError):
        _group(gid=raw)


@pytest.mark.parametrize("raw", ["nope", "20 48", "2048x", "0x800", "1_024", "2048.0"])
def test_non_numeric_gids_are_rejected(raw):
    with pytest.raises(ValueError, match="gid must be"):
        _group(gid=raw)


# ---------------------------------------------------------------------------
# Converter hooks: gid's `str | int | None` union and empty YAML collections.
# Both of these blew up inside cattrs before __post_init__ ever ran.
# ---------------------------------------------------------------------------


@pytest.fixture
def converter(clean_registry):
    """A converter built against a freshly-loaded registry.

    `load_plugins` raises "Type Collision" if the registry is already populated,
    so this leans on `clean_registry` (see conftest) to reset the singleton first
    and restore it afterward.
    """
    from cs_image_system.base.loader import load_plugins
    from cs_image_system.base.orchestrator import Orchestrator

    load_plugins()
    return Orchestrator().get_converter()


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
    # stage 23: the contract is that the converter REFUSES and says why, not
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
