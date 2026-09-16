# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.basic.builder_base_os import OsBuilderBase
from .alpine_type import ALPINE_TYPE


class AlpineOsBuilder(OsBuilderBase):
    """Alpine specific OS builder implementation."""

    @classmethod
    def csis_name(cls) -> str:
        return ALPINE_TYPE
