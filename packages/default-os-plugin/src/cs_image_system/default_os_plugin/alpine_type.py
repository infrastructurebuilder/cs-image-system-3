# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.models.os_builder_model import OsBuilderModel

ALPINE_TYPE: str = "alpine"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class AlpineOsBuilderModel(OsBuilderModel):
    """Alpine OS/Source configuration data object.

    Alpine updates via apk against its default repositories. Note: official
    Alpine cloud images ship doas rather than guaranteeing sudo; if a target
    lacks sudo, this command list will need to become config-adjustable —
    sudo is used here for consistency with every other OS type.
    """
    type = ALPINE_TYPE

    @classmethod
    def csis_name(cls) -> str:
        return ALPINE_TYPE

    @classmethod
    def get_command_to_update(cls) -> list[str]:
        """Full package-level update for Alpine (single packer shell script).

        --available upgrades even when packages must be replaced/downgraded to
        match the repositories — the right semantic for "bring fully current".
        """
        return [
            "sudo apk update",
            "sudo apk upgrade --available",
        ]
