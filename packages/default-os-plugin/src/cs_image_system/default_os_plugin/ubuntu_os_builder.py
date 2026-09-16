# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar

from cs_image_system.base.basic.builder_base_os import OsBuilderBase
from .ubuntu_os_type import UbuntuOsBuilderModel, UBUNTU_TYPE



UBUOS = TypeVar('UBUOS', bound=UbuntuOsBuilderModel)
# @registry.register_class_to_type_and_key(type_=OS_BUILDER, key=UBUNTU_TYPE)
class UbuntuOsBuilder(OsBuilderBase[UBUOS]):
    """Ansible-based modification provider implementation."""

    @classmethod
    def csis_name(cls) -> str:
        return UBUNTU_TYPE
