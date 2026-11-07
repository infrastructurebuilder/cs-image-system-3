# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The user item as Okta reads it: the core's ``User`` (name, the personal
names, email, keys, the posix uid, the management mode) plus the optional
``okta_user`` profile arguments.

This plugin injects :class:`OktaUser` under ``VCT.USER_MODEL`` as the
default item model (``main.py``), so with the plugin installed every
``users:`` item in the tree is structured into it, and a user that writes
``mobile_phone:`` or ``department:`` loads. Without the plugin the core's
``User`` is the item model, those keys are unknown, and the tree is
refused at load -- which is right: nothing installed would read them.
``OktaTFUser`` (``okta_tf_models``) emits each of these fields, when set,
as the resource argument of the same name.
"""
from __future__ import annotations

from pydantic.dataclasses import dataclass

from cs_image_system.base.models.user import User
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG

#: The optional ``okta_user`` arguments this model carries beside the core's
#: fields, in the resource's own names. ``middle_name`` is the core's.
OKTA_PROFILE_FIELDS: tuple[str, ...] = (
    "mobile_phone", "honorific_prefix", "honorific_suffix", "title", "display_name", "nick_name",
    "profile_url", "second_email", "primary_phone", "street_address", "city", "state", "zip_code",
    "country_code", "postal_address", "preferred_language", "locale", "timezone", "user_type",
    "employee_number", "cost_center", "organization", "division", "department", "manager_id", "manager",
)


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OktaUser(User):
    """A ``users:`` item with Okta's profile attributes. Every field is
    optional and emitted only when set; the core's fields keep their
    meaning and validation."""
    mobile_phone: str | None = None
    honorific_prefix: str | None = None
    honorific_suffix: str | None = None
    title: str | None = None
    # an Okta profile attribute, written by the user's YAML; it shadows the base
    # models' display property (the human-entered name) on purpose, and the
    # core's User.get_display_name keeps the base meaning
    display_name: str | None = None  # pyright: ignore[reportIncompatibleMethodOverride]
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

    @classmethod
    def klazz_yaml_key(cls) -> str:
        """The items stay under ``users:``; a subclass only adds fields."""
        return User.klazz_yaml_key()
