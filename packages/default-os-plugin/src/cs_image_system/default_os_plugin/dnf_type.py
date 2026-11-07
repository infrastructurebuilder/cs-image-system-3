# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Sequence

from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.base.models.os_builder_model import OsBuilderModel
from cs_image_system.base.models.update_policy import (
    POLICY_FULL,
    POLICY_NONE,
    POLICY_PACKAGES,
    POLICY_SECURITY,
    UpdatePolicy,
)
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG

from .helpers import rpm_or_dpkg_present_check


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DnfOsBuilderModel(OsBuilderModel):
    """dnf-managed families. Subclasses supply ``repo_setup_commands`` (e.g.
    subscription-manager on RHEL); the update policy is realized here
    (EXPLORE "More Targeted Updates?")."""

    def repo_setup_commands(self) -> list[str]:
        return []

    # ------------------------------------------------ the package manager
    # The bake lines say `yum`: the compatibility name every supported
    # release (EL 8, 9, 10; fedora) answers to, and the one every bake
    # carried before the type owned them. The update policy above says
    # `dnf`; one name for both is a later decision.
    @classmethod
    def package_format(cls) -> str:
        return "rpm"

    @classmethod
    def package_install_command(cls, packages: Sequence[str], *, lock_timeout: int | None = None) -> str:
        # no lock option: dnf waits for the rpm database on its own
        return f"sudo yum install -y {' '.join(packages)}"

    @classmethod
    def package_update_command(cls, *, lock_timeout: int | None = None) -> str:
        return "sudo yum -y makecache"

    @classmethod
    def package_present_check(cls, package: str) -> str:
        return rpm_or_dpkg_present_check(package)

    @classmethod
    def service_enable_command(cls, service: str) -> str:
        return f"sudo systemctl enable {service}"

    @classmethod
    def ansible_python_install_command(cls) -> str:
        # ansible needs a python its controller supports and EL8-era images
        # ship 3.6: install the newest python3.x the release offers, else
        # whatever python3 is (yum where an image has no dnf)
        return ("for v in 3.12 3.11 3.9; do command -v python$v >/dev/null 2>&1 && exit 0; "
                "dnf -y install python$v >/dev/null 2>&1 && exit 0; done; "
                "command -v python3 >/dev/null 2>&1 || dnf -y install python3 || yum -y install python3")

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
