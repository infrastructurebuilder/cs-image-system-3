# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
import urllib.error
from typing import Any

from cs_image_system.base import utils
from cs_image_system.base.basic.asset import AssetSet
from cs_image_system.base.basic.builder_base_group import GID_POLICY_CREATION_ONLY, GroupBuilderBase
from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
from cs_image_system.base.models.executable_adds import CFExecutables
from cs_image_system.base.models.group import Group
from cs_image_system.hashicorp_utils.blocks import BlockSpec, DataSpec, OutputSpec, Raw, render_blocks
from cs_image_system.hashicorp_utils.collector import TerraformCollector
from cs_image_system.hashicorp_utils.roots import TerraformRootMixin

from .okta_opa_tf_group_models import OktaTfGroupBuilderModel
from .okta_tf_models import OKTATF
from .opa_attributes import OPA_GROUP_ATTRIBUTES, validate_opa_attributes
from .opa_gids import ADMIN_GROUP_SUFFIX, GROUP_NAME_ATTRIBUTE, USER_GROUP_SUFFIX, OpaGidResolver, credentials_from_env
from .workload_policy import (WorkloadSnapshot, by_name, ci_policy_from, ci_policy_name, policies_equal,
                              user_policy_name, workload_state)

"""
Group provider implementation via Terraform/Tofu for Okta groups using okta/oktapam

"""


# THIS version of the OktaTfGroupBuilder is forced to pull
# users and groups directly from Okta for Linux machines
# and inject them into the running image via a cron process that
# continuouslly performs that pull/chage operation BECAUSE OKTA DOESN'T
# SYNC GROUPS TO OPA PAM MACHINES!!!!!!!!

# The identity-type token base images declare (DESIGN §3F1).
OKTA_IDENTITY_TYPE = "okta"
EXTERNAL_PROVIDER = "external"
GID_SHIM_LABEL = "group_gids"


log = logging.getLogger(__name__)


class OktaTfGroupBuilder(GroupBuilderBase[OktaTfGroupBuilderModel], TerraformRootMixin):
    """Okta group provider implementation via Terraform/Tofu."""
    @classmethod
    def csis_name(cls) -> str:
        return OKTATF


    @property
    def model(self) -> OktaTfGroupBuilderModel:
        return self._model # type: ignore   # FIXME: This is dangerous

    # ------------------------------------------------------ V2 contract
    @classmethod
    def identity_type(cls) -> str:
        return OKTA_IDENTITY_TYPE

    def gid_policy(self) -> str:
        # N1: okta allows defining a gid only at group creation; thereafter it
        # is a read attribute, delivered downstream by reference (N7).
        return GID_POLICY_CREATION_ONLY

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]:
        """Bake the OPA server agent (sftd), installed but DORMANT: no
        enrollment token, service disabled. Activation happens per instance
        image (activation_commands) and enrollment at launch (N26)."""
        fam = (os_family or "").lower()
        if fam in ("debian", "ubuntu"):
            install = [
                # Debian vendor AMIs ship neither curl nor gnupg (found live)
                "command -v curl >/dev/null 2>&1 && command -v gpg >/dev/null 2>&1 || { sudo apt-get -o DPkg::Lock::Timeout=600 update -y; sudo apt-get -o DPkg::Lock::Timeout=600 install -y curl gnupg; }",
                "curl -fsSL https://dist.scaleft.com/GPG-KEY-OktaPAM-2023 | sudo gpg --dearmor -o /usr/share/keyrings/oktapam-2023-archive-keyring.gpg",
                "echo 'deb [signed-by=/usr/share/keyrings/oktapam-2023-archive-keyring.gpg] https://dist.scaleft.com/repos/deb focal okta' | sudo tee /etc/apt/sources.list.d/oktapam-stable.list",
                "sudo apt-get -o DPkg::Lock::Timeout=600 update -y",
                "sudo apt-get -o DPkg::Lock::Timeout=600 install -y scaleft-server-tools",
            ]
        else:
            install = [
                "sudo rpm --import https://dist.scaleft.com/GPG-KEY-OktaPAM-2023",
                "printf '[oktapam-stable]\\nname=Okta PAM Stable - $basearch\\nbaseurl=https://dist.scaleft.com/repos/rpm/stable/rhel/$releasever/$basearch\\ngpgcheck=1\\nrepo_gpgcheck=1\\nenabled=1\\ngpgkey=https://dist.scaleft.com/GPG-KEY-OktaPAM-2023\\n' | sudo tee /etc/yum.repos.d/oktapam-stable.repo",
                "sudo yum install -y scaleft-server-tools",
            ]
        return [f"# identity type '{OKTA_IDENTITY_TYPE}' prerequisites ({self.get_name()}): OPA agent, dormant"] + install + [
            "sudo systemctl disable --now sftd || true",
            "sudo rm -f /var/lib/sftd/enrollment.token",
        ]

    def verify_commands(self, os_family: str | None = None) -> list[str]:
        return [
            "# verify: OPA agent present and dormant",
            "command -v sftd >/dev/null 2>&1 || test -x /usr/sbin/sftd || test -x /usr/bin/sftd",
            "! systemctl is-enabled sftd >/dev/null 2>&1",
            "test ! -e /var/lib/sftd/enrollment.token",
        ]

    def activation_verify_commands(self, image: Any, group: Group) -> list[str]:
        return [
            f"# verify: activated for group '{group.get_name()}'",
            f"grep -q 'tx.group: {group.get_name()}' /etc/sft/sftd.yaml",
            "systemctl is-enabled sftd >/dev/null 2>&1",
        ]

    def activation_commands(self, image: Any, group: Group) -> list[str]:
        """Turn the dormant plumbing on for the image's owning group: the
        ``sftd.tx.group`` server label the group's policies select on, and
        the service armed to enroll when a token appears at launch."""
        label = group.get_name()
        return [
            f"# identity activation for group '{label}' ({OKTA_IDENTITY_TYPE}) on image {image.get_name()}",
            "sudo mkdir -p /etc/sft",
            f"printf 'Labels:\\n  tx.group: {label}\\n' | sudo tee /etc/sft/sftd.yaml",
            "sudo systemctl enable sftd",
        ]

    def launch_parameters(self, group: Group) -> dict[str, str]:
        return {"enrollment": "sftd-token", "server_label": f"sftd.tx.group={group.get_name()}"}

    @classmethod
    def export_gids(cls, query: dict[str, str], groups: list[str]) -> dict[str, int]:
        team = str(query.get("team") or "")
        api_host = str(query.get("api_host") or "")
        if not team or not api_host:
            raise ValueError("okta gid shim query must carry 'team' and 'api_host'")
        key, secret = credentials_from_env(team)
        return OpaGidResolver(api_host, team, key, secret).resolve(groups)

    # ----------------------------------------------- server registry (stage 55)
    # (_resolver, further down, already builds the client these use)
    def can_query_servers(self) -> bool:
        return True

    def registered_servers(self, group: str) -> list[dict[str, Any]] | None:
        try:
            return self._resolver().registered_servers(group)
        except Exception as e:  # noqa: BLE001 - credentials, network: cannot ask, so no claim
            log.debug(f"OPA servers for group {group!r} unavailable: {e}")
            return None

    def retire_servers_named(self, group: str, hostname: str) -> list[str]:
        r = self._resolver()
        servers = r.registered_servers(group)
        if servers is None:
            raise RuntimeError(f"OPA could not be asked for group {group!r}'s servers; "
                               f"registration of {hostname!r} NOT retired")
        gone: list[str] = []
        for s in servers:
            if s["hostname"] == hostname and r.retire_server(group, s["id"]):
                log.info(f"OPA server registration {s['id']} ({hostname} at {s['address'] or '?'}) retired")
                gone.append(s["id"])
        return gone

    # ------------------------------------------- CI login policy (stage 56)
    def can_manage_workload_access(self) -> bool:
        return bool(self.model.workload_connection and self.model.workload_role)

    def workload_access_expected(self, group: str) -> dict[str, Any] | None:
        if not self.can_manage_workload_access():
            return None
        return {"connection": str(self.model.workload_connection),
                "role": str(self.model.workload_role),
                "policy": ci_policy_name(group), "mirrors": user_policy_name(group)}

    def _workload_snapshot(self) -> "WorkloadSnapshot | None":
        """One read of the three listings a group's state and reconcile need;
        None when the policies or the roles could not be read (the
        connections listing may fail alone: it is reported, never required)."""
        r = self._resolver()
        policies, roles = r.security_policies(), r.workload_roles()
        if policies is None or roles is None:
            return None
        return WorkloadSnapshot(policies=policies, roles=roles, connections=r.workload_connections())

    def workload_access_state(self, group: str) -> dict[str, Any] | None:
        snap = self._workload_snapshot()
        return None if snap is None else workload_state(snap, group, str(self.model.workload_connection),
                                                        str(self.model.workload_role))

    def ensure_workload_access(self, group: str) -> dict[str, Any]:
        snap = self._workload_snapshot()
        if snap is None:
            raise RuntimeError("OPA's security policies or workload roles could not be read")
        role = by_name(snap.roles, str(self.model.workload_role))
        if role is None:
            raise RuntimeError(f"workload role {self.model.workload_role!r} is not known to OPA; "
                               "the operator creates it (WORKLOAD_CONNECTION.md section 2)")
        role_id = str(role.get("id") or "")
        if not role_id:
            raise RuntimeError(f"workload role {self.model.workload_role!r} carries no id")
        user = by_name(snap.policies, user_policy_name(group))
        if user is None:
            raise RuntimeError(f"user policy {user_policy_name(group)!r} is absent; the identity apply "
                               "creates it, and the CI policy is a copy of it")
        desired = ci_policy_from(user, group, role_id)
        standing = by_name(snap.policies, ci_policy_name(group))
        r = self._resolver()
        if standing is None:
            created = r.create_security_policy(desired)
            return {"action": "created", "policy": ci_policy_name(group),
                    "id": str(created.get("id") or ""), "role_id": role_id}
        if policies_equal(standing, desired):
            return {"action": "unchanged", "policy": ci_policy_name(group),
                    "id": str(standing.get("id") or ""), "role_id": role_id}
        r.update_security_policy(str(standing["id"]), desired)
        return {"action": "updated", "policy": ci_policy_name(group),
                "id": str(standing.get("id") or ""), "role_id": role_id}

    def query_state(self) -> dict[str, dict[str, Any]]:
        """OPA's record of every group this builder manages: the server
        group's unix gid / group name and, when the service answers, its
        members. Read-only; the service token never leaves the process."""
        team, api_host = str(self.model.team), str(self.model.api_host)
        key, secret = credentials_from_env(team)
        resolver = OpaGidResolver(api_host, team, key, secret)
        snapshot = self._workload_snapshot() if self.can_manage_workload_access() else None
        out: dict[str, dict[str, Any]] = {}
        for g in self.get_groups_for_builder():
            name = g.get_name()
            server_group = f"{name}{USER_GROUP_SUFFIX}"
            try:
                attrs = resolver.group_attributes(server_group)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    out[name] = {"present": False}          # OPA answered: the group is not there
                    continue
                # stage 61 item 1: a call that FAILED (401 from a lapsed key pair,
                # a 5xx) is not an absence; the record says so and the drift
                # rule reports the group as unavailable, never as missing
                log.debug(f"OPA group {server_group!r} unavailable: {e}")
                out[name] = {"present": False, "error": f"HTTP {e.code} {e.reason}"[:120]}
                continue
            except Exception as e:                          # no token, no network, no credentials
                log.debug(f"OPA group {server_group!r} unavailable: {e}")
                out[name] = {"present": False, "error": str(e)[:120]}
                continue
            rec: dict[str, Any] = {"present": True, "gid": resolver.gid_of(attrs),
                                   "local_name": attrs.get(GROUP_NAME_ATTRIBUTE)}
            members = resolver.group_users(server_group)
            if members is not None:
                rec["members"] = members
            admins = resolver.group_users(f"{name}{ADMIN_GROUP_SUFFIX}")
            if admins is not None:
                rec["admins"] = admins
            # Token liveness (PLAN.md IaC-managed enrollment tokens, finding
            # 32): an out-of-band deletion ERRORS every identity plan, so this
            # probe is the only witness. Key omitted when the API is silent.
            descs = resolver.project_enrollment_tokens(name)
            if descs is not None:
                rec["enrollment_token"] = any(
                    d.startswith("cs-image-system launch enrollment") for d in descs)
            # stage 56: the CI login policy, the role it names and the
            # connection behind it; the key is omitted when OPA is silent
            if snapshot is not None:
                rec["workload"] = workload_state(snapshot, name, str(self.model.workload_connection),
                                                 str(self.model.workload_role))
            out[name] = rec
        return out

    # ------------------------------------------- EXPLORE identity hooks
    def validate_attributes(self, group: Any, attributes: dict[str, Any]) -> list[str]:
        return validate_opa_attributes(f"group '{group.get_name()}'", attributes, OPA_GROUP_ATTRIBUTES)

    def _resolver(self) -> OpaGidResolver:
        team, api_host = str(self.model.team), str(self.model.api_host)
        key, secret = credentials_from_env(team)
        return OpaGidResolver(api_host, team, key, secret)

    def query_attributes(self, group: Any) -> dict[str, Any] | None:
        return self._resolver().group_attributes(f"{group.get_name()}{USER_GROUP_SUFFIX}")

    def attribute_conflicts(self) -> list[dict[str, Any]] | None:
        return self._resolver().attribute_conflicts()

    # ------------------------------------------------------- emission
    def _external_provider_ref(self) -> str | None:
        return TerraformCollector().provider_bindings(self.name).get(EXTERNAL_PROVIDER)

    def generate_items_before(
        self, phase: ExecutionLifecyclePhase
    ) -> AssetSet:
        """Generate a list of items to create before a specific execution lifecycle
        event."""
        items: AssetSet = AssetSet()
        if phase == ExecutionLifecyclePhase.GROUP_GENERATION:
            rpath = self.get_path_for_phase(phase, suffix=".tf")
            items = items.with_default_path(rpath)  # Set default path for convenience when generating group TF configs
            items.add(
                f"# Terraform configuration for Okta groups generated by "
                f"{self.__class__.__name__} ({self.name})",
            )
            items.add( "\n")
            col = TerraformCollector()
            self.model.register_hcl_requirements(self.name)
            # The gid shim (N7) is a data "external" lookup: declare the provider.
            col.require_provider(self.name, EXTERNAL_PROVIDER, source="hashicorp/external")
            col.configure_provider(self.name, EXTERNAL_PROVIDER, {})
            items.add_list(col.generate_terraform_block(self.name))
            items.add("\n")
            items.add_list(col.generate_provider_blocks(self.name))
            items.add("\n")
            # stage 34: declared-encrypted workspace credentials, if any,
            # reach the provider block by reference (registered by
            # transform_provider above)
            sensitive_lines = col.generate_sensitive_blocks(self.name)
            if sensitive_lines:
                items.add_list(sensitive_lines)
                items.add("\n")
            vpath = self.get_path_for_phase(phase,
                suffix=f"-{utils.safe_name(self.name)}-vars.tf"
            )
            items.add_list(vpath, col.generate_variable_blocks(self.name))
            backend_lines = col.generate_backend_config(self.name)
            if backend_lines:
                items.add_list(self._backend_config_path(phase), backend_lines)

        return items

    def get_commands_to_run_before(
        self, phase: ExecutionLifecyclePhase
    ) -> CFExecutables:
        """Get a list of commands to run before a specific execution lifecycle event."""
        return CFExecutables()

    def generate_items_during(
        self, phase: ExecutionLifecyclePhase
    ) -> AssetSet:
        """Generate a list of items to create during a specific execution lifecycle
        event."""
        items = AssetSet()
        if phase == ExecutionLifecyclePhase.GROUP_GENERATION:
            from cs_image_system.base.global_context import GlobalTypeContext
            ctx = GlobalTypeContext()
            rg: Group = ctx.root_group
            src = utils.module_source("okta_opa_module",
                                      self.get_path_for_phase(phase, suffix=".tf").parent)

            for group in self.get_groups_for_builder():
                rpath = self.get_path_for_phase(phase, f"group-{group.name}", suffix=".tf")
                if getattr(group, "unmanaged", False):
                    items.add(rpath, f"# Okta group {group.name} is UNMANAGED (N19): alive on the far side, "
                                     "no longer described here; its state entries are removed, never destroyed.")
                    continue
                items.add(
                    rpath,
                    f"# Terraform module call for Okta group {group.name} "
                    f"generated by {self.__class__.__name__} "
                    f"({self.name})",
                )
                items.add_list(rpath, self._group_module_call(group, rg, src))
            opath = self.get_path_for_phase(phase, "outputs", suffix=".tf")
            items.add_list(opath, self._outputs(self.managed_groups()))

        return items

    def _outputs(self, groups: list[Group]) -> list[str]:
        """The identity root's outputs (N7): ``group_gids`` (group -> gid, via
        the external gid shim) and ``groups`` (the OPA object ids per group,
        from the module outputs). Consumers read them through
        ``data.terraform_remote_state.<this workspace>.outputs``."""
        names = sorted(g.get_name() for g in groups)
        lines = [
            f"# Outputs of the identity root {self.name} (DESIGN N7).",
            "# GIDs are never literals: the oktapam provider exposes no group gid, so this",
            "# root asks the system's own CLI (read-only, credentials from the environment)",
            "# and publishes the answer as an output for terraform_remote_state consumers.",
        ]
        if not names:
            lines.append('output "group_gids" {')
            lines.append("  value = {}")
            lines.append("}")
            return lines
        query: dict[str, Any] = {
            "identity_type": OKTA_IDENTITY_TYPE,
            "org": self.model.org,
            "team": self.model.team,
            "api_host": self.model.api_host,
            "groups": ",".join(names),
        }
        args: dict[str, Any] = {}
        ref = self._external_provider_ref()
        if ref:
            args["provider"] = Raw(ref)
        args["program"] = [utils.SYSTEM_CLI, "identity", "export-gids"]
        args["query"] = query
        specs: list[BlockSpec] = [DataSpec(EXTERNAL_PROVIDER, GID_SHIM_LABEL, args,
                                           comment="gid shim: {group: gid} for every managed group")]
        specs.append(OutputSpec(
            "group_gids",
            Raw(f"{{ for g, gid in data.external.{GID_SHIM_LABEL}.result : g => tonumber(gid) }}"),
            description="Group name -> unix gid, queried from OPA; consume by reference only"))
        group_map: dict[str, Any] = {}
        for name in names:
            label = utils.super_safe_name(name)
            group_map[name] = {
                "user_group_id": Raw(f"module.group_{label}.user_group_id"),
                "admin_group_id": Raw(f"module.group_{label}.admin_group_id"),
                "resource_group_id": Raw(f"module.group_{label}.resource_group_id"),
                "user_group_name": Raw(f"module.group_{label}.user_group_name"),
            }
        specs.append(OutputSpec("groups", group_map,
                                description="Managed OPA groups and their object ids"))
        token_map = {name: Raw(f"module.group_{utils.super_safe_name(name)}.enrollment_token")
                     for name in names}
        specs.append(OutputSpec(
            "group_enrollment_tokens", token_map, sensitive=True,
            description="Group -> launch enrollment token (IaC-owned, PLAN.md); "
                        "consume by reference only"))
        lines.extend(render_blocks(specs))
        return lines

    def enrollment_token_reference(self, group: str) -> str | None:
        """The launch enrollment credential for ``group``, by remote-state
        reference into this root's sensitive output (PLAN.md IaC-managed
        enrollment tokens); never a literal."""
        ws = utils.super_safe_name(self.name)
        return (f"data.terraform_remote_state.{ws}"
                f'.outputs.group_enrollment_tokens["{group}"]')

    def _group_module_call(self, group: Group, root_group: Group, source: str) -> list[str]:
        """Emit a `module` call for one group against tfmodules/okta_opa_module.

        Every group's resource group delegates to that group's OWN admin
        group: no delegates are passed and the module's fallback
        ([oktapam_group.admin.id]) supplies it (PLAN.md local-migration Q1).
        """
        label = utils.super_safe_name(group.name)
        # Membership comes from the group definition itself; users attach to the
        # user builder, not this group builder. Member/admin entries are bare
        # OPA usernames (PLAN.md local-migration Q3) — exactly what the module's
        # oktapam_user_group_attachment expects.
        members = sorted(group.members or set())
        admin_set = set(group.admins or set())
        # Root group's admins merge into every group's admins (union, no
        # duplicates) unless the group opts out (PLAN.md local-migration Q2); the
        # root group itself is a natural no-op.
        if getattr(group, "include_root_group_in_admins", True):
            admin_set |= set(root_group.admins or set())
        admins = sorted(admin_set)
        quoted_members = ", ".join(f'"{m}"' for m in members)
        quoted_admins = ", ".join(f'"{a}"' for a in admins)
        delegated = "[]"
        bindings = TerraformCollector().provider_bindings(self.name)
        providers = ", ".join(f"{k} = {v}" for k, v in sorted(bindings.items())
                              if k != EXTERNAL_PROVIDER)
        lines = [
            f'module "group_{label}" {{',
            f'  source                    = "{source}"',
            *([f'  providers                 = {{ {providers} }}'] if providers else []),
            f'  group_id                  = "{label}"',
            f'  members                   = [{quoted_members}]',
            f'  admins                    = [{quoted_admins}]',
            f'  delegated_admin_group_ids = {delegated}',
            f'  account_discovery         = {str(self.model.account_discovery).lower()}',
        ]
        gateway_selector = self.model.effective_gateway_selector
        if gateway_selector:
            lines.append(f'  gateway_selector          = "{gateway_selector}"')
        lines.append("}")
        return lines

    def get_commands_to_run_during(
        self, phase: ExecutionLifecyclePhase
    ) -> CFExecutables:
        """Get a list of commands to run during a specific execution lifecycle event."""
        return CFExecutables([], [])

    def generate_items_after(
        self, phase: ExecutionLifecyclePhase
    ) -> AssetSet:
        """Generate a list of items to create after a specific execution lifecycle event."""
        return AssetSet()

    def _newly_unmanaged_groups(self) -> list[Group]:
        """Groups marked unmanaged now that the identity read-model last
        recorded as managed: their state entries get removed (never destroyed)."""
        from cs_image_system.base.global_context import GlobalTypeContext
        previous = GlobalTypeContext().meta_state.identity_read_model().get("groups", {}) or {}
        out: list[Group] = []
        for g in self.get_groups_for_builder():
            if getattr(g, "unmanaged", False):
                rec = previous.get(g.get_name())
                if isinstance(rec, dict) and rec.get("managed", True):
                    out.append(g)
        return out

    def _stale_attachment_addresses(self) -> list[str]:
        """Stage 61 item 3: the ``oktapam_user_group_attachment`` state entries
        of memberships the declaration DROPPED and OPA no longer holds.

        The provider ERRORS on refreshing an attachment whose membership is
        gone (``user "x" is not present within group "g"``) instead of
        dropping it from state, so the plan never reaches the destroy it
        would have shown; on 2026-09-22 two such entries blocked the first
        real identity run after a roster was conformed to OPA by hand. The
        addresses come from the previous identity read-model (members and
        admins as last applied) minus the declaration; each is removed from
        state before the plan ONLY when OPA, asked now, does not hold the
        membership either. A membership OPA still holds is left to the plan
        (the destroy shows, the gate sees it: the explicit decision the rules
        want); a silent OPA removes nothing and the plan proceeds as it did.
        A dry run asks nothing and removes nothing."""
        if self._dry_run():
            return []
        from cs_image_system.base.global_context import GlobalTypeContext
        previous = GlobalTypeContext().meta_state.identity_read_model().get("groups", {}) or {}
        candidates: list[tuple[Group, str, str, set[str]]] = []
        for g in self.get_groups_for_builder():
            if getattr(g, "unmanaged", False):
                continue
            rec = previous.get(g.get_name())
            if not isinstance(rec, dict) or not rec.get("managed", True):
                continue
            for kind, suffix, declared in (("members", USER_GROUP_SUFFIX, set(g.members or ())),
                                           ("admins", ADMIN_GROUP_SUFFIX, set(g.admins or ()))):
                dropped = {str(u) for u in (rec.get(kind) or [])} - {str(u) for u in declared}
                if dropped:
                    candidates.append((g, kind, f"{g.get_name()}{suffix}", dropped))
        if not candidates:
            return []
        try:
            resolver = self._resolver()
        except Exception as e:
            log.warning(f"Identity builder {self.name}: memberships were dropped from the declaration but OPA "
                        f"cannot be asked whether it still holds them ({e}); nothing is removed from state")
            return []
        out: list[str] = []
        for g, kind, server_group, dropped in candidates:
            held = resolver.group_users(server_group)
            if held is None:
                log.warning(f"Identity builder {self.name}: OPA did not answer for group {server_group!r}; "
                            f"its dropped {kind} {sorted(dropped)} stay in state for the plan to decide")
                continue
            label = utils.super_safe_name(g.name)
            for user in sorted(dropped - set(held)):
                out.append(f'module.group_{label}.oktapam_user_group_attachment.{kind}["{user}"]')
                log.info(f"Identity builder {self.name}: {kind[:-1]} {user!r} was dropped from group "
                         f"{g.get_name()!r} and OPA no longer holds it; its attachment leaves tofu state "
                         "before the plan (state rm, after a backup)")
            for user in sorted(dropped & set(held)):
                log.info(f"Identity builder {self.name}: {kind[:-1]} {user!r} was dropped from group "
                         f"{g.get_name()!r} but OPA still holds it; the plan will show the destroy")
        return out

    def get_commands_to_run_after(
        self, phase: ExecutionLifecyclePhase
    ) -> CFExecutables:
        """fmt/init/validate/plan at generation (a read); the deferred runner
        script carries the gated plan -> gate -> (apply) sequence, applying
        only when ``config: apply_identity`` is set."""
        if phase != ExecutionLifecyclePhase.GROUP_GENERATION:
            return CFExecutables([], [])
        wd = self.get_path_for_phase(phase, suffix=".tf").parent
        # a dry run initialises without the backend and touches no state, so
        # the generation-time plan (a read) is a real run's; the deferred
        # script below enumerates the gated plan either way
        commands = self.terraform_commands(phase, [["fmt"], self._init_args(phase), ["validate"]], wd)
        if not self._dry_run():
            # the plan reads plaintext, so it runs in the private mirror (stage 51: the
            # derived addresses carry ciphertext in the committed emission)
            commands += self.plaintext_read_commands(phase, wd, [["plan"]])
        pre_plan = [["state", "rm", f"module.group_{utils.super_safe_name(g.name)}"]
                    for g in self._newly_unmanaged_groups()]
        pre_plan += [["state", "rm", addr] for addr in self._stale_attachment_addresses()]
        # Per-root apply scoping (stage 7): the identity root is its builder name;
        # a pre-plan state rm is preceded by a state backup (stage 61 item 3)
        deferred = self.gated_apply_commands(
            phase, wd, apply=utils.apply_enabled("identity", self.name), pre_plan=pre_plan,
            apply_flag_key="identity", apply_root=self.name, pre_plan_backup=True)
        # EXPLORE identity: attributes travel outside terraform. When
        # anything is declared, the runner probes (read-only) after the
        # apply and shows what an attribute apply would change; the write
        # itself stays disabled (DESIGN Q7).
        from cs_image_system.base.identity_attributes import declared_attributes
        declared = declared_attributes(self._get_context())
        if declared["groups"] or declared["users"]:
            deferred.append(utils.system_cli_executable(
                ["identity-attributes", "--probe", "--dry-run-apply"], wd))
        return CFExecutables(commands, deferred)
