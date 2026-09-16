# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from enum import StrEnum
from typing import Any, Callable

from cs_image_system.base.models.group import Group
from cs_image_system.base.models.group_builder import GroupBuilderModel
from cs_image_system.base.models.user import User
from cs_image_system.base.models.user_builder import UserBuilderModel
from cs_image_system.base.utils import super_safe_name as ssn
from cs_image_system.hashicorp_utils.blocks import (
    DataSpec,
    Raw,
    ResourceSpec,
    render_blocks,
)
from cs_image_system.hashicorp_utils.hashicorp import TerraformGenerator

OKTATF: str = "okta-tf"
OKTATF_RO: str = "okta-tf-ro"

class OKTA_USER_ROLES(StrEnum):
    USER = "access_user"
    ADMIN = "access_admin"
    REPORTING = "reporting_user"

class OKTA_USER_STATUS(StrEnum):
    """okta_user statuses. NOTE: not the same value set as the Okta *API*
    (there is no DISABLED); is_enabled=False maps to SUSPENDED."""
    ACTIVE = "ACTIVE"
    STAGED = "STAGED"
    SUSPENDED = "SUSPENDED"
    DEPROVISIONED = "DEPROVISIONED"


# okta_user optional arguments that are simultaneously User field names.
# Emitted only when truthy; snake_case is the resource's argument style
# (User.as_profile() is the camelCase API wire shape -- do NOT use it here).
_OKTA_USER_OPTIONAL_ATTRS = (
    "middle_name", "mobile_phone", "honorific_prefix", "honorific_suffix",
    "title", "display_name", "nick_name", "profile_url", "second_email",
    "primary_phone", "street_address", "city", "state", "zip_code",
    "country_code", "postal_address", "preferred_language", "locale",
    "timezone", "user_type", "employee_number", "cost_center",
    "organization", "division", "department", "manager_id", "manager",
)


class OktaTFUser(TerraformGenerator):
    """Emits a root-level Okta identity via the okta/okta provider's
    ``okta_user`` resource.

    History: this originally emitted ``oktapam_user`` blocks, commented out
    because that oktapam resource does not function; identities are created in
    the Okta org itself, and OPA sees them through Okta.

    Deliberately not emitted: ``User.public_keys`` (okta_user has no home for
    SSH keys; reserved for the modification builders) and any user-type or
    service-account marker (``okta_user.user_type`` is an Okta User Type *id*,
    not a human/service discriminator).
    """

    def __init__(self, user: User, *, provider: str | None = None,
                 status: str | None = None, login_from_email: bool = True,
                 lookup_depends_on: bool = True,
                 sensitive: Callable[[str, Any], Any] | None = None) -> None:
        """Create an OktaTFUser from a User object.

        Parameters
        ----------
        user : User
            The user to derive Okta attributes from.
        provider : str | None
            Aliased provider reference (e.g. ``okta.okta_tf_users``) emitted as
            the ``provider`` meta-argument. Required for root-level resources:
            the collector always aliases provider configs, so no default okta
            provider configuration exists.
        status : str | None
            Status for enabled users (a builder passes its model's
            default_user_status, STAGED by default). Disabled users are always
            SUSPENDED; with no status given, enabled users are ACTIVE.
        login_from_email : bool
            Use the email as the Okta login (the convention email_as_username
            enforces); otherwise the bare user name.
        lookup_depends_on : bool
            Give the data-source lookup a depends_on on the created resource so
            a fresh workspace can plan before the user exists.
        sensitive : callable
            ``(key, value) -> value`` -- the collector's ``sensitive_ref`` for
            the root (stage 34): a decrypted value comes back as the
            ``local.sensitive[...]`` reference to its ciphertext and is
            registered for the root's decrypting data source; anything else
            comes back unchanged. Constructing the object registers.
        """
        self.name = user.name
        self.label = ssn(user.name)
        self.provider = provider
        s: Callable[[str, Any], Any] = sensitive or (lambda key, value: value)
        self.first_name = s(f"first_name_{self.label}", user.first_name)
        self.last_name = s(f"last_name_{self.label}", user.last_name)
        self.email = s(f"email_{self.label}", user.email) if user.email else None
        # login is the email when the convention says so: one registered value
        self.login = self.email if (login_from_email and self.email) else s(f"login_{self.label}", user.name)
        if not user.is_enabled:
            self.status = OKTA_USER_STATUS.SUSPENDED.value
        else:
            self.status = status or OKTA_USER_STATUS.ACTIVE.value
        self.lookup_depends_on = lookup_depends_on
        self._user = user

    def get_resource_name(self) -> str:
        return f"okta_user.{self.resource_name_from_this_type()}"

    def generate_terraform(self, setup: dict[str, Any] = {}) -> list[str]:
        user = self._user
        args: dict[str, Any] = {}
        if self.provider:
            args["provider"] = Raw(self.provider)
        args.update({
            "first_name": self.first_name,
            "last_name": self.last_name,
            "login": self.login,
            "email": self.email or self.login,
            "status": self.status,
        })
        for attr in _OKTA_USER_OPTIONAL_ATTRS:
            val = getattr(user, attr, None)
            if val:
                args[attr] = val
        return render_blocks([ResourceSpec(
            "okta_user", self.label, args,
            comment=f"Okta user {self.name}",
        )])

    def generate_terraform_data(self, setup: dict[str, Any] = {}) -> list[str]:
        args: dict[str, Any] = {}
        if self.provider:
            args["provider"] = Raw(self.provider)
        if self.lookup_depends_on:
            # Defer the read to apply: on a fresh workspace the user does not
            # exist at plan time and an eager lookup fails the plan.
            args["depends_on"] = [Raw(self.get_resource_name())]
        # Least privilege (LEDGER.md item 1): the lookup needs neither the
        # user's admin roles nor group memberships. Skipping them is what lets
        # the okta.roles.read scope stay revoked on the API services app.
        args["skip_roles"] = True
        args["skip_groups"] = True
        spec = DataSpec(
            "okta_user", self.label, args,
            comment=f"Lookup of Okta user {self.name} by login",
        )
        # data "okta_user" has no top-level login argument -- search block only.
        spec.block("search", name="profile.login", value=self.login, comparison="eq")
        return render_blocks([spec])

    def resource_name_from_this_type(self) -> str:
        return self.label

class OktaTFGroup(TerraformGenerator):
    name: str
    admin: bool = False

    def __init__(self, group: Group, admin: bool = False) -> None:
        """Create an OktaTFGroup from a Group object.

        Parameters
        ----------
        group : Group
            The group to derive Okta attributes from.
        """
        self.name = group.name
        self.admin = admin
        self.include_root_group_in_admins = group.include_root_group_in_admins
    def get_resource_name(self) -> str:
        return f"oktapam_group.{self.resource_name_from_this_type()}"

    def generate_terraform(self, setup: dict[str, Any] = {}) -> list[str]:
        rn = self.resource_name_from_this_type()
        return render_blocks([ResourceSpec("oktapam_group", rn, {"name": rn})])

    def generate_terraform_data(self, setup: dict[str, Any] = {}) -> list[str]:
        return render_blocks([DataSpec(
            "oktapam_group", self.resource_name_from_this_type(),
            {"name": self.name},
            comment=(f"Terraform data source configuration for Okta group "
                     f"{self.name} does not currently exist in the provider"),
            commented_out=True,
        )])

    def resource_name_from_this_type(self) -> str:
        return f"{ssn(self.name)}_{'admin' if self.admin else 'user'}"


class OktaTFGroupLookup(TerraformGenerator):
    """Emits a lookup of an existing Okta group via the okta/okta provider's
    ``data "okta_group"`` source. Lookup-only: there is no resource emission.

    The oktapam provider has no group data source (see OktaTFGroup's
    commented-out data block), so read-only group roots look groups up in the
    Okta org itself. NOTE: the okta provider's ``name`` search is prefix-based;
    exact group names in the YAML definitions are the contract here.
    """

    def __init__(self, group: Group, *, provider: str | None = None) -> None:
        """Create an OktaTFGroupLookup from a Group object.

        Parameters
        ----------
        group : Group
            The group whose name to look up.
        provider : str | None
            Aliased provider reference (e.g. ``okta.okta_ro_groups``) emitted
            as the ``provider`` meta-argument. Required for root-level data
            sources: the collector always aliases provider configs, so no
            default okta provider configuration exists.
        """
        self.name = group.name
        self.label = ssn(group.name)
        self.provider = provider

    def get_resource_name(self) -> str:
        return f"data.okta_group.{self.label}"

    def generate_terraform(self, setup: dict[str, Any] = {}) -> list[str]:
        return []

    def generate_terraform_data(self, setup: dict[str, Any] = {}) -> list[str]:
        args: dict[str, Any] = {}
        if self.provider:
            args["provider"] = Raw(self.provider)
        args["name"] = self.name
        return render_blocks([DataSpec(
            "okta_group", self.label, args,
            comment=f"Lookup of Okta group {self.name} by name",
        )])


class OktaTFUserToGroup(TerraformGenerator):
    group: OktaTFGroup
    user: OktaTFUser

    def __init__(self, group: OktaTFGroup, user:  OktaTFUser) -> None:
        """Create an OktaTFUserToGroup from a Group and User object.

        Parameters
        ----------
        group : Group
            The group to derive Okta attributes from.
        user : User
            The user to derive Okta attributes from.
        """
        self.group = group
        self.user = user

    def generate_terraform(self, setup: dict[str, Any] = {}) -> list[str]:
        return render_blocks([ResourceSpec(
            "oktapam_user_group_attachment",
            f"{self.group.name}_{self.user.name}",
            {
                "group": Raw(self.group.get_resource_name() + ".name"),
                "username": self.user.name,
            },
        )])


class OktaTFResourceGroup(TerraformGenerator):
    group: OktaTFGroup
    name: str
    description: str = ""
    admin_groups: list[OktaTFGroup] = []

    def __init__(
        self, group: OktaTFGroup, 
        admin_groups: list[OktaTFGroup] | None = None,
        gateway_selector: str | None = None,
        account_discovery: bool = False,
        addl_setup: dict[str, Any] = {},
    ) -> None:
        self.group = group
        self.name = group.name
        self.description = (
            f"Resource group for Okta group {group.resource_name_from_this_type()} "
            "generated by OktaTFResourceGroup"
        )
        self.admin_groups = admin_groups or []
        self.gateway_selector = gateway_selector
        self.account_discovery = account_discovery
        self.addl_setup = addl_setup
        self.delegated_resource_admin_groups = [
            f"{g.get_resource_name()}.id"
            for g in self.admin_groups
            if self.admin_groups
        ]
        
    def resource_name_from_this_type(self) -> str:
        return f"{ssn(self.name)}_rg"

    def get_resource_name(self) -> str:
        return f"oktapam_resource_group.{self.resource_name_from_this_type()}"

    def generate_terraform(self, setup: dict[str, Any] = {}) -> list[str]:
        this_name: str = self.resource_name_from_this_type()
        items = render_blocks([ResourceSpec(
            "oktapam_resource_group", this_name,
            {
                "name": this_name,
                "description": self.description,
                "delegated_resource_admin_groups": [
                    Raw(g) for g in self.delegated_resource_admin_groups],
            },
        )])
        items.append("")
        items.extend(self.generate_resource_group_project(this_name))
        return items

    def generate_resource_group_project(
        self, name: str
    ) -> list[str]:
        rg_name: str = f"{name}_login"
        ct: dict[str, Any] = {
            "name": rg_name,
            "resource_group": Raw(f"oktapam_resource_group.{name}.id"),
            "account_discovery": self.account_discovery,
        }
        if self.gateway_selector:
            ct["gateway_selector"] = self.gateway_selector
        return render_blocks([ResourceSpec(
            "oktapam_resource_group_project", rg_name, ct,
            comment=(f"Terraform configuration for Okta resource group project "
                     f"generated by OktaTFResourceGroup ({self.name})"),
        )])


class OktaTFSecurityPolicyV1(TerraformGenerator):
    name: str
    description: str = ""
    active: bool = True

    def __init__(self, resource_group: OktaTFResourceGroup, group: OktaTFGroup,
                 labels = {}) -> None:
        """Create an OktaTFSecurityPolicyV1 from a Group object.

        Parameters
        ----------
        group : Group
            The group to derive Okta attributes from.
        """
        self.name = f"{ssn(group.name)}_v1_security_policy"
        self.description = (
            f"Security policy for Okta group {group.resource_name_from_this_type()} "
            "generated by OktaTFSecurityPolicyV1"
        )
        self.active = True

        self.group = group
        self.resource_group_id = f"{resource_group.get_resource_name()}.id"

        # Map KEYS are pre-quoted (dotted keys need quotes in HCL); values are
        # plain strings quoted by the renderer's value policy.
        self.labels: dict[str, str] = {'"system.os_type"': "linux",
                '"sftd.tx.group"': self.group.name}
        if labels:
            for k, v in labels.items():
                self.labels[f'"{k}"'] = v

    def get_resource_name(self) -> str:
        return f"oktapam_security_policy.{self.resource_name_from_this_type()}"

    def resource_name_from_this_type(self) -> str:
        return ssn(self.name) + "_admin" if self.group.admin else ssn(self.name) + "_user"

    def generate_terraform(self, setup: dict[str, Any] = {}) -> list[str]:
        # principals = ScopedDict(
        #     scope="principals", content={"groups": f"[{self.group.get_resource_name()}.id]"}
        # )
        # principals = Builder().block("principals", groups = f"[{self.group.get_resource_name()}.id]")
        
        # kv = ScopedDict(
        #     scope="resource",
        #     resource_type=QString("oktapam_security_policy", quoted=True),
        #     nametag=QString(self.resource_name_from_this_type(), quoted=True),
        #     content={
        #         "name": QString(self.resource_name_from_this_type(), quoted=True),
        #         "description": QString(self.description, quoted=True),
        #         "active": str(self.active).lower(),
        #         "resource_group": self.resource_group.get_resource_name() + ".id",
        #     },
        # )
        rn = self.resource_name_from_this_type()
        spec = ResourceSpec(
            "oktapam_security_policy", rn,
            {
                "name": rn,
                "description": self.description,
                "active": self.active,
                "resource_group": Raw(self.resource_group_id),
            },
            comment=(f"Terraform configuration for Okta security policy for "
                     f"group {self.group.name} generated by "
                     f"{self.__class__.__name__} ({self.name})"),
        )
        spec.block("principals",
                   groups=Raw(f"[{self.group.get_resource_name()}.id]"))
        rule = spec.block("rule", name=f"allow_login_{ssn(self.group.name)}")
        rule.block("conditions").block("gateway",
                                       traffic_forwarding=True,
                                       session_recording=False)
        rule.block("privileges").block("principal_account_ssh",
                                       enabled=True,
                                       admin_level_permissions=self.group.admin)
        rule.block("resources").block("servers") \
            .block("label_selectors", server_labels=self.labels)
        return render_blocks([spec])


# resource "oktapam_security_policy" "test3_v1_security_policy" {
#   name   = "test3_v1_security_policy"
#   active = true

#   resource_group = oktapam_resource_group.test3.id

#   principals {
#     groups = [oktapam_group.test3_group.id]
#   }
#   rule {
#     name = "allow_login"

#     privileges {
#       principal_account_ssh {
#         enabled                 = true
#         admin_level_permissions = false
#       }
#     }
#     resources {
#       servers {
#         label_selectors {
#           server_labels = {
#             "system.os_type" = "windows"
#             "env.model"      = "cora"
#           }
#         }
#       }
#     }

#     conditions {
#       gateway {
#         traffic_forwarding = true
#         session_recording  = false
#       }

#     }
#   }

# Base classes. Workspace/credential fields (org, team, key, secret,
# api_host, ...) live on OktaTfWorkspaceModelMixin (okta_tf_workspace.py),
# which the concrete OktaTf*BuilderModel classes mix in.
# Global config key consulted when a group builder sets no gateway_selector.
OKTA_GATEWAY_SELECTOR_CONFIG_KEY = "okta_gateway_selector"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OktaGroupBuilderModel(GroupBuilderModel):
    """Dataclass representing an Okta group configuration."""

    gateway_selector: str | None = None
    account_discovery: bool = True

    @property
    def effective_gateway_selector(self) -> str | None:
        """The builder's gateway_selector, falling back to the global
        ``config.okta_gateway_selector`` when unset (PLAN.md local-migration Q6).
        None when neither is set. A model-field template default cannot do
        this: the TemplateResolver context has no ``config`` scope, so an
        unresolved ``{{ config.* }}`` would leak into HCL as a literal.
        """
        if self.gateway_selector is not None:
            return self.gateway_selector
        from cs_image_system.base.global_context import GlobalTypeContext
        return GlobalTypeContext().config.get(OKTA_GATEWAY_SELECTOR_CONFIG_KEY) or None
@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OktaUserBuilderModel(UserBuilderModel):
    """Dataclass representing an Okta user configuration."""
    type = OKTATF