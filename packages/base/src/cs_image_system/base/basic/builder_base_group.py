# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeVar

from ..models.user import User
from ..models.group import Group

from ..models.group_builder import GroupBuilderModel

from ..constants import VCT

from .builder_base import BuilderBase

if TYPE_CHECKING:
    from ..models.image import Image

# GID authority policies (N1): who defines a group's gid, and when.
GID_POLICY_CONFIG_TIME = "config-time"      # settable in YAML (bash-style groupadd)
GID_POLICY_CREATION_ONLY = "creation-only"  # settable only when the group is created (okta)
GID_POLICY_PROVIDER_ASSIGNED = "provider-assigned"


TGROUP = TypeVar("TGROUP", bound=GroupBuilderModel)
class GroupBuilderBase(BuilderBase[TGROUP]):
    """Base of every identity (group) plugin.

    V2 contract (DESIGN §3D, §3F1/F2):

    * ``identity_type()`` -- the token base images declare in
      ``identity_types``; a group's builder thereby fixes the identity type
      every group name resolves to (group names are system-unique);
    * ``gid_policy()`` -- the plugin's gid authority semantics (N1); every
      plugin must make produced gids queryable downstream by reference (N7);
    * ``base_image_prerequisites()`` -- what a base image declaring this type
      bakes, installed but dormant;
    * ``activation_commands()`` -- how an instance image turns the dormant
      plumbing on for its owning group.
    """
    # Per-instance (allocated in __init__): class-level default lists would be
    # shared by every group builder instance.
    local_users: list[User]
    local_groups: list[Group]

    def __init__(self, model: TGROUP) -> None:
        super().__init__(model)
        self.local_users = []
        self.local_groups = []

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.GROUP_BUILDER

    def add_group_to_builder(self, group: Group) -> None:
        self.local_groups.append(group)

    def get_groups_for_builder(self) -> list[Group]:
        """Get the groups for a builder from the provider."""
        return self.local_groups

    def add_user_to_builder(self, user: User) -> None:
        self.local_users.append(user)
        """Add a user to a group in the provider."""

    def get_users_for_builder(self) -> list[User]:
        """Get the users for a builder from the provider."""
        return self.local_users

    def get_users_for_group(self, group: Group) -> list[User]:
        """Get the users for a group from the provider."""
        return [u for u in self.local_users if u.get_name()  in group.members]

    def get_admins_for_group(self, group: Group) -> list[User]:
        """Get the admins for a group from the provider."""
        return [u for u in self.local_users if u.get_name() in group.admins]

    # ---------------------------------------------------------- V2 contract
    @classmethod
    def identity_type(cls) -> str:
        """The identity-type token (e.g. ``okta``). Defaults to the plugin's
        canonical name."""
        name = getattr(cls, "csis_name", None)
        return str(name()) if callable(name) else cls.__name__

    def gid_policy(self) -> str:
        return GID_POLICY_PROVIDER_ASSIGNED

    def managed_groups(self) -> list[Group]:
        """Groups this builder manages (unmanaged groups are excluded)."""
        return [g for g in self.local_groups if not getattr(g, "unmanaged", False)]

    def enrollment_token_reference(self, group: str) -> str | None:
        """A terraform expression yielding ``group``'s launch enrollment
        credential, or None when this identity plugin does not mint one.
        HOW a token is generated is plugin-dependent (PLAN.md IaC-managed
        enrollment tokens); consumers only ever see the expression."""
        return None

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]:
        """Shell commands baked into a base image declaring this identity type:
        agents/packages installed, enrollment OFF (capable but dormant)."""
        return []

    def verify_commands(self, os_family: str | None = None) -> list[str]:
        """Shell assertions (exit nonzero = the image is wrong) proving this
        identity type's prerequisites are present and DORMANT on a base image
        (EXPLORE "Automated Testing for Image Builds", in-bake layer)."""
        return []

    def activation_verify_commands(self, image: "Image", group: Group) -> list[str]:
        """Shell assertions proving an instance image is activated for its
        owning group."""
        return []

    def activation_commands(self, image: "Image", group: Group) -> list[str]:
        """Shell commands baked into an INSTANCE image that turn the dormant
        plumbing on for its owning group (e.g. the server label)."""
        return []

    def launch_parameters(self, group: Group) -> dict[str, str]:
        """Instance-specific bindings supplied at launch (N26), e.g. the
        enrollment trigger. Values must be public-safe (they are recorded)."""
        return {}

    def query_state(self) -> dict[str, dict[str, Any]]:
        """Reality check (EXPLORE state query): the identity provider's
        record of each group this builder manages, ``{group: {present, gid,
        local_name?, members?, admins?}}``, read-only, credentials from the
        environment, nothing secret in the result. ``members`` is a list
        only when the provider can answer it. Optional."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot query identity state")

    # ------------------------------------------- server registry (stage 55)
    def can_query_servers(self) -> bool:
        """Whether this identity provider keeps a registry of enrolled
        servers that the builder can read and retire (OPA does). Gated like
        the stage-57 runtime hooks: a provider without one makes no claim."""
        return False

    def registered_servers(self, group: str) -> list[dict[str, Any]] | None:
        """Every server currently enrolled for ``group``, each
        ``{id, hostname, address}`` -- or ``None`` when the provider could
        not be ASKED. None is never an empty list: a caller deciding whether
        a canonical hostname is free must not read silence as freedom."""
        return None

    def retire_servers_named(self, group: str, hostname: str) -> list[str]:
        """Remove every registration of ``hostname`` for ``group`` and return
        the ids removed. The registration is the third record of a launch,
        beside the pin and the launch parameters, and the only one that
        used to outlive the machine (stage 55: three ``coops-model``
        entries, one live). Raises when it cannot: a retirement that did
        not happen must not be reported as one."""
        raise NotImplementedError(f"{self.__class__.__name__} keeps no server registry")

    # ------------------------------------ stale memberships (stage 61 item 3)
    def prune_stale_attachments(self, tofu: str, run_id: str, cwd: Path) -> int:
        """A runner step, after the root's ``init`` and before its plan: drop
        from terraform state the membership attachments the declaration no
        longer has AND the provider no longer holds, after a state backup.
        Runs in ``cwd``, the initialised root. Exit code: 0 when nothing
        needs doing or everything was done; non-zero stops the runner before
        its plan. A provider with no such notion does nothing."""
        return 0

    # ------------------------------------------- CI login policy (stage 56)
    def can_manage_workload_access(self) -> bool:
        """Whether this builder keeps a CI login policy per managed group --
        true only when the configuration names the team's workload
        connection and role (WORKLOAD_CONNECTION.md), both made by hand
        once. A provider without workload identity makes no claim."""
        return False

    def workload_access_expected(self, group: str) -> dict[str, Any] | None:
        """What the configuration expects for ``group``: the connection and
        role it names and the CI policy's name. Structural, no network; the
        identity read-model records it so the state query can compare."""
        return None

    def workload_access_state(self, group: str) -> dict[str, Any] | None:
        """Reality: ``{connection: {present, active}, role: {present, id},
        policy: {present, id, mirrors}}`` for ``group``, or None when the
        provider could not be asked (never an absent policy)."""
        return None

    def ensure_workload_access(self, group: str) -> dict[str, Any]:
        """Make ``group``'s CI login policy exist as a copy of its standing
        user policy with the workload role as the only principal: created,
        updated or unchanged, reported as ``{action, policy, id, role_id}``.
        Raises when it cannot -- a policy that was not written must not be
        recorded as one."""
        raise NotImplementedError(f"{self.__class__.__name__} keeps no CI login policy")

    # ------------------------------------------- EXPLORE identity hooks
    def validate_attributes(self, group: Any, attributes: dict[str, Any]) -> list[str]:
        """Names/types of declarable provider attributes. Default: none."""
        return [f"group '{group.get_name()}': builder {self.name} ({self.get_type()}) supports no attributes "
                f"(declared {sorted(attributes)})"] if attributes else []

    def query_attributes(self, group: Any) -> dict[str, Any] | None:
        """The provider's current attributes for one group (read-only)."""
        raise NotImplementedError

    def attribute_conflicts(self) -> list[dict[str, Any]] | None:
        """Provider-reported attribute conflicts (read-only), if it has such
        a notion; ``None`` when it cannot ask."""
        raise NotImplementedError

    @classmethod
    def export_gids(cls, query: dict[str, str], groups: list[str]) -> dict[str, int]:
        """The queryable gid mechanism (N7): answer ``{group: gid}`` for the
        requested groups from the provider, read-only, credentials from the
        environment. Plugins whose terraform provider already exposes gids
        need not implement this."""
        raise NotImplementedError(
            f"{cls.__name__} does not implement a gid shim; its terraform root must "
            "expose gids some other queryable way (N7)")
