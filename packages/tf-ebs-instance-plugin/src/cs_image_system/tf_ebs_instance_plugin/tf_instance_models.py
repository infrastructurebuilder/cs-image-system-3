# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from pydantic.dataclasses import dataclass

from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.hashicorp_utils.tofu_models import TofuInstanceBuilderModelBase

TOFU: str = "tofu"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuInstanceBuilderModel(TofuInstanceBuilderModelBase):
    """The AWS instance root's configuration (``type: tofu``): what every
    tofu instance root declares, nothing of its own."""
    type = TOFU

    @classmethod
    def csis_name(cls) -> str:
        return TOFU
