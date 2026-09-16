# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction





from .dnf_type import DnfOsBuilderModel

RHEL_TYPE:str = "rhel"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class RhelOsBuilderModel(DnfOsBuilderModel):
    """RHEL 8 OS/Source configuration data object."""
    type = RHEL_TYPE
    subscription_id: str | None = None
    
    @classmethod
    def csis_name(cls) -> str:
        return RHEL_TYPE

    def repo_setup_commands(self) -> list[str]:
        """Version-aware repository setup (RHEL 8/9/10 enable different repos).

        Guarded on registration (found live, TODO stage 1: cloud vendor
        RHEL AMIs are pay-as-you-go/RHUI, "This system is not yet
        registered" -- their RHUI repos already serve baseos/appstream and
        security metadata, so on an unregistered system this is a no-op)."""
        v = self.version()
        if not v:
            raise ValueError(f"Could not determine RHEL version from family_version '{self.family_version}' in OS builder {self.name}")
        if v.major not in (8, 9, 10):        # EL10 since stage 13 (AlmaLinux 10 on both clouds)
            raise ValueError(f"Unsupported RHEL version '{v}' in OS builder {self.name}")
        repos = " ".join(f"--enable='rhel-{v.major}-for-x86_64-{r}-rpms'" for r in ("baseos", "appstream"))             + f" --enable='codeready-builder-for-rhel-{v.major}-x86_64-rpms'"
        return [
            "# subscription-managed systems get their repos enabled; RHUI/PAYG images skip",
            ("if sudo subscription-manager identity >/dev/null 2>&1; then "
             "sudo subscription-manager refresh; "
             "sudo subscription-manager repos --disable='*'; "
             f"sudo subscription-manager repos {repos}; "
             "else echo 'not subscription-registered (RHUI image): using vendor repos as-is'; fi"),
        ]

    def commands_to_update(self) -> list[str]:
        """Full update (policy 'full'): repos + dnf update/upgrade/autoremove."""
        from cs_image_system.base.models.update_policy import POLICY_FULL, UpdatePolicy
        return self.commands_for_policy(UpdatePolicy(policy=POLICY_FULL))


    def get_command_to_update(self) -> list[str]:
        """Version-aware update commands (RHEL 8/9 enable different repos)."""
        return self.commands_to_update()
