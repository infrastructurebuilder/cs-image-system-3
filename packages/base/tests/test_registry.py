# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Registry lifecycle (state is instance-level; reset() clears it)."""
from typing import Any, cast

from cs_image_system.base import registry as _registry
from cs_image_system.contract.constants import VCT


def test_a_registry_is_per_run_and_the_process_holds_the_bound_one():
    # stage 124: two constructions are two registries; the shim answers with
    # the one bound last, and makes one when none is
    assert _registry.Registry() is not _registry.Registry()
    previous = _registry.current_registry()
    try:
        mine = _registry.Registry()
        _registry.bind_current_registry(mine)
        assert _registry.current_registry() is mine
        _registry.bind_current_registry(None)
        assert _registry.current_registry() is not mine
    finally:
        _registry.bind_current_registry(previous)


def test_reset_clears_registered_state(clean_registry):
    reg = _registry.current_registry()

    reg.models[VCT.STORAGE_MODEL]["thing"] = cast(Any, object)
    reg.instances[VCT.STORAGE_MODEL]["thing"] = object()
    assert reg.get_model(VCT.STORAGE_MODEL, "thing") is not None

    reg.reset()

    # All registered state is gone, and the per-VCT dicts are rebuilt (present + empty).
    assert reg.get_model(VCT.STORAGE_MODEL, "thing") is None
    assert reg.instances[VCT.STORAGE_MODEL] == {}
    assert set(reg.instances.keys()) == set(VCT)
