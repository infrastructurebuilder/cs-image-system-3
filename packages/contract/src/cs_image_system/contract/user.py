# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The user kind (stage 30): the people a group builder places in its
groups, looked up or managed one by one. The user item is the core's model
and ``Any`` here."""
from __future__ import annotations

from typing import Any, Protocol

from .core import BuilderModelProtocol, BuilderProtocol


class UserBuilderModelProtocol(BuilderModelProtocol, Protocol):
    """An entry under ``user_builders:``: how a user's email and description
    are derived."""

    default_user_email_template: str
    default_user_description_template: str
    email_domain: str | None
    email_as_username: bool

    def get_user_email_template(self) -> str: ...

    def get_user_description_template(self) -> str: ...

    def get_email_domain(self) -> str | None: ...


class UserBuilderProtocol(BuilderProtocol, Protocol):
    """A user builder: the users it holds, whether it manages or looks them
    up, and the validation and attribute queries the identity side asks."""

    @property
    def default_user_email_template(self) -> str: ...

    @property
    def default_user_description_template(self) -> str: ...

    @property
    def email_as_username(self) -> bool: ...

    def add_user_to_builder(self, user: Any) -> None: ...

    def get_users_for_builder(self) -> list[Any]: ...

    def posix_id_claims(self) -> list[Any]: ...

    @classmethod
    def default_managed(cls) -> bool: ...

    def is_managed(self, user: Any) -> bool: ...

    def validate_user(self, user: Any) -> list[str]: ...

    def validate_attributes(self, user: Any, attributes: dict[str, Any]) -> list[str]: ...

    def query_attributes(self, user: Any) -> dict[str, Any] | None: ...
