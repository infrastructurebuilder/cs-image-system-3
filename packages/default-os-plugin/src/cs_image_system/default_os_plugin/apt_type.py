# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Sequence

from cs_image_system.base.models.os_builder_model import OsBuilderModel
from cs_image_system.base.models.update_policy import (
    POLICY_FULL,
    POLICY_NONE,
    POLICY_PACKAGES,
    POLICY_SECURITY,
    UpdatePolicy,
)

from .helpers import rpm_or_dpkg_present_check


class AptOsBuilderModel(OsBuilderModel):
    """Base model for apt-managed OS families (debian, ubuntu)."""

    # ------------------------------------------------ the package manager
    @classmethod
    def package_format(cls) -> str:
        return "deb"

    @classmethod
    def _apt_get(cls, lock_timeout: int | None) -> str:
        # the lock option waits for a freshly booted machine's own updater
        # instead of failing on the lock; None is apt-get's own default
        return "sudo apt-get" + (f" -o DPkg::Lock::Timeout={lock_timeout}" if lock_timeout is not None else "")

    @classmethod
    def package_install_command(cls, packages: Sequence[str], *, lock_timeout: int | None = None) -> str:
        return f"{cls._apt_get(lock_timeout)} install -y {' '.join(packages)}"

    @classmethod
    def package_update_command(cls, *, lock_timeout: int | None = None) -> str:
        return f"{cls._apt_get(lock_timeout)} update -y"

    @classmethod
    def package_present_check(cls, package: str) -> str:
        return rpm_or_dpkg_present_check(package)

    @classmethod
    def service_enable_command(cls, service: str) -> str:
        return f"sudo systemctl enable {service}"

    @classmethod
    def ansible_python_install_command(cls) -> str:
        # a bare image has no python at all; the distribution's python3 is
        # new enough for ansible on every supported release
        return "command -v python3 >/dev/null 2>&1 || (apt-get update && apt-get install -y python3)"

    def commands_for_policy(self, policy: UpdatePolicy) -> list[str]:
        if policy.policy == POLICY_NONE and not policy.pin:
            return []
        cmds = ["sudo apt-get -o DPkg::Lock::Timeout=600 update"]
        for e in policy.exclude:
            cmds.append(f"sudo apt-mark hold '{e}'")
        if policy.policy == POLICY_SECURITY:
            # only upgrades whose candidate comes from a *-security suite
            cmds.append("sudo apt-get -o DPkg::Lock::Timeout=600 -s dist-upgrade | awk '/^Inst/ && /security/ {print $2}' | xargs -r sudo apt-get -o DPkg::Lock::Timeout=600 install -y --only-upgrade")
            if policy.packages:
                cmds.append("sudo apt-get -o DPkg::Lock::Timeout=600 install -y --only-upgrade " + " ".join(policy.packages))
        elif policy.policy == POLICY_PACKAGES:
            if policy.packages:
                cmds.append("sudo apt-get -o DPkg::Lock::Timeout=600 install -y --only-upgrade " + " ".join(policy.packages))
        elif policy.policy == POLICY_FULL:
            cmds += ["sudo apt-get -o DPkg::Lock::Timeout=600 upgrade -y", "sudo apt-get -o DPkg::Lock::Timeout=600 full-upgrade -y",
                     "sudo apt-get -o DPkg::Lock::Timeout=600 autoremove -y", "sudo apt-get -o DPkg::Lock::Timeout=600 autoclean -y"]
        for pkg, ver in policy.pin:
            cmds.append(f"sudo apt-get -o DPkg::Lock::Timeout=600 install -y --allow-downgrades '{pkg}={ver}' && sudo apt-mark hold '{pkg}'")
        for e in policy.exclude:
            cmds.append(f"sudo apt-mark unhold '{e}'")
        return cmds
