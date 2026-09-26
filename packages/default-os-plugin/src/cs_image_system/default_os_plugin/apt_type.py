# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.os_builder_model import OsBuilderModel
from cs_image_system.base.models.update_policy import (
    POLICY_FULL,
    POLICY_NONE,
    POLICY_PACKAGES,
    POLICY_SECURITY,
    UpdatePolicy,
)


class AptOsBuilderModel(OsBuilderModel):
    """Base model for apt-managed OS families (debian, ubuntu)."""

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
