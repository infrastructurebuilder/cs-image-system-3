# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import Any, TypeVar

from ..models.user import User

from ..models.user_builder import UserBuilderModel

from ..constants import VCT

from .builder_base import BuilderBase
TUSER = TypeVar("TUSER", bound=UserBuilderModel)

class UserBuilderBase(BuilderBase[TUSER]):
    # Per-instance (allocated in __init__): a class-level default list would be
    # shared by every user builder, so two builders would each emit ALL users.
    local_users: list[User]

    def __init__(self, model: TUSER) -> None:
        super().__init__(model)
        self.local_users = []

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.USER_BUILDER
    
    @property
    def model(self) -> UserBuilderModel:
        return self._model
    @property
    def default_user_email_template(self) -> str:
        return self.model.get_user_email_template() if self.model.get_user_email_template() else "{{ user.name }}@example.com"
    @property
    def default_user_description_template(self) -> str:
        return self.model.get_user_description_template() if self.model.get_user_description_template() else "User {{ user.name }}"
    @property
    def email_as_username(self) -> bool:
        return self.model.email_as_username

    def add_user_to_builder(self, user: User) -> None:
        """Attach a user to this builder, enforcing email_as_username.

        Runs after template resolution, so user.email is already expanded.
        Comparison is casefolded: Okta logins are case-insensitive, so
        'Pat.Trip@example.org' vs 'pat.trip@example.org' is not a mismatch.
        """
        if self.email_as_username:
            if not user.name:
                user.name = user.email
            elif user.name.casefold() != user.email.casefold():
                raise ValueError(
                    f"Builder {self.name} sets email_as_username, but user name "
                    f"{user.name!r} != email {user.email!r}"
                )
        self.local_users.append(user)

    def get_users_for_builder(self) -> list[User]:
        """Get the users for a builder from the provider."""
        return self.local_users

    # ------------------------------------------- EXPLORE identity hooks
    @classmethod
    def default_managed(cls) -> bool:
        """Whether users of this builder are managed (emitted as resources)
        unless the item says otherwise."""
        return True

    def is_managed(self, user: User) -> bool:
        m = getattr(user, "managed", None)
        return self.default_managed() if m is None else bool(m)

    def validate_user(self, user: User) -> list[str]:
        """Item-level checks a plugin adds (e.g. a read-only builder refusing
        ``managed: true``). Default: nothing to say."""
        return []

    def validate_attributes(self, user: User, attributes: dict[str, Any]) -> list[str]:
        """Names/types of declarable provider attributes. Default: none."""
        return [f"user '{user.get_name()}': builder {self.name} ({self.get_type()}) supports no attributes "
                f"(declared {sorted(attributes)})"] if attributes else []

    def query_attributes(self, user: User) -> dict[str, Any] | None:
        """The provider's current attributes for one user (read-only), or
        ``None`` when the plugin cannot ask."""
        raise NotImplementedError
