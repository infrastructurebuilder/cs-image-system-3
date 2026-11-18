# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The example plugin satisfies the contract's protocols structurally: its
model, its builder and its backend kind conform, and so does everything its
metadata registers, by the same check the loader applies to a discovered
plugin. Kept with the example plugin, so the contract's own tests need
nothing but the contract."""
from __future__ import annotations

from cs_image_system.contract import state
from cs_image_system.contract.testing import assert_conforms, conformance_problems, protocol_for


def test_the_example_plugin_satisfies_the_protocols_structurally():
    from cs_image_system.contract_example_plugin.builder import InmemStateBuilder
    from cs_image_system.contract_example_plugin.main import initialize
    from cs_image_system.contract_example_plugin.models import InmemBackendKind, InmemStateBackendModel
    assert_conforms(InmemStateBackendModel, state.StateBackendModelProtocol)
    assert_conforms(InmemStateBuilder, state.StateBuilderProtocol)
    assert_conforms(InmemBackendKind, state.BackendKindProtocol)
    # what the loader holds a discovered plugin to, applied to the example's own metadata
    metadata = initialize()
    checked = 0
    for services in metadata.services.values():
        for service in services:
            protocol = protocol_for(service.csis_classifier())
            if protocol is not None:
                assert conformance_problems(service, protocol) == [], service
                checked += 1
    for model_cls, builder_cls in metadata.builders_for_models.items():
        assert conformance_problems(builder_cls, state.StateBuilderProtocol) == [], builder_cls
        assert conformance_problems(model_cls, state.StateBackendModelProtocol) == [], model_cls
        checked += 1
    assert checked >= 1, "the example plugin registers nothing"
