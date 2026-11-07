# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # validation at construction

from .runtime_builder_item import RuntimeBuilderItemModel
# one spelling, the contract's (base said "container" while the
# contract said "container_provider"; nothing read either)
from cs_image_system.contract.constants import CONTAINER_PROVIDER_TYPE  # noqa: F401


@dataclass(config=CSIS_MODEL_CONFIG)
class Container(RuntimeBuilderItemModel):
    """A  data object for a Container Provider

    Attributes
    ----------

    """

    pass
