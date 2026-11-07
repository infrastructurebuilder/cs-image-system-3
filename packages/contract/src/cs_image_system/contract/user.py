# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The user kind: the people a group builder places in its
groups, looked up or managed one by one. The user item is the core's model
and ``Any`` here."""
from __future__ import annotations

from typing import Any, Protocol

from .core import BuilderModelProtocol, BuilderProtocol


class UserBuilderModelProtocol(BuilderModelProtocol, Protocol):
    """An entry under ``user_builders:``: how a user's email and description
    are derived."""

    email_as_username: bool

    default_user_description_template: str
    email_domain: str | None

    def get_user_email_template(self) -> str: ...


class UserBuilderProtocol(BuilderProtocol, Protocol):
    """A user builder: the users it holds, whether it manages or looks them
    up, and the validation and attribute queries the identity side asks."""

    def get_users_for_builder(self) -> list[Any]: ...

    def posix_id_claims(self) -> list[Any]: ...

    @classmethod
    def default_managed(cls) -> bool: ...

    def validate_user(self, user: Any) -> list[str]: ...

    def validate_attributes(self, user: Any, attributes: dict[str, Any]) -> list[str]: ...

    def query_attributes(self, user: Any) -> dict[str, Any] | None: ...

    def add_user_to_builder(self, user: Any) -> None: ...
