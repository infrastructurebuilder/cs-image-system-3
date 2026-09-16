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

    @classmethod
    def get_command_to_update(cls) -> list[str]:
        """Full package-level update for apt systems (single packer shell script)."""
        return [
            "sudo -s -- <<EOF",
            "apt-get update",
            "apt-get upgrade -y",
            "apt-get full-upgrade -y",
            "apt-get autoremove -y",
            "apt-get autoclean -y",
            "EOF",
        ]

    def commands_for_policy(self, policy: UpdatePolicy) -> list[str]:
        if policy.policy == POLICY_NONE and not policy.pin:
            return []
        cmds = ["sudo apt-get update"]
        for e in policy.exclude:
            cmds.append(f"sudo apt-mark hold '{e}'")
        if policy.policy == POLICY_SECURITY:
            # only upgrades whose candidate comes from a *-security suite
            cmds.append("sudo apt-get -s dist-upgrade | awk '/^Inst/ && /security/ {print $2}' | xargs -r sudo apt-get install -y --only-upgrade")
            if policy.packages:
                cmds.append("sudo apt-get install -y --only-upgrade " + " ".join(policy.packages))
        elif policy.policy == POLICY_PACKAGES:
            if policy.packages:
                cmds.append("sudo apt-get install -y --only-upgrade " + " ".join(policy.packages))
        elif policy.policy == POLICY_FULL:
            cmds += ["sudo apt-get upgrade -y", "sudo apt-get full-upgrade -y",
                     "sudo apt-get autoremove -y", "sudo apt-get autoclean -y"]
        for pkg, ver in policy.pin:
            cmds.append(f"sudo apt-get install -y --allow-downgrades '{pkg}={ver}' && sudo apt-mark hold '{pkg}'")
        for e in policy.exclude:
            cmds.append(f"sudo apt-mark unhold '{e}'")
        return cmds
