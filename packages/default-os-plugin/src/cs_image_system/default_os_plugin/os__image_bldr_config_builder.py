# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar

from cs_image_system.base.basic.builder_base_os import OsRuntimeConfigBuilderBase
from cs_image_system.base.models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig

    
DEFAULT_RTCB = TypeVar('DEFAULT_RTCB', bound=OSBuilderBaseImageBuilderSubconfig)
class DefaultOSImageBuilderConfigBuilder(OsRuntimeConfigBuilderBase[DEFAULT_RTCB]):
    """Default OS runtime config builder implementation."""
    
    @classmethod
    def csis_name(cls) -> str:
        return "default_os_runtime_config_builder"
