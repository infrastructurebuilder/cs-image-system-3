# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

log = logging.getLogger(__name__)

from typing import TypeVar


from .debian_type import DEBIAN_TYPE, DebianOsBuilderModel
from cs_image_system.base.basic.builder_base_os import OsBuilderBase


DEBSOS = TypeVar('DEBSOS', bound=DebianOsBuilderModel)
class DebianOsBuilder(OsBuilderBase[DEBSOS]):
    """Ansible-based modification provider implementation."""
    
    @classmethod
    def csis_name(cls) -> str:
        return DEBIAN_TYPE

