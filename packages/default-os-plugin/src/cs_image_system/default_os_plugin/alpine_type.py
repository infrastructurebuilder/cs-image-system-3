# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Sequence

from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # validation at construction

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

    def get_command_to_update(self) -> list[str]:
        """Full package-level update for Alpine (single packer shell script).

        --available upgrades even when packages must be replaced/downgraded to
        match the repositories — the right semantic for "bring fully current".
        """
        return [
            "sudo apk update",
            "sudo apk upgrade --available",
        ]

    # ------------------------------------------------ the package manager
    @classmethod
    def package_format(cls) -> str:
        return "apk"

    @classmethod
    def package_install_command(cls, packages: Sequence[str], *, lock_timeout: int | None = None) -> str:
        # apk has no lock-wait option; --no-cache keeps the image's index out of the layer
        return f"sudo apk add --no-cache {' '.join(packages)}"

    @classmethod
    def package_update_command(cls, *, lock_timeout: int | None = None) -> str:
        return "sudo apk update"

    @classmethod
    def package_present_check(cls, package: str) -> str:
        # exits for itself: `set -e` ignores a command in an AND-OR list
        return (f"if ! apk info -e {package} >/dev/null 2>&1; "
                f"then printf 'package %s is not installed\\n' {package} >&2; exit 1; fi")

    @classmethod
    def service_enable_command(cls, service: str) -> str:
        # OpenRC, not systemd
        return f"sudo rc-update add {service} default"

    @classmethod
    def ansible_python_install_command(cls) -> str:
        return "command -v python3 >/dev/null 2>&1 || apk add --no-cache python3"
