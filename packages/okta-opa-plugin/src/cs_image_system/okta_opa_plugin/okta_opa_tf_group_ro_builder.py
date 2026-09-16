# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Read-only group provider via Terraform/Tofu for existing Okta groups.

Emits ONLY ``data "okta_group"`` lookups via the okta/okta provider -- never
creates groups or module calls. The oktapam provider has no group data source,
so read-only instances declare okta/okta in required_providers.
"""

import logging

from cs_image_system.base.basic.asset import AssetSet
from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
from cs_image_system.base.models.executable_adds import CFExecutables
from cs_image_system.base.models.group import Group
from cs_image_system.hashicorp_utils.collector import TerraformCollector

from .okta_opa_tf_group_builder import OktaTfGroupBuilder
from .okta_opa_tf_group_models import OktaTfGroupRoBuilderModel
from .okta_tf_models import OKTATF_RO, OktaTFGroupLookup
from .okta_tf_workspace import OKTA_PROVIDER, okta_credentials_present

log = logging.getLogger(__name__)


class OktaTfGroupRoBuilder(OktaTfGroupBuilder):
    """Read-only Okta group builder: a data-source-only terraform root.

    Inherits the workspace scaffolding from OktaTfGroupBuilder but skips it
    when no groups are attached, emits okta_group lookups instead of module
    calls, and gates 'plan' on okta credentials like the user builder.
    """

    @classmethod
    def csis_name(cls) -> str:
        return OKTATF_RO

    @property
    def model(self) -> OktaTfGroupRoBuilderModel:
        return self._model  # type: ignore   # FIXME: This is dangerous

    def _groups(self) -> list[Group]:
        # Sorted for the same reason as the user builders: deterministic
        # output keeps generated diffs reviewable.
        return sorted(self.get_groups_for_builder(), key=lambda g: g.name)

    def _okta_provider_ref(self) -> str | None:
        """Aliased provider reference for root-level data sources (the
        collector always aliases, so no default provider config exists)."""
        ref = TerraformCollector().provider_bindings(self.name).get(OKTA_PROVIDER)
        if ref is None:
            log.warning(
                f"Group builder {self.name} has no configured '{OKTA_PROVIDER}' "
                f"provider; emitted data sources will rely on a default provider "
                f"configuration that this workspace does not generate."
            )
        return ref

    def generate_items_before(
        self, phase: ExecutionLifecyclePhase
    ) -> AssetSet:
        """Workspace scaffolding, skipped entirely when no groups are attached
        (unlike the managed parent, which always scaffolds its root)."""
        if phase != ExecutionLifecyclePhase.GROUP_GENERATION or not self._groups():
            return AssetSet()
        return super().generate_items_before(phase)

    def generate_items_during(
        self, phase: ExecutionLifecyclePhase
    ) -> AssetSet:
        """One okta_group data lookup per attached group -- no module calls."""
        items = AssetSet()
        if phase != ExecutionLifecyclePhase.GROUP_GENERATION or not self._groups():
            return items
        dpath = self.get_path_for_phase(phase, "groups", suffix="-data.tf")
        provider_ref = self._okta_provider_ref()
        for group in self._groups():
            lookup = OktaTFGroupLookup(group, provider=provider_ref)
            items.add_list(dpath, lookup.generate_terraform_data())
        return items

    def get_commands_to_run_after(
        self, phase: ExecutionLifecyclePhase
    ) -> CFExecutables:
        """fmt/init/validate always; plan only when okta credentials are
        exported. Skipped entirely when there are no groups, so tofu never
        runs against an unwritten directory."""
        if phase != ExecutionLifecyclePhase.GROUP_GENERATION or not self._groups():
            return CFExecutables([], [])
        arg_lists = [["fmt"], self._init_args(phase), ["validate"]]
        if self._dry_run():
            # a dry run initialises without the backend and touches no state
            log.info(f"Group builder {self.name}: dry run, 'plan' not run at generation time")
        elif okta_credentials_present():
            arg_lists.append(["plan"])
        else:
            log.warning(
                f"Group builder {self.name}: skipping 'plan' (no okta "
                f"credentials in the environment)."
            )
        wd = self.get_path_for_phase(phase, suffix=".tf").parent
        return CFExecutables(self.terraform_commands(phase, arg_lists, wd), [])
