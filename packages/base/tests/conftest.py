# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for base-package tests.

The registry and the template resolver are one per run (the loader makes
them), and a model reads the registry of the run that structured it.
`clean_registry` is a unit test's own run in miniature: a fresh, empty
registry, a resolver over it and the converter that binds a model to it.
Nothing is shared with another test or with the end-to-end pipeline test,
so there is nothing to restore afterward.
"""
import pytest

from cs_image_system.base import registry as _registry
from cs_image_system.base.orchestrator import TemplateResolver


@pytest.fixture
def clean_registry() -> TemplateResolver:
    """A resolver over a registry of the test's own: ``.reg`` is the
    registry, ``.converter`` structures a model bound to it, and
    ``.flattened_map`` starts empty."""
    return TemplateResolver(_registry.Registry())
