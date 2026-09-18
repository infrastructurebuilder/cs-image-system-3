# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import Annotated, Any
from dataclasses import field
from pydantic import field_validator, Field
from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
import logging

from ..encryption import EncryptedStr
from ..helpers.field_helpers import fk_field, templated_field
from ..protocols.name_typed_protocol import SelfInjectedNameProtocol
from ..protocols.parent_property_holding_protocol import ParentPropertyHoldingProtocol

log = logging.getLogger(__name__)

from ..constants import DEFAULT, OOPS_DEFAULTS, VCT

from .root_item import RootItem


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class User(RootItem, SelfInjectedNameProtocol, ParentPropertyHoldingProtocol):
    """A user data object.

    Aliases are invalid for user names at this time
    Tags cannot be applied to users at this time

    Attributes
    ----------
    first_name: str
        The user's given name. Required — never derived from ``name``.
    last_name: str
        The user's family name. Required — never derived from ``name``.
    is_service_account: bool
        Whether the user is a service account.
    """
    type_: Annotated[str, Field(alias="type")] = fk_field(target = VCT.USER_BUILDER_MODEL,
                         also_set_on_update="model_id",
                         default = DEFAULT, metadata={
                            "description": (f"The type of the item. "
                                            f"For User items, this should probably "
                                            f"always be {DEFAULT}."),
                            "required": True,
                        })
    description: str | None = templated_field(replace_value = "{{ builder.default_user_description_template }}" ,
                                              default = DEFAULT)
    # Required (no default): a missing value fails structuring/construction.
    # Note the "required": True *metadata* used elsewhere is not enforcement --
    # it only back-fills defaults (see orchestrator.field_is_required).
    # stage 33: a user's identifying fields may be declared encrypted (ENC[age:...]);
    # `name` re-declared from NameTyped so the username can be too
    name: EncryptedStr
    first_name: EncryptedStr
    last_name: EncryptedStr
    middle_name: str | None = None
    email: EncryptedStr = templated_field(replace_value = "{{ builder.get_user_email_template() }}",
                                 default = DEFAULT, metadata={
        "description": "The user email or a format string",
        "required": True,
        })
    is_service_account: bool = False
    is_enabled: bool = True
    # EXPLORE identity: per-item management mode. None = the builder's
    # default (okta-tf: managed, okta-tf-ro: lookup only). A managed user is
    # emitted as a resource; an unmanaged one only as a data lookup.
    managed: bool | None = None
    # Provider attributes to hold on the identity (e.g. OPA unix_uid,
    # unix_user_name); names/types validated by the user builder's plugin.
    attributes: dict[str, Any] | None = None
    public_keys: list[str] = field(default_factory=list)
    mobile_phone: str | None = None
    honorific_prefix: str | None = None
    honorific_suffix: str | None = None
    title: str | None = None
    display_name: str | None = None
    nick_name: str | None = None
    profile_url: str | None = None
    second_email: str | None = None
    primary_phone: str | None = None
    street_address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country_code: str | None = None
    postal_address: str | None = None
    preferred_language: str | None = None
    locale: str | None = None
    timezone: str | None = None
    user_type: str | None = None
    employee_number: str | None = None
    cost_center: str | None = None
    organization: str | None = None
    division: str | None = None
    department: str | None = None
    manager_id: str | None = None
    manager: str | None = None

    _model_id: str | None = fk_field(target = VCT.USER_BUILDER_MODEL,
                                     init=False, default=None, metadata={
        "description": "The name of the model for the builder holding object is associated with",
    })

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def _names_are_non_blank_strings(cls, val: Any, info: Any) -> Any:
        """stage 23 step 2: keep this model's own wording for a None or a
        non-string. Pydantic validates types before __post_init__, so without
        this the domain message below is replaced by a generic type error."""
        if not isinstance(val, str) or not val.strip():
            raise ValueError(
                f"requires a non-blank {info.field_name} (got {val!r}); "
                "names are never derived from the user name."
            )
        return val

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.aliases:
            raise ValueError(
                f"Aliases are not allowed for User items. Found aliases: "
                f"{self.aliases} in {self.name}."
            )
        # stage 23 step 2: the blank check below still runs for "" and "  ",
        # which are valid strings. A None (or any non-string) is caught by the
        # field validator above instead, because pydantic's type check runs
        # BEFORE __post_init__ and would otherwise replace this wording with a
        # generic "Input should be a valid string".
        for f_name in ("first_name", "last_name"):
            val = getattr(self, f_name)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(
                    f"User {self.name!r} requires a non-blank {f_name} "
                    f"(got {val!r}); names are never derived from the user name."
                )

    @classmethod
    def csis_name(cls) -> str:
        return str(VCT.USER_MODEL)
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.USER_MODEL
    def get_classification(self) -> VCT:
        return self.csis_classifier()

    def format_email(self, format: str) -> None:
        if self.email in OOPS_DEFAULTS:
            if format:
                self.email = format.format(**self.__dict__)
                log.info("Setting email to {self.email}")

    def as_profile(self) -> dict[str, str]:
        """Okta REST API wire shape (camelCase, for ``POST /api/v1/users``) --
        **not** the terraform ``okta_user`` resource argument shape.

        Do not feed this into terraform emission: the resource wants
        snake_case arguments (``mobile_phone``, not ``mobilePhone``), sets
        ``login`` from email rather than name, and requires
        ``first_name``/``last_name``, which this body omits. ``OktaTFUser``
        (okta-opa-plugin) is the emitter for the resource shape. Do not
        "complete" this method by adding firstName/lastName -- that only
        makes it look more like the resource shape while remaining unusable
        for it. Currently uncalled; reserved for a future direct-API path
        such as ``query_existing_users()``.
        """
        p: dict[str, str] = {
            "email": self.email,
            "login": self.name,
        }
        if self.mobile_phone:
            p["mobilePhone"] = self.mobile_phone
        if self.honorific_prefix:
            p["honorificPrefix"] = self.honorific_prefix
        if self.honorific_suffix:
            p["honorificSuffix"] = self.honorific_suffix
        if self.title:
            p["title"] = self.title
        if self.display_name:
            p["displayName"] = self.display_name
        if self.nick_name:
            p["nickName"] = self.nick_name
        if self.profile_url:
            p["profileUrl"] = self.profile_url
        if self.second_email:
            p["secondEmail"] = self.second_email
        if self.primary_phone:
            p["primaryPhone"] = self.primary_phone
        if self.street_address:
            p["streetAddress"] = self.street_address
        if self.city:
            p["city"] = self.city
        if self.state:
            p["state"] = self.state
        if self.zip_code:
            p["zipCode"] = self.zip_code
        if self.country_code:
            p["countryCode"] = self.country_code
        if self.postal_address:
            p["postalAddress"] = self.postal_address
        if self.preferred_language:
            p["preferredLanguage"] = self.preferred_language
        if self.locale:
            p["locale"] = self.locale
        if self.timezone:
            p["timezone"] = self.timezone
        if self.user_type:
            p["userType"] = self.user_type
        if self.employee_number:
            p["employeeNumber"] = self.employee_number
        if self.cost_center:
            p["costCenter"] = self.cost_center
        if self.organization:
            p["organization"] = self.organization
        if self.division:
            p["division"] = self.division
        if self.department:
            p["department"] = self.department
        if self.manager_id:
            p["managerId"] = self.manager_id
        if self.manager:
            p["manager"] = self.manager
        return p


# Body is like this with fields from example below
# {
#   "profile": {
#     "firstName": "Isaac",
#     "lastName": "Brock",
#     "email": "isaac.brock@example.com",
#     "login": "isaac.brock@example.com",
#     "mobilePhone": "555-415-1337"
#   }
# }
