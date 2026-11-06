# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The words of identity a group or user plugin answers with: who defines a
group's gid and when (the gid policies), and one side's claim on a name
and an id (what the core reconciles ids from). The reconciliation itself
is the core's."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: GID authority policies: who defines a group's gid, and when.
GID_POLICY_CONFIG_TIME = "config-time"      # settable in the configuration (groupadd-style)
GID_POLICY_CREATION_ONLY = "creation-only"  # settable only when the group is created (a directory that assigns ids)
GID_POLICY_PROVIDER_ASSIGNED = "provider-assigned"

#: What a claim names: a group or a user.
ClaimKind = Literal["group", "user"]

#: an id a side will supply at a later moment (a provider read at bake)
DEFERRED = "deferred"


@dataclass(frozen=True)
class Claim:
    """One side's knowledge of one name: an id, None (the name only), or
    DEFERRED (an id that side will supply later). ``rank`` orders the sides
    -- lower resolves first (3: a provider before the configuration)."""
    side: str
    kind: ClaimKind
    name: str
    id: int | None | str = None
    rank: int = 50
    #: a claim that follows from another (a user's private group from the
    #: user): resolved like any other, but its name and id are checked once,
    #: on the claim it follows from
    derived: bool = False
