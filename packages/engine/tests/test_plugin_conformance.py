# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The engine's loader refuses a plugin whose classes do not conform.

The kit's registry takes what a plugin registers
(``packages/base/tests/test_plugin_registration.py``); the loader holds
each class to the contract's protocol for its classification first.
"""
import types
from typing import Any, cast


class FakeBuilder:
    pass


def test_a_plugin_that_does_not_conform_is_refused_at_load():
    """The loader holds every class a plugin registers to the
    contract's protocol for its classification (``protocol_for``) when it
    discovers the installed plugins, so a builder that lacks a hook is
    refused with the plugin, the class, the protocol and the member named
    -- not later, with an ``AttributeError`` from whatever first calls the
    hook."""
    import pytest

    from cs_image_system.base.basic.builder_base_storage import StorageBuilderBase
    from cs_image_system.base.models.storage_builder import StorageBuilderModel
    from cs_image_system.engine.loader import PluginConformanceError, check_conformance

    class HalfModel(StorageBuilderModel):
        @classmethod
        def csis_name(cls):
            return "half"

    class HalfBuilder(StorageBuilderBase):
        @classmethod
        def csis_name(cls):
            return "half"
        # the builder protocol's launch hooks, answered by a method of the wrong shape
        def launch_mount(self, storage):  # pyright: ignore[reportIncompatibleMethodOverride] -- the protocol's takes (storage, mapping, index)
            return {}
        query_state = "not a method"  # pyright: ignore[reportAssignmentType]

    md = types.SimpleNamespace(services={"half": [HalfModel, HalfBuilder]},
                               builders_for_models={HalfModel: HalfBuilder},
                               injected_models={}, is_injected_models_default=False, namespace="half")
    with pytest.raises(PluginConformanceError) as refused:
        check_conformance("half-plugin", cast(Any, md))
    message = str(refused.value)
    assert "Plugin half-plugin is refused" in message
    assert "HalfBuilder does not conform to StorageBuilderProtocol" in message
    assert "launch_mount: lacks parameter 'mapping'" in message
    assert "query_state: the protocol declares a method, the class holds str" in message
    assert "HalfModel" not in message, "the conforming model is not named"

    # a class under a classification the contract declares no protocol for
    # (an injected item model) is held only to PluginArtifactProtocol
    with pytest.raises(PluginConformanceError, match="names no csis_name/csis_classifier"):
        check_conformance("nameless", cast(Any, types.SimpleNamespace(
            services={"x": [FakeBuilder]}, builders_for_models={}, injected_models={},
            is_injected_models_default=False, namespace="nameless")))
