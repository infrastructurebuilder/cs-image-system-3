# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from .runtime_builder_item import RuntimeBuilderItemModel


CONTAINER_PROVIDER_TYPE: str = "container"


@dataclass(config=CSIS_MODEL_CONFIG)
class Container(RuntimeBuilderItemModel):
    """A  data object for a Container Provider

    Attributes
    ----------

    """

    pass
