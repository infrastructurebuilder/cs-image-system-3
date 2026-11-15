# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A User structures through the run's converter only with both names.

The kit pins ``first_name`` and ``last_name`` as required data
(``packages/base/tests/test_user_required_names.py``); the engine's
converter, with the installed plugins loaded, refuses a mapping that lacks
them and structures one that holds both.
"""
import pytest

from cs_image_system.base.models.user import User


def test_user_missing_names_fails_to_structure(converter_ready):
    """YAML without first_name/last_name must fail structuring (the mapper
    is pydantic, so the refusal arrives as its ValidationError)."""
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
    """The converter of a registry of the test's own, plugins loaded
    (see test_group_structures_through_the_converter)."""
    from cs_image_system.engine.loader import load_plugins

    load_plugins(clean_registry.reg)
    return clean_registry.converter
