# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar

from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
from cs_image_system.base.models.container_builder import ContainerBuilderModel
from ..models.container import Container


TC = TypeVar("TC", bound=ContainerBuilderModel)
ContainerT = TypeVar("ContainerT", bound=Container)


class ContainerBuilderBase(RuntimeBuilderBase[TC]):
    """Base class for Container providers."""
