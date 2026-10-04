# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""POSIX ids across sides (stage 75): the operator's rule, in one pass.

A POSIX name -- a group or a user -- can be known to several SIDES: an
identity provider that assigns ids (OPA), the configuration, the machine.
The rule (operator, 2026-10-03):

1. Two sides that each supply an id for one name and disagree: a
   CONFIGURATION ERROR, naming both sides and both ids.
2. A side that knows only the name takes the other side's id.
3. Resolution is serial: sides that SUPPLY ids come first (a provider that
   assigns them, then the configuration), sides that need not supply them
   after.
4. A name no side supplies an id for is refused (a conservative reading:
   shared storage is owned by number, so every machine must agree on it) --
   unless a side has said its id will come LATER (a provider read at bake,
   not at validate), which defers the name instead.

Two names holding one id within a kind (two groups with one gid, two users
with one uid) are refused as well: the machine could not tell them apart.

The same pass serves every moment the plan names: ``validate`` (the
configuration against itself), the bake (a provider's gid against a
declared one) and the machine (the accounts script applies the last two
rules on the spot). It is pure: claims in, ids and problems out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

Kind = Literal["group", "user"]

#: a name groupadd and useradd take on every supported family: lower case, a
#: letter or underscore first, at most 32 characters; the dot is allowed
#: because OPA names its accounts `first.last`
NAME_RE = re.compile(r"^[a-z_][a-z0-9._-]{0,31}$")

#: ids below this are refused: the system's own accounts live there, and the
#: Group model already refuses a gid below it at load (the same floor for uids)
FIRST_REGULAR_ID = 1024

#: an id a side will supply at a later moment (a provider read at bake)
DEFERRED = "deferred"


@dataclass(frozen=True)
class Claim:
    """One side's knowledge of one name: an id, None (the name only), or
    DEFERRED (an id that side will supply later). ``rank`` orders the sides
    -- lower resolves first (3: a provider before the configuration)."""
    side: str
    kind: Kind
    name: str
    id: int | None | str = None
    rank: int = 50
    #: a claim that follows from another (a user's private group from the
    #: user): resolved like any other, but its name and id are checked once,
    #: on the claim it follows from
    derived: bool = False


@dataclass
class Resolution:
    ids: dict[tuple[Kind, str], int] = field(default_factory=dict)
    deferred: set[tuple[Kind, str]] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)


def supplied_id(claim: Claim) -> int | None:
    """The id ``claim`` supplies, when it supplies one."""
    i = claim.id
    return i if isinstance(i, int) and not isinstance(i, bool) else None


def resolve_posix_ids(claims: Iterable[Claim]) -> Resolution:
    out = Resolution()
    by_name: dict[tuple[Kind, str], list[Claim]] = {}
    for c in claims:
        by_name.setdefault((c.kind, c.name), []).append(c)
    for key in sorted(by_name):
        kind, name = key
        ordered = sorted(by_name[key], key=lambda c: (c.rank, c.side))
        supplied = [(c, i) for c in ordered if (i := supplied_id(c)) is not None]
        first = supplied[0] if supplied else None
        clash = next(((c, i) for c, i in supplied[1:] if i != first[1]), None) if first else None
        if first is not None and clash is not None:
            out.problems.append(
                f"{kind} {name}: {first[0].side} supplies id {first[1]} and {clash[0].side} supplies {clash[1]} "
                f"-- one name, two ids is a configuration error")
        elif first is not None:
            out.ids[key] = first[1]            # every other side takes it (rule 2)
        elif any(c.id == DEFERRED for c in ordered):
            out.deferred.add(key)
        else:
            sides = ", ".join(sorted({c.side for c in ordered}))
            out.problems.append(f"{kind} {name}: no side supplies its id ({sides}); declare one "
                                f"(`{'gid' if kind == 'group' else 'uid'}:`)")
    for kind in ("group", "user"):
        holders: dict[int, list[str]] = {}
        for (k, name), i in out.ids.items():
            if k == kind:
                holders.setdefault(i, []).append(name)
        for i, names in sorted(holders.items()):
            if len(names) > 1:
                out.problems.append(f"{kind}s {', '.join(sorted(names))} all have id {i} "
                                    f"-- a machine could not tell them apart")
    return out
