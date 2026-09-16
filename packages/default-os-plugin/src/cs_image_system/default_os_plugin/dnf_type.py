# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.models.os_builder_model import OsBuilderModel
from cs_image_system.base.models.update_policy import (
    POLICY_FULL,
    POLICY_NONE,
    POLICY_PACKAGES,
    POLICY_SECURITY,
    UpdatePolicy,
)


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DnfOsBuilderModel(OsBuilderModel):
    """dnf-managed families. Subclasses supply ``repo_setup_commands`` (e.g.
    subscription-manager on RHEL); the update policy is realized here
    (EXPLORE "More Targeted Updates?")."""

    def repo_setup_commands(self) -> list[str]:
        return []

    def commands_for_policy(self, policy: UpdatePolicy) -> list[str]:
        if policy.policy == POLICY_NONE and not policy.pin:
            return []
        cmds = list(self.repo_setup_commands()) + ["sudo dnf clean all"]
        excl = "".join(f" --exclude={e}" for e in policy.exclude)

        def retried(cmd: str) -> str:
            # RHUI repos flip their cache path mid-run when the point release
            # moves (found live twice: Errno 2 on a downloaded rpm); a clean
            # retry re-resolves against the new cache
            return f"{cmd} || {{ sudo dnf clean all; {cmd}; }}"

        def targeted(pkgs: str) -> str:
            # dnf5 (EL10; found live on the first Alma 10 bake) exits 1 on
            # `update <pkg>` when the named package has no pending update
            # ("No packages marked for upgrade") where dnf4 exited 0.
            # check-update keeps stable exit semantics on both (100 =
            # updates exist, 0 = none), so the update runs only behind it;
            # the rc dance keeps the line safe under packer's /bin/sh -e.
            check = f"sudo dnf -q check-update{excl} {pkgs}"
            update = retried(f"sudo dnf -y update{excl} {pkgs}")
            return (f'rc=0; {check} || rc=$?; if [ "$rc" -eq 100 ]; then {update}; '
                    f'elif [ "$rc" -ne 0 ]; then exit "$rc"; fi')

        if policy.policy == POLICY_SECURITY:
            cmds.append(retried(f"sudo dnf -y update --security{excl}"))
            if policy.packages:
                cmds.append(targeted(" ".join(policy.packages)))
        elif policy.policy == POLICY_PACKAGES:
            if policy.packages:
                cmds.append(targeted(" ".join(policy.packages)))
        elif policy.policy == POLICY_FULL:
            cmds += [retried(f"sudo dnf -y upgrade{excl}"),
                     "sudo dnf -y autoremove", "sudo dnf -y autoclean"]
        if policy.pin:
            cmds.append("sudo dnf -y install python3-dnf-plugin-versionlock || sudo dnf -y install dnf-plugins-core")
            for pkg, ver in policy.pin:
                cmds.append(f"sudo dnf -y install '{pkg}-{ver}' && sudo dnf versionlock add '{pkg}-{ver}'")
        return cmds
