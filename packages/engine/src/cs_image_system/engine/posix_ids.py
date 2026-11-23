# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""POSIX ids across sides and identities: the operator's rule, in one pass.

A POSIX name -- a group or a user -- can be known to several SIDES: an
identity whose provider assigns ids itself (an EXTERNAL identity),
the configuration, the machine, and the ids the tree has already
RECORDED (``meta-state/ids.yaml``). The rule (the operator's; spec 010):

1. Two sides that each supply an id for one name and disagree: a
   CONFIGURATION ERROR, naming both sides and both ids. Between two
   external identities nothing defers.
2. A side that knows only the name takes the other side's id. The POSIX
   identity is the final fallback: a POSIX name an external identity holds
   takes that identity's id, and a different declared id is refused,
   saying which it must be.
3. Resolution is serial: a recorded id first (it never changes), then the
   sides that SUPPLY ids (an external identity, then the configuration),
   then the sides that need not supply them.
4. A name no side supplies an id for draws one from its identity's POOL:
   the lowest id of the pool that no name holds, claims or once held (users
   and groups alike, so a user and its private group draw one id); once
   recorded it never moves. A side that says its id will come LATER (a
   provider read at bake, not at validate) defers the name instead. An
   identity with no pool cannot draw, and the name is refused.

Pools: two identities' pools never overlap, a pool never lies over an id
another identity has recorded, and a declared id not yet recorded never
lies in another identity's pool. Every identity that does not assign ids
itself (every builder of the POSIX identity) is one party: its pools may
coincide, since this one pass draws for all of them. A recorded id that a
pool change leaves outside its pool is kept, and noted.

Two names holding one id within a kind (two groups with one gid, two users
with one uid) are refused as well: the machine could not tell them apart.
An id the tree once recorded for a name it no longer declares (retired) is
never another name's; the name it was held by may take it back.

The same pass serves every moment the plan names: ``validate`` (the
configuration against itself), the bake (a provider's gid against a
declared one) and the machine (the accounts script applies the last two
rules on the spot). It is pure: claims in, ids and problems out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# The claim and its words are the contract's (`contract.identity_vocabulary`); this path keeps them.
from cs_image_system.contract.identity_vocabulary import DEFERRED, Claim  # noqa: F401, E402
from cs_image_system.contract.identity_vocabulary import ClaimKind as Kind

#: a name groupadd and useradd take on every supported family: lower case, a
#: letter or underscore first, at most 32 characters; the dot is allowed
#: because OPA names its accounts `first.last`
NAME_RE = re.compile(r"^[a-z_][a-z0-9._-]{0,31}$")

#: ids below this are refused: the system's own accounts live there, and the
#: Group model already refuses a gid below it at load (the same floor for uids)
FIRST_REGULAR_ID = 1024

#: the party every identity that does not assign ids itself belongs to
POSIX_PARTY = "the POSIX identity"


@dataclass(frozen=True)
class Pool:
    """An identity's pool: the ids it may give, ``low`` to ``high``
    inclusive. ``external``: the identity assigns ids itself."""
    identity: str
    low: int
    high: int
    external: bool = False

    @property
    def party(self) -> str:
        return self.identity if self.external else POSIX_PARTY

    def __str__(self) -> str:
        return f"{self.identity}'s pool {self.low}-{self.high}"


@dataclass
class Resolution:
    ids: dict[tuple[Kind, str], int] = field(default_factory=dict)
    deferred: set[tuple[Kind, str]] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)
    #: the identity each resolved name's id belongs to ("" when no claim says)
    identities: dict[tuple[Kind, str], str] = field(default_factory=dict)
    #: POSIX names that take an external namesake's id: name -> that identity
    defers: dict[tuple[Kind, str], str] = field(default_factory=dict)
    #: the names whose id is an external identity's (it cannot move)
    externals: set[tuple[Kind, str]] = field(default_factory=set)
    #: how each resolved id came: recorded, declared, read (an external
    #: identity's) or pooled (drawn this run)
    hows: dict[tuple[Kind, str], str] = field(default_factory=dict)
    #: what the run keeps but says: a recorded id outside its pool
    notes: list[str] = field(default_factory=list)
    #: the names only a user's private group claims (recorded on the user)
    private_groups: set[tuple[Kind, str]] = field(default_factory=set)


def supplied_id(claim: Claim) -> int | None:
    """The id ``claim`` supplies, when it supplies one."""
    i = claim.id
    return i if isinstance(i, int) and not isinstance(i, bool) else None


def _who(c: Claim, other: Claim | None = None) -> str:
    """A claim's side, with the identity it comes from when that tells it
    apart from ``other``'s (two sides of one identity need no naming)."""
    if c.identity and (other is None or other.identity != c.identity):
        return f"{c.side} ({c.identity})"
    return c.side


def _recorded(recorded: dict | None) -> tuple[dict[tuple[Kind, str], dict], dict[tuple[Kind, str], int]]:
    """The records' current ids and retired ids, keyed by (kind, name)."""
    doc = recorded or {}
    current = {(kind, str(n)): dict(r) for kind in ("group", "user")
               for n, r in ((doc.get("ids") or {}).get(kind) or {}).items() if isinstance(r, dict)}
    retired = {(kind, str(n)): int(i) for kind in ("group", "user")
               for n, i in ((doc.get("retired") or {}).get(kind) or {}).items()}
    return current, retired  # type: ignore[return-value]


def resolve_posix_ids(claims: Iterable[Claim], recorded: dict | None = None,
                      pools: Iterable[Pool] = ()) -> Resolution:
    """Resolve every claim, with the tree's recorded ids (``ids.yaml``'s
    document, or None for none) as the first side and each identity's
    ``pools`` to draw from: ids in, ids and problems out. Pure."""
    out = Resolution()
    pools = list(pools)
    current, retired = _recorded(recorded)
    claims = list(claims)
    by_name: dict[tuple[Kind, str], list[Claim]] = {}
    for c in claims:
        by_name.setdefault((c.kind, c.name), []).append(c)
    only_derived = out.private_groups
    pending: list[tuple[tuple[Kind, str], list[Claim]]] = []
    for key in sorted(by_name):
        ordered = sorted(by_name[key], key=lambda c: (c.rank, c.side))
        if all(c.derived for c in ordered):
            only_derived.add(key)
        rec = current.get(key)
        if any(c.external and supplied_id(c) is not None for c in ordered):
            _resolve_external(key, ordered, rec, out)
        elif rec is not None:
            _resolve_recorded(key, ordered, rec, out)
        elif _resolve_declared(key, ordered, retired.get(key), out):
            pending.append((key, ordered))
    _check_pools(pools, current, out)
    taken = ({i for c in claims if (i := supplied_id(c)) is not None} | set(out.ids.values())
             | {int(r["id"]) for r in current.values() if isinstance(r.get("id"), int)} | set(retired.values()))
    _draw(pending, pools, taken, out)
    # a recorded name no builder claims now is held as a retired one is: the
    # next recording retires it, and its id is never another name's
    unclaimed = {k: int(r["id"]) for k, r in current.items() if k not in by_name and isinstance(r.get("id"), int)}
    for kind in ("group", "user"):
        _check_across_names(kind, out, {**retired, **unclaimed}, only_derived)
    return out


def _resolve_external(key: tuple[Kind, str], ordered: list[Claim], rec: dict | None, out: Resolution) -> None:
    """A name an external identity supplies an id for: that id stands, and
    the POSIX identity defers to it (rule 2)."""
    kind, name = key
    externals = [(c, i) for c in ordered if c.external and (i := supplied_id(c)) is not None]
    first_c, first_i = externals[0]
    other = next(((c, i) for c, i in externals[1:] if i != first_i), None)
    if other is not None:
        out.problems.append(
            f"{kind} {name}: {_who(first_c)} holds id {first_i} and {_who(other[0])} holds {other[1]} "
            f"-- two external identities disagree on one name, a configuration error")
        return
    if rec is not None and rec.get("id") != first_i:
        if rec.get("external"):
            out.problems.append(
                f"{kind} {name}: recorded with id {rec.get('id')}, and {_who(first_c)} now reports "
                f"{first_i}; a recorded id does not change")
        else:
            out.problems.append(
                f"{kind} {name}: recorded with id {rec.get('id')} ({rec.get('identity') or 'the records'}), "
                f"and {_who(first_c)} now holds it with id {first_i}; one of the names must change "
                "-- neither id moves")
        return
    wrong = [(c, i) for c in ordered if not c.external and (i := supplied_id(c)) is not None and i != first_i]
    if wrong:
        c, i = wrong[0]
        out.problems.append(
            f"{kind} {name}: {_who(c)} declares id {i}, but {_who(first_c)} holds {name} with id "
            f"{first_i}; the POSIX identity defers to it, so the id must be {first_i}")
        return
    out.ids[key] = first_i
    out.identities[key] = first_c.identity
    out.hows[key] = "read"
    out.externals.add(key)
    if any(not c.external for c in ordered):
        out.defers[key] = first_c.identity


def _resolve_recorded(key: tuple[Kind, str], ordered: list[Claim], rec: dict, out: Resolution) -> None:
    """A name the tree has recorded: its recorded id stands (rule 3)."""
    kind, name = key
    moved = [(c, i) for c in ordered if (i := supplied_id(c)) is not None and i != rec.get("id")]
    if moved:
        c, i = moved[0]
        out.problems.append(
            f"{kind} {name}: recorded with id {rec.get('id')}, and {_who(c)} declares {i}; "
            "a recorded id does not change")
        return
    out.ids[key] = int(rec["id"])
    out.identities[key] = str(rec.get("identity") or (ordered[0].identity if ordered else ""))
    out.hows[key] = "recorded"
    if rec.get("external"):
        out.externals.add(key)


def _resolve_declared(key: tuple[Kind, str], ordered: list[Claim], retired_id: int | None,
                      out: Resolution) -> bool:
    """A name neither recorded nor external: the sides' declared ids (rules
    1 and 2), and a retired id its own name takes back. True when no side
    supplies an id and none defers it: the name draws from its pool."""
    kind, name = key
    supplied = [(c, i) for c in ordered if (i := supplied_id(c)) is not None]
    if retired_id is not None and supplied and supplied[0][1] != retired_id:
        c, i = supplied[0]
        out.problems.append(
            f"{kind} {name}: once recorded with id {retired_id}, and {_who(c)} declares {i}; "
            "a recorded id does not change")
        return False
    first = supplied[0] if supplied else None
    clash = next(((c, i) for c, i in supplied[1:] if i != first[1]), None) if first else None
    if first is not None and clash is not None:
        out.problems.append(
            f"{kind} {name}: {_who(first[0], clash[0])} supplies id {first[1]} and {_who(clash[0], first[0])} "
            f"supplies {clash[1]} -- one name, two ids is a configuration error")
    elif first is not None:
        out.ids[key] = first[1]            # every other side takes it (rule 2)
        out.identities[key] = first[0].identity
        out.hows[key] = "declared"
    elif any(c.id == DEFERRED for c in ordered):
        out.deferred.add(key)
    else:
        return True
    return False


def _draw(pending: list[tuple[tuple[Kind, str], list[Claim]]], pools: list[Pool], taken: set[int],
          out: Resolution) -> None:
    """Rule 4: each pending name takes the lowest free id of its identity's
    pool, users first so that a user's private group takes the user's id."""
    by_identity = {p.identity: p for p in pools}
    for key, ordered in sorted(pending, key=lambda kv: (kv[0][0] != "user", kv[0])):
        kind, name = key
        user = ("user", name)
        if key in out.private_groups and user in out.ids:
            out.ids[key] = out.ids[user]
            out.identities[key] = out.identities.get(user, "")
            out.hows[key] = out.hows.get(user, "pooled")
            continue
        if key in out.private_groups:
            continue                       # its user could not resolve; the user's problem says why
        identity = next((c.identity for c in ordered if c.identity), "")
        pool = by_identity.get(identity)
        if pool is None:
            sides = ", ".join(sorted({c.side for c in ordered}))
            out.problems.append(f"{kind} {name}: no side supplies its id ({sides}) and "
                                f"{identity or 'its identity'} has no pool to draw one from; declare one "
                                f"(`{'gid' if kind == 'group' else 'uid'}:`)")
            continue
        i = next((n for n in range(pool.low, pool.high + 1) if n not in taken), None)
        if i is None:
            out.problems.append(f"{kind} {name}: {pool} has no free id left; widen the pool or declare an id")
            continue
        taken.add(i)
        out.ids[key] = i
        out.identities[key] = identity
        out.hows[key] = "pooled"


def _check_pools(pools: list[Pool], current: dict[tuple[Kind, str], dict], out: Resolution) -> None:
    """Pools below the floor, two parties' pools that overlap, a pool over
    another party's recorded id, a declared id inside another party's
    pool; and, as a note, a recorded id outside its own pool."""
    for p in pools:
        if not FIRST_REGULAR_ID <= p.low < p.high:
            out.problems.append(f"{p} must lie above {FIRST_REGULAR_ID - 1}, its first id below its last")
    for n, a in enumerate(pools):
        for b in pools[n + 1:]:
            if a.party != b.party and max(a.low, b.low) <= min(a.high, b.high):
                out.problems.append(f"{a} and {b} overlap on {max(a.low, b.low)}-{min(a.high, b.high)}; "
                                    "two identities' pools never overlap")
    for (kind, name), rec in sorted(current.items()):
        i, who = rec.get("id"), str(rec.get("identity") or "")
        if not isinstance(i, int):
            continue
        party = who if rec.get("external") else POSIX_PARTY
        for p in pools:
            if p.party != party and p.low <= i <= p.high:
                out.problems.append(f"{p} lies over {kind} {name}'s recorded id {i} ({who or 'the records'}); "
                                    "a pool never moves over another identity's recorded id")
        own = next((p for p in pools if p.identity == who), None)
        if own is not None and not own.low <= i <= own.high:
            out.notes.append(f"{kind} {name}: its recorded id {i} lies outside {own}; kept, since a recorded "
                             "id never moves")
    for key, how in sorted(out.hows.items()):
        if how != "declared":
            continue
        i, who = out.ids[key], out.identities.get(key, "")
        for p in pools:
            if p.party != POSIX_PARTY and p.low <= i <= p.high:
                out.problems.append(f"{key[0]} {key[1]}: {who or 'the configuration'} declares id {i}, inside "
                                    f"{p}; declare an id outside it, or leave it out to draw one")


def _check_across_names(kind: str, out: Resolution, retired: dict[tuple[Kind, str], int],
                        only_derived: set[tuple[Kind, str]]) -> None:
    """Two names on one id within ``kind``, and an id recorded for a name no
    builder declares now (retired, or about to be) that another name took."""
    holders: dict[int, list[tuple[Kind, str]]] = {}
    for (k, name), i in out.ids.items():
        if k == kind:
            holders.setdefault(i, []).append((k, name))
    for i, keys in sorted(holders.items()):
        if len(keys) > 1:
            out.problems.append(_shared_id(kind, i, sorted(keys), out, only_derived))
    for (k, name), i in sorted(retired.items()):
        if k != kind or (k, name) in out.ids:
            continue
        takers = [n for (kk, n) in holders.get(i, []) if n != name]
        if takers:
            out.problems.append(
                f"{kind} {', '.join(takers)}: id {i} is recorded for {name}, which no builder declares now; an id "
                f"once held is never another name's (only {name} may take it back)")


def _shared_id(kind: str, i: int, keys: list[tuple[Kind, str]], out: Resolution,
               only_derived: set[tuple[Kind, str]]) -> str:
    """The refusal for one id held by several names, naming each name's
    identity, a user's private group as that user's, and an external
    identity's id as the one that cannot move."""
    several = len({out.identities.get(k, "") for k in keys}) > 1     # name identities only when they differ

    def label(key: tuple[Kind, str]) -> str:
        name = key[1]
        who = out.identities.get(key, "") if several else ""
        shown = f"{name}'s private group" if key in only_derived else name
        return f"{shown} ({who})" if who else shown
    named = ", ".join(label(k) for k in keys)
    externals = [k for k in keys if k in out.externals]
    if len(externals) > 1:
        return f"{kind}s {named} all have id {i} -- two external identities on one id, a configuration error"
    if externals:
        return (f"{kind}s {named} all have id {i} -- a machine could not tell them apart; "
                f"{externals[0][1]}'s id is its identity's and cannot move")
    return f"{kind}s {named} all have id {i} -- a machine could not tell them apart"


def ids_document(resolution: Resolution, recorded: dict | None, pools: Iterable[Pool], run_id: str) -> dict:
    """The ``ids.yaml`` a recording run writes: every resolved id (a user's
    private group is recorded on the user), each unchanged entry as it was
    recorded, the names that take an external namesake's id under
    ``defers``, every pool, and the names no longer declared moved to
    ``retired`` with their ids (a name declared again leaves it). Pure."""
    current, retired = _recorded(recorded)
    doc: dict = {"ids": {"group": {}, "user": {}}, "defers": {"group": {}, "user": {}}, "pools": {},
                 "retired": {"group": {}, "user": {}}}
    for (kind, name), i in sorted(resolution.ids.items()):
        if (kind, name) in resolution.private_groups:
            continue
        before = current.get((kind, name))
        if before is not None and before.get("id") == i:
            doc["ids"][kind][name] = dict(before)
            continue
        how = resolution.hows.get((kind, name), "declared")
        doc["ids"][kind][name] = {"id": i, "identity": resolution.identities.get((kind, name), ""),
                                  "external": (kind, name) in resolution.externals,
                                  "how": "declared" if how == "recorded" else how, "recorded_run": run_id}
    for (kind, name), identity in sorted(resolution.defers.items()):
        doc["defers"][kind][name] = identity
    for (kind, name), i in sorted(retired.items()):
        if (kind, name) not in resolution.ids:
            doc["retired"][kind][name] = i
    for (kind, name), rec in sorted(current.items()):
        if (kind, name) in resolution.ids or not isinstance(rec.get("id"), int):
            continue
        if (kind, name) in resolution.deferred:
            doc["ids"][kind][name] = dict(rec)         # an id to come keeps what was recorded
        else:
            doc["retired"][kind][name] = int(rec["id"])
    for pool in sorted(pools, key=lambda q: q.identity):
        doc["pools"][pool.identity] = {"min": pool.low, "max": pool.high,
                                       "how": "read" if pool.external else "declared"}
    return doc


def drawn(resolution: Resolution) -> list[str]:
    """One line per id drawn from a pool this run, for the run's log."""
    return [f"{kind} {name} takes id {i} from {resolution.identities.get((kind, name)) or 'its identity'}'s pool"
            for (kind, name), i in sorted(resolution.ids.items())
            if resolution.hows.get((kind, name)) == "pooled" and (kind, name) not in resolution.private_groups]
