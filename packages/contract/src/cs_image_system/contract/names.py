# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The two name normalisations the system applies everywhere, defined
here alone: the core imports them from here as a plugin does
(``cs_image_system.base.utils`` imports ``safe_name`` for its own name
checks and re-exports neither). A model's ``name`` is ``safe_name`` of
what was written; a name that becomes a terraform label, a file name or a
state key goes through ``super_safe_name``."""

from __future__ import annotations


def safe_name(name: str) -> str:
    """Convert a name to a safe format by replacing spaces with underscores
    and converting to lowercase."""
    if not name:
        raise ValueError("Name cannot be empty or None.")
    return name.strip().replace(" ", "_").replace(":", "_").lower()


def super_safe_name(name: str) -> str:
    return (
        safe_name(name)
        .replace(":", "_")
        .replace("+", "_")
        .replace(" ", "_")
        .replace(".", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("-", "_")
        .replace("@", "_")  # user names are emails (email_as_username)
    )
