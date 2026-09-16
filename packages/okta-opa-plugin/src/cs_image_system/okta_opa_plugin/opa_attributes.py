# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Declarable OPA attributes (EXPLORE identity).

Names and types come from the OPA Attributes API as observed read-only on
the live team (2026-08-27): groups carry ``unix_gid``, ``unix_group_name``,
``windows_group_name``; users carry ``unix_uid``, ``unix_gid``,
``unix_user_name``, ``windows_user_name`` (plus Active Directory identities
the system does not manage). Every attribute record also carries OPA's own
``managed`` flag -- ``true`` when an admin set the value, ``false`` when OPA
generated it -- which is exactly the distinction a declared attribute
makes.
"""
from __future__ import annotations

from typing import Any

OPA_GROUP_ATTRIBUTES: dict[str, type] = {
    "unix_gid": int,
    "unix_group_name": str,
    "windows_group_name": str,
}
OPA_USER_ATTRIBUTES: dict[str, type] = {
    "unix_uid": int,
    "unix_gid": int,
    "unix_user_name": str,
    "windows_user_name": str,
}

MIN_ID = 1024  # ids below are reserved for the system (Group.MIN_GID)


def validate_opa_attributes(where: str, attributes: dict[str, Any],
                            allowed: dict[str, type]) -> list[str]:
    errors: list[str] = []
    for name, value in sorted(attributes.items()):
        expected = allowed.get(name)
        if expected is None:
            errors.append(f"{where}: unknown OPA attribute {name!r} (known: {sorted(allowed)})")
            continue
        if isinstance(value, bool) or not isinstance(value, expected):
            errors.append(f"{where}: OPA attribute {name!r} must be {expected.__name__}, got {value!r}")
            continue
        if expected is int and value < MIN_ID:
            errors.append(f"{where}: OPA attribute {name!r} = {value} is below the reserved range ({MIN_ID})")
        if expected is str and not value.strip():
            errors.append(f"{where}: OPA attribute {name!r} must not be empty")
    return errors
