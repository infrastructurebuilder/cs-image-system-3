# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Read-only user provider via Terraform/Tofu for existing Okta users.

Emits ONLY ``data "okta_user"`` lookups -- never creates or modifies Okta
identities. Use it to reference pre-existing users from other roots.
EXPLORE identity: the emission lives in OktaTfUserBuilder, chosen per
item by ``managed``; this type only flips the default to "lookup" and
refuses ``managed: true``.
"""


from .okta_opa_tf_user_builder import OktaTfUserBuilder
from .okta_opa_tf_user_models import OktaTfUserRoBuilderModel
from cs_image_system.base.models.user import User

from .okta_tf_models import OKTATF, OKTATF_RO


class OktaTfUserRoBuilder(OktaTfUserBuilder):
    """Read-only Okta user builder: a data-source-only terraform root.

    Inherits the workspace scaffolding and credential-gated commands from
    OktaTfUserBuilder; only the emission differs (no okta_user resources).
    """

    @classmethod
    def csis_name(cls) -> str:
        return OKTATF_RO

    @property
    def model(self) -> OktaTfUserRoBuilderModel:
        return self._model  # type: ignore   # FIXME: This is dangerous

    @classmethod
    def default_managed(cls) -> bool:
        return False

    def validate_user(self, user: User) -> list[str]:
        """The read-only builder never creates: an explicit ``managed: true``
        is a configuration error, not a quiet upgrade to resources."""
        if getattr(user, "managed", None) is True:
            return [f"user '{user.get_name()}': builder {self.name} is {OKTATF_RO} (read-only) and cannot "
                    f"manage users; move the user to an {OKTATF} builder"]
        return []
