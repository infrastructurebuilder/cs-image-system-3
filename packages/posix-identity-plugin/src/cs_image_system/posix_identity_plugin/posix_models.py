# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The posix identity plugin's builder models (stage 75): a group builder and
a user builder, both ``type: posix``, both without a terraform root -- the
accounts they describe live on the machines, written there by the bake (a
group) and by the accounts script after launch (users, memberships, keys,
sudo)."""

from __future__ import annotations

from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.models.group_builder import GroupBuilderModel
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from cs_image_system.base.models.user_builder import UserBuilderModel

POSIX: str = "posix"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PosixGroupBuilderModel(GroupBuilderModel):
    """Groups that exist as POSIX groups on the machines of their images.

    Attributes:
        shell: the login shell of the accounts this builder's users get.
        admin_sudo: the group's ``admins`` may run anything as root without
            a password (their accounts have none: keys only). False leaves
            sudo to the operator.
    """
    shell: str = "/bin/bash"
    admin_sudo: bool = True

    @classmethod
    def csis_name(cls) -> str:
        return POSIX


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PosixUserBuilderModel(UserBuilderModel):
    """Users that exist as POSIX accounts: a ``uid`` each, a user-private
    group of the same name and id, and their ``public_keys`` as the only way
    in. No directory is asked: the configuration is the authority."""
    email_as_username: bool = False

    @classmethod
    def csis_name(cls) -> str:
        return POSIX
