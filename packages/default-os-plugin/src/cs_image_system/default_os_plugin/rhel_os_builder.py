# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.basic.builder_base_os import OsBuilderBase
from .rhel_type import RHEL_TYPE


# @registry.register_class_to_type_and_key(type_=OS_BUILDER, key=RHEL_TYPE)
class RhelOsBuilder(OsBuilderBase):
    """RHEL 8 specific Ansible-based modification provider implementation."""

    @classmethod
    def csis_name(cls) -> str:
        return RHEL_TYPE
