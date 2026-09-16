# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for base-package tests.

`Registry` and `TemplateResolver` are process-wide singletons. `clean_registry`
snapshots the registry's (instance-level) state, resets it for the test, and
restores it afterward so unit tests don't leak into each other (or into the
end-to-end pipeline test).
"""
import pytest

from cs_image_system.base import registry as _registry
from cs_image_system.base.orchestrator import TemplateResolver, Orchestrator

_REG_ATTRS = [
    "registry", "vct_type_registry", "reverse_registry", "builder_for_model",
    "aliases", "classified_aliases", "defaults_registry", "instances",
    "instances_by_global_id", "models", "builders",
]


@pytest.fixture
def clean_registry():
    reg = _registry.Registry()  # the singleton instance (state lives here now)
    snap = {a: getattr(reg, a) for a in _REG_ATTRS}
    reg.reset()  # fresh empty state for this test

    tr = TemplateResolver()
    tr_snap = tr.flattened_map
    tr.flattened_map = {}
    # The cattrs converter is memoized on the Orchestrator singleton; drop it so the
    # test builds one against this (reset) registry, and again on teardown so later
    # tests / the e2e pipeline rebuild against the restored registry.
    Orchestrator().invalidate_converter()
    try:
        yield tr
    finally:
        for a, v in snap.items():
            setattr(reg, a, v)
        tr.flattened_map = tr_snap
        Orchestrator().invalidate_converter()
