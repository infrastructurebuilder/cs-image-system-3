# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
import logging
log = logging.getLogger(__name__)


from .apt_type import AptOsBuilderModel



DEBIAN_TYPE: str = "debian"
UBUNTU_TYPE: str = "ubuntu"


@dataclass(config=CSIS_MODEL_CONFIG)
class DebianOsBuilderModel(AptOsBuilderModel):
    """Some Debian OS/Source configuration data object."""
    type = DEBIAN_TYPE

    @classmethod
    def csis_name(cls) -> str:
        return DEBIAN_TYPE


