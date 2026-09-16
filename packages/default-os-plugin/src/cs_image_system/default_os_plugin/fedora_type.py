# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from .dnf_type import DnfOsBuilderModel

FEDORA_TYPE: str = "fedora"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class FedoraOsBuilderModel(DnfOsBuilderModel):
    """Fedora OS/Source configuration data object.

    Unlike RHEL, Fedora needs no subscription-manager repository enablement —
    a package-level update is a plain dnf upgrade against the default repos.
    """
    type = FEDORA_TYPE

    @classmethod
    def csis_name(cls) -> str:
        return FEDORA_TYPE

    @classmethod
    def get_command_to_update(cls) -> list[str]:
        """Full package-level update for Fedora (single packer shell script)."""
        return [
            "sudo dnf clean all",
            "sudo dnf -y upgrade --refresh",
            "sudo dnf -y autoremove",
        ]
