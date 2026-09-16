# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Registry lifecycle (state is instance-level; reset() clears it)."""
from typing import Any, cast

from cs_image_system.base import registry as _registry
from cs_image_system.base.constants import VCT


def test_registry_is_singleton():
    assert _registry.Registry() is _registry.Registry()


def test_reset_clears_registered_state(clean_registry):
    reg = _registry.Registry()

    reg.models[VCT.STORAGE_MODEL]["thing"] = cast(Any, object)
    reg.instances[VCT.STORAGE_MODEL]["thing"] = object()
    assert reg.get_model(VCT.STORAGE_MODEL, "thing") is not None

    reg.reset()

    # All registered state is gone, and the per-VCT dicts are rebuilt (present + empty).
    assert reg.get_model(VCT.STORAGE_MODEL, "thing") is None
    assert reg.instances[VCT.STORAGE_MODEL] == {}
    assert set(reg.instances.keys()) == set(VCT)
