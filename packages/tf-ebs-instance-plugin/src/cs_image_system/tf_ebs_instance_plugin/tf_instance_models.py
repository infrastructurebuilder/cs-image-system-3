# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.constants import DEFAULT, VCT
from cs_image_system.base.helpers.field_helpers import fk_field
from cs_image_system.base.models.instance_builder import InstanceBuilderModel
from cs_image_system.hashicorp_utils.hashicorp_models import TFTofuPluginModel

TOFU: str = "tofu"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuInstanceBuilderModel(InstanceBuilderModel):
    """OpenTofu IaC builder configuration data object."""
    type = TOFU
    executable: str | None = "tofu"
    required_plugins: list[TFTofuPluginModel] = field(default_factory=list)
    state_configuration: str = fk_field(target=VCT.STATE_BACKEND_MODEL,
                                        default=DEFAULT, metadata={
        "description": "State backend used for this builder's terraform workspace",
    })


    @classmethod
    def csis_name(cls) -> str:
        return TOFU
