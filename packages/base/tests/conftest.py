# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for base-package tests.

`TemplateResolver` is a process-wide singleton; the registry is one per run
since stage 124 (the loader makes it), and what a model or a builder without
a bound context reads is the process's current one. `clean_registry` binds a
fresh, empty registry as the current one for the test and restores the
previous binding afterward so unit tests don't leak into each other (or
into the end-to-end pipeline test).
"""
import pytest

from cs_image_system.base import registry as _registry
from cs_image_system.base.orchestrator import TemplateResolver, Orchestrator

@pytest.fixture
def clean_registry():
    previous = _registry.current_registry()
    _registry.bind_current_registry(_registry.Registry())   # fresh, empty, and what the test's models read

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
        _registry.bind_current_registry(previous)
        tr.flattened_map = tr_snap
        Orchestrator().invalidate_converter()
