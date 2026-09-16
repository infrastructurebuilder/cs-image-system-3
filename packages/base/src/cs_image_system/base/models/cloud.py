# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from .runtime_builder_item import RuntimeBuilderItemModel

CLOUD_PROVIDER_TYPE: str = "cloud"


@dataclass(config=CSIS_MODEL_CONFIG)
class Cloud(RuntimeBuilderItemModel):
    """A group data object.

    Attributes
    ----------

    """

    pass
