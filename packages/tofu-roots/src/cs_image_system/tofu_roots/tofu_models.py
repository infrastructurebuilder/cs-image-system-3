# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The provider-neutral models of a terraform root.

An instance root and a storage root are one terraform workspace each,
driven by OpenTofu, bound to a state manager by reference and extended by
the provider plugins they require. What every such root declares --
the executable, the required provider plugins, the state manager, the
module inputs -- is here; what a cloud or a daemon adds (a bucket name,
a volume driver) is declared by the provider's own subclass, and the
``type:`` a tree writes is the subclass's, never one of these.
"""
from dataclasses import field

from pydantic.dataclasses import dataclass

from cs_image_system.base.models.instance_builder import InstanceBuilderModel
from cs_image_system.base.models.module_variables import ModuleVariables
from cs_image_system.base.models.storage_builder import StorageBuilderModel
from cs_image_system.contract.constants import DEFAULT, VCT
from cs_image_system.contract.fields import fk_field
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG

from cs_image_system.hashicorp_utils.hashicorp_models import TFTofuPluginModel

TOFU_EXECUTABLE = "tofu"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuInstanceBuilderModelBase(InstanceBuilderModel):
    """What an instance root declares whatever its provider: the OpenTofu
    executable, the provider plugins the root requires (the provider's
    default when none) and the state manager its workspace is bound to."""
    executable: str | None = TOFU_EXECUTABLE
    required_plugins: list[TFTofuPluginModel] = field(default_factory=list)
    state_configuration: str = fk_field(target=VCT.STATE_BACKEND_MODEL,
                                        default=DEFAULT, metadata={
        "description": "State backend used for this builder's terraform workspace",
    })


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuStorageBuilderModelBase(StorageBuilderModel):
    """What a storage root declares whatever its provider: the OpenTofu
    executable, the required provider plugins, the state manager, and the
    declared inputs to the module call (``variables``), which each provider
    narrows to its module's own tunables."""
    executable: str | None = TOFU_EXECUTABLE
    required_plugins: list[TFTofuPluginModel] = field(default_factory=list)
    state_configuration: str = fk_field(target=VCT.STATE_BACKEND_MODEL,
                                        default=DEFAULT, metadata={
        "description": "State backend used for this builder's terraform workspace",
    })
    variables: ModuleVariables = field(default_factory=ModuleVariables)
