# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for base-package tests.

The kit knows a run's resolver only as its protocol
(:class:`~cs_image_system.base.run_context.TemplateResolverLike`); the
engine's resolver implements it, and the kit's tests import nothing of the
engine. `clean_registry` is a unit test's own run in miniature: a fresh,
empty registry behind a stand-in that satisfies the protocol. The stand-in
resolves and structures nothing: a test that needs a whole resolution or a
model structured by the run's converter tests the engine and lives with the
engine's tests. Nothing is shared with another test, so there is nothing to
restore afterward.
"""
from typing import Any

import pytest

from cs_image_system.base import registry as _registry
from cs_image_system.base.image_sources import ImageSourceCatalog
from cs_image_system.base.models.builder_model import ModelBinding
from cs_image_system.base.run_context import TemplateResolverLike


class StubConverter:
    """A converter that hands out its run's binding and structures nothing."""

    def __init__(self, reg: _registry.Registry) -> None:
        self._binding = ModelBinding(reg, ImageSourceCatalog(reg))

    @property
    def binding(self) -> ModelBinding:
        return self._binding

    def structure(self, data: Any, cls: Any) -> Any:
        raise NotImplementedError("the kit's stand-in structures nothing; the engine's converter does")


class StubResolver:
    """A resolver over a registry of its own: it holds the flat map and
    leaves every template as it is."""

    def __init__(self, reg: _registry.Registry) -> None:
        self._reg = reg
        self._converter = StubConverter(reg)
        self._flattened_map: dict[str, Any] = {}

    @property
    def reg(self) -> _registry.Registry:
        return self._reg

    @property
    def converter(self) -> StubConverter:
        return self._converter

    @property
    def flattened_map(self) -> dict[str, Any]:
        return self._flattened_map

    def flatten_dataclass(self, obj: Any) -> Any:
        self._flattened_map[obj.global_id] = obj
        return obj

    def resolve_all(self) -> list[tuple[str, str, str, str, str]]:
        return []


@pytest.fixture
def clean_registry() -> TemplateResolverLike:
    """A resolver over a registry of the test's own: ``.reg`` is the
    registry and ``.flattened_map`` starts empty."""
    return StubResolver(_registry.Registry())
