# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.default_os_plugin.apt_type import AptOsBuilderModel

UBUNTU_TYPE: str = "ubuntu"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
# @registry.register_class_to_type_and_key(type_=OS_BUILDER_MODEL, key=UBUNTU_TYPE)
class UbuntuOsBuilderModel(AptOsBuilderModel):
    """Some Ubuntu OS/Source configuration data object."""
    type = UBUNTU_TYPE

    @classmethod
    def csis_name(cls) -> str:
        return UBUNTU_TYPE

