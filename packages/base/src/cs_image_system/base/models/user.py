# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from dataclasses import field
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.contract.fields import fk_field, parent_field, templated_field
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG

from ..encryption import EncryptedStr
from .mixins import ParentPropertyHolding, SelfInjectedName

log = logging.getLogger(__name__)

from cs_image_system.contract.constants import DEFAULT, OOPS_DEFAULTS, VCT

from .root_item import RootItem


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class User(RootItem, SelfInjectedName, ParentPropertyHolding):
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
    # a user's identifying fields may be declared encrypted (ENC[age:...]);
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
    # default (a managing builder: managed; a lookup-only one: lookup only).
    # A managed user is emitted as a resource; an unmanaged one only as a
    # data lookup.
    managed: bool | None = None
    # Provider attributes to hold on the identity (e.g. OPA unix_uid,
    # unix_user_name); names/types validated by the user builder's plugin.
    attributes: dict[str, Any] | None = None
    # a POSIX uid the configuration declares (the posix user builder);
    # the twin of Group.gid. None: no id declared here (another side may own it)
    uid: int | None = None
    public_keys: list[str] = field(default_factory=list)
    # An identity plugin that keeps more on a user (a directory's profile
    # attributes) declares a subclass carrying those fields and injects it
    # under VCT.USER_MODEL as the default; the loader then structures every
    # `users:` item into it, and a tree that writes such a field loads only
    # with that plugin installed (an unknown key is refused).

    _model_id: str | None = parent_field(VCT.USER_BUILDER_MODEL, description="The name of the model for the builder holding object is associated with")

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def _names_are_non_blank_strings(cls, val: Any, info: Any) -> Any:
        """Keep this model's own wording for a None or a
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
        # the blank check below still runs for "" and "  ",
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

    def get_display_name(self) -> str:
        """The human-entered name, as on every model. Kept explicit here
        because an identity plugin's user subclass may declare a profile
        attribute called ``display_name`` that shadows the base property;
        this method keeps the base meaning whatever the subclass adds."""
        return getattr(self, "_display_name", None) or self.name

    def get_self_injected_name(self) -> str:
        """Every user item enters the Jinja context as ``user`` (the
        templates say ``{{ user.name }}``), whatever subclass an identity
        plugin injected it as."""
        return "user"

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
