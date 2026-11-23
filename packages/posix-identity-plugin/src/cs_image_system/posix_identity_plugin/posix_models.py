# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The posix identity plugin's builder models: a group builder and
a user builder, both ``type: posix``, both without a terraform root -- the
accounts they describe live on the machines, written there by the bake (a
group) and by the accounts script after launch (users, memberships, keys,
sudo)."""

from __future__ import annotations

from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.base.models.group import Group
from cs_image_system.base.models.group_builder import GroupBuilderModel
from cs_image_system.base.models.user_builder import UserBuilderModel
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG

POSIX: str = "posix"

#: the POSIX identity's default pool (plan D4): every POSIX id declared
#: today, clear of the system's accounts and of every range Okta has used
DEFAULT_ID_POOL: tuple[int, int] = (3000, 59999)


def checked_pool(pool: tuple[int, int], owner: str) -> tuple[int, int]:
    """``pool`` as a pair, refused unless it lies above the system's own
    accounts with its first id below its last."""
    low, high = (int(pool[0]), int(pool[1]))
    if not Group.MIN_GID <= low < high:
        raise ValueError(f"{owner}: id_pool {low}-{high} must start at {Group.MIN_GID} or above, "
                         "its first id below its last")
    return low, high


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PosixGroupBuilderModel(GroupBuilderModel):
    """Groups that exist as POSIX groups on the machines of their images.

    Attributes:
        id_pool: the ids a group without a ``gid:`` may be given (the lowest
            free one, recorded for good); ``[3000, 59999]`` by default.
        shell: the login shell of the accounts this builder's users get.
        admin_sudo: the group's ``admins`` may run anything as root without
            a password (their accounts have none: keys only). False leaves
            sudo to the operator.
    """
    shell: str = "/bin/bash"
    admin_sudo: bool = True
    id_pool: tuple[int, int] = DEFAULT_ID_POOL

    def __post_init__(self) -> None:
        super().__post_init__()
        self.id_pool = checked_pool(self.id_pool, f"group builder {self.name}")

    @classmethod
    def csis_name(cls) -> str:
        return POSIX


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PosixUserBuilderModel(UserBuilderModel):
    """Users that exist as POSIX accounts: a ``uid`` each (declared, or
    drawn from ``id_pool`` and recorded), a user-private group of the same
    name and id, and their ``public_keys`` as the only way in. No directory
    is asked: the configuration and the run's records are the authority.

    Attributes:
        id_pool: the ids a user without a ``uid:`` may be given (the lowest
            free one, recorded for good), shared with the group builder's.
    """
    email_as_username: bool = False
    id_pool: tuple[int, int] = DEFAULT_ID_POOL

    def __post_init__(self) -> None:
        super().__post_init__()
        self.id_pool = checked_pool(self.id_pool, f"user builder {self.name}")

    @classmethod
    def csis_name(cls) -> str:
        return POSIX
