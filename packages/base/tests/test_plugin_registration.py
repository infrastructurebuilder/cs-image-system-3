# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Contract test for the plugin extension surface.

This pins `Registry.register_plugin_metadata` (services / builders_for_models /
injected_models) so later refactors cannot silently narrow how plugins register
models and builders. If a future phase touches the extension surface, this test
must be updated deliberately, not by accident.
"""
import types
from typing import Any, cast

from cs_image_system.base import registry as _registry
from cs_image_system.contract.constants import VCT


class FakeModel:
    @classmethod
    def csis_name(cls): return "fake-thing"
    @classmethod
    def csis_classifier(cls): return VCT.STORAGE_BUILDER_MODEL


class FakeBuilder:
    pass


class FakeInjected:
    @classmethod
    def csis_name(cls): return "fake-injected"
    @classmethod
    def csis_classifier(cls): return VCT.STORAGE_MODEL


def _fake_metadata(namespace: str | None = None):
    return types.SimpleNamespace(
        services={"storage": [FakeModel]},
        builders_for_models={FakeModel: FakeBuilder},
        injected_models={VCT.STORAGE_MODEL: FakeInjected},
        is_injected_models_default=True,
        namespace=namespace,
    )


def test_register_plugin_metadata_registers_model_builder_and_injected(clean_registry):
    reg = clean_registry.reg
    # in-process metadata has no distribution behind it: the namespace is passed
    reg.register_plugin_metadata(cast(Any, _fake_metadata()), namespace="fake")

    # Service model is registered under its (sanitized) classifier, the
    # namespace and the canonical name; the bare word and the qualified
    # form both read it.
    assert reg.get_model(VCT.STORAGE_BUILDER_MODEL, "fake-thing") is FakeModel
    assert reg.get_model(VCT.STORAGE_BUILDER_MODEL, "fake/fake-thing") is FakeModel
    assert reg.get_model(VCT.STORAGE_BUILDER_MODEL, "other/fake-thing") is None
    assert _registry.RegistrationKey(VCT.STORAGE_BUILDER_MODEL, "fake", "fake-thing") in reg.models
    # Builder wired to the model (`get_builder` had no production
    # caller and is gone; the map itself is what the template's shape shows).
    assert reg.builders[cast(Any, FakeModel)] is FakeBuilder
    # Injected model registered and set as default for its classifier.
    assert reg.get_model(VCT.STORAGE_MODEL, "fake-injected") is FakeInjected
    assert reg.get_default_for(VCT.STORAGE_MODEL) == "fake-injected"


def test_metadata_without_a_namespace_is_refused_unless_it_names_one(clean_registry):
    import pytest
    reg = clean_registry.reg
    with pytest.raises(ValueError, match="PluginMetadata.namespace"):
        reg.register_plugin_metadata(cast(Any, _fake_metadata()))
    reg.register_plugin_metadata(cast(Any, _fake_metadata(namespace="named")))
    assert reg.get_model(VCT.STORAGE_BUILDER_MODEL, "named/fake-thing") is FakeModel

