# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The posix identity plugin's builders (stage 75).

The group builder's identity type is ``posix``, its gid policy
``config-time``: a group's ``gid:`` is declared, the configuration is the
authority, and generated IaC writes the number (no identity root, no
remote state). A base image declaring ``identity_types: [posix]`` checks
that the shadow tools and sudo are there; an instance image owned by a
posix group BAKES that group (adopted when it already stands equal,
refused when it stands different). Users, memberships, keys and sudo come
after launch, from the same accounts script (step 4).

The user builder holds users with a declared ``uid:``; each gets a
user-private group of the same name and id. Neither builder generates
terraform or runs a command of its own in any lifecycle.
"""

from __future__ import annotations

from typing import Any

from cs_image_system.base.basic.asset import AssetSet
from cs_image_system.base.basic.builder_base_group import GID_POLICY_CONFIG_TIME, GroupBuilderBase
from cs_image_system.base.basic.builder_base_user import UserBuilderBase
from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
from cs_image_system.base.models.executable_adds import CFExecutables
from cs_image_system.base.models.group import Group
from cs_image_system.base.models.user import User
from cs_image_system.base.posix_ids import Claim

from . import accounts
from .posix_models import POSIX, PosixGroupBuilderModel, PosixUserBuilderModel

TOOLS = ("groupadd", "useradd", "gpasswd", "visudo")
HEREDOC = "CSIS_POSIX_ACCOUNTS"


def _declared_gid(group: Group) -> int | None:
    gid = getattr(group, "gid", None)
    return gid if isinstance(gid, int) and not isinstance(gid, bool) else None


class _NoGeneration:
    """Neither builder writes a terraform root or runs a lifecycle command."""

    def generate_items_before(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return AssetSet()

    def generate_items_during(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return AssetSet()

    def generate_items_after(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return AssetSet()

    def get_commands_to_run_before(self, phase: ExecutionLifecyclePhase) -> CFExecutables:
        return CFExecutables([], [])

    def get_commands_to_run_during(self, phase: ExecutionLifecyclePhase) -> CFExecutables:
        return CFExecutables([], [])

    def get_commands_to_run_after(self, phase: ExecutionLifecyclePhase) -> CFExecutables:
        return CFExecutables([], [])


class PosixGroupBuilder(_NoGeneration, GroupBuilderBase[PosixGroupBuilderModel]):
    @classmethod
    def csis_name(cls) -> str:
        return POSIX

    @property
    def model(self) -> PosixGroupBuilderModel:
        return self._model  # type: ignore[return-value]

    @classmethod
    def identity_type(cls) -> str:
        return POSIX

    def gid_policy(self) -> str:
        return GID_POLICY_CONFIG_TIME

    # ------------------------------------------------ gids are configuration
    def gid_workspace(self) -> str | None:
        return None

    def gid_expression(self, group: str) -> str | None:
        found = next((g for g in self.get_groups_for_builder() if g.get_name() == group), None)
        gid = _declared_gid(found) if found is not None else None
        return str(gid) if gid is not None else None

    def posix_id_claims(self) -> list[Claim]:
        return [Claim("the configuration", "group", g.get_name(), _declared_gid(g), rank=20)
                for g in self.get_groups_for_builder()]

    # ------------------------------------------------------- the bake
    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]:
        return [f"# identity type '{POSIX}' prerequisites ({self.get_name()}): the shadow tools and sudo, "
                "present on every supported family -- checked, not installed",
                " && ".join(f"command -v {t} >/dev/null" for t in TOOLS)]

    def verify_commands(self, os_family: str | None = None) -> list[str]:
        return [f"# verify: {', '.join(TOOLS)} present", *(f"command -v {t} >/dev/null" for t in TOOLS)]

    def activation_commands(self, image: Any, group: Group) -> list[str]:
        """Bake the image's owning group with its declared gid -- adopted when
        it already stands equal, refused when it stands different."""
        gid = _declared_gid(group)
        if gid is None:
            raise ValueError(f"posix group {group.get_name()} declares no gid (validate refuses this first)")
        script = accounts.header() + accounts.group_part(group.get_name(), gid)
        return [f"# identity activation for group '{group.get_name()}' ({POSIX}) on image {image.get_name()}",
                f"sudo bash -s <<'{HEREDOC}'", *script, HEREDOC]

    def activation_verify_commands(self, image: Any, group: Group) -> list[str]:
        gid = _declared_gid(group)
        return [f"# verify: group '{group.get_name()}' stands with gid {gid}",
                f"test \"$(getent group {group.get_name()} | cut -d: -f3)\" = '{gid}'"]

    # ------------------------------------------------------- attributes
    def validate_attributes(self, group: Any, attributes: dict[str, Any]) -> list[str]:
        return [f"group '{group.get_name()}': a posix group declares its id as `gid:`, not as attributes "
                f"(declared {sorted(attributes)})"] if attributes else []


class PosixUserBuilder(_NoGeneration, UserBuilderBase[PosixUserBuilderModel]):
    @classmethod
    def csis_name(cls) -> str:
        return POSIX

    def query_existing_users(self) -> list[User]:
        return []

    def posix_id_claims(self) -> list[Claim]:
        out: list[Claim] = []
        for u in self.get_users_for_builder():
            uid = getattr(u, "uid", None)
            uid = uid if isinstance(uid, int) and not isinstance(uid, bool) else None
            out.append(Claim("the configuration", "user", u.get_name(), uid, rank=20))
            # the user-private group: same name, same id
            out.append(Claim("the configuration (user-private group)", "group", u.get_name(), uid, rank=20,
                             derived=True))
        return out

    def validate_attributes(self, user: User, attributes: dict[str, Any]) -> list[str]:
        return [f"user '{user.get_name()}': a posix user declares its id as `uid:`, not as attributes "
                f"(declared {sorted(attributes)})"] if attributes else []
