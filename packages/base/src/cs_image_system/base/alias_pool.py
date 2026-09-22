# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 59: a pool of names, each spent once.

``meta-state/aliases.txt`` in the configuration is a pool of pre-approved,
memorable names, hand-written in advance, one per line. When a NEW machine
of a durable instance is about to be launched, the system takes the first
line that is not commented out, records it as that machine's alias in its
launch parameters, and comments the line out IN PLACE, on the same line,
with what took it and when. A name is therefore spent exactly once,
permanently, and the file is both the supply and the ledger.

Optional by construction: no file, no aliases, no error. The division of
bytes with the operator is the whole contract: a human only ever APPENDS
lines; the system only ever comments out lines that are already there.

The burn is the claim and it comes first: the line is rewritten before the
machine exists (the launch parameters are recorded at generation, the
apply follows), so a run that dies between the two costs one name and
never lets two machines answer to one. A dry run draws nothing and says
what it would take. A run whose instance roots may not apply draws
nothing either: a name is burned only by the run that can launch.
Ephemeral instances draw nothing -- a proof machine that comes and goes
each cycle would drain the pool for nobody. Spent is spent: a decommission
returns nothing.
"""
from __future__ import annotations

import fcntl
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)

POOL_FILE = "aliases.txt"
_SPENT_RE = re.compile(r"^\s*#\s*(?P<name>[A-Za-z0-9][A-Za-z0-9-]*)\s+--\s+(?P<record>.+?)\s*$")

# names drawn by THIS process, per run and instance: the launch parameters
# are computed more than once per run, and a second computation must find
# the name the first one burned, not burn another
_DRAWN: dict[tuple[str, str], str] = {}


@dataclass
class PoolLine:
    index: int
    text: str
    name: str | None        # a free name, or the name a spent line records; None for blanks/other comments
    spent: bool


def pool_path(config_root: Path | str) -> Path:
    from .meta_state import META_STATE_DIRNAME
    return Path(config_root) / META_STATE_DIRNAME / POOL_FILE


def parse(text: str) -> list[PoolLine]:
    out: list[PoolLine] = []
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line:
            out.append(PoolLine(i, raw, None, False))
        elif line.startswith("#"):
            m = _SPENT_RE.match(raw)
            out.append(PoolLine(i, raw, m.group("name") if m else None, True))
        else:
            out.append(PoolLine(i, raw, line, False))
    return out


def read_pool(path: Path) -> list[PoolLine]:
    return parse(path.read_text()) if path.is_file() else []


def free_names(path: Path) -> list[str]:
    return [ln.name for ln in read_pool(path) if not ln.spent and ln.name]


def spent_names(path: Path) -> dict[str, str]:
    """``{name: record}`` for every line the system has commented out."""
    out: dict[str, str] = {}
    for ln in read_pool(path):
        if ln.spent and ln.name:
            m = _SPENT_RE.match(ln.text)
            out[ln.name] = m.group("record") if m else ""
    return out


def peek(path: Path) -> str | None:
    """The name the next draw would take, without taking it."""
    free = free_names(path)
    return free[0] if free else None


def pool_problems(path: Path, *, reserved: set[str] | None = None) -> list[str]:
    """Why a free line could not be used as it stands: not a legal hostname
    label (RFC 1123, at most 63 characters -- it goes into OPA as an
    AltNames entry beside the canonical name, stage 58), a repeat of another
    free line, or a name the configuration already gives an instance."""
    from .launch_params import hostname_problems
    problems: list[str] = []
    seen: set[str] = set()
    for ln in read_pool(path):
        if ln.spent or not ln.name:
            continue
        for why in hostname_problems(ln.name):
            problems.append(f"line {ln.index + 1}: {ln.name!r} {why}")
        if ln.name in seen:
            problems.append(f"line {ln.index + 1}: {ln.name!r} repeats an earlier free line")
        seen.add(ln.name)
        if reserved and ln.name in reserved:
            problems.append(f"line {ln.index + 1}: {ln.name!r} is a name the configuration already gives an instance")
    return problems


def burn_record(taken_by: str, run_id: str, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return f"{taken_by} {when.isoformat(timespec='seconds').replace('+00:00', 'Z')} run {run_id}"


def draw(path: Path, *, taken_by: str, run_id: str, when: datetime | None = None) -> str | None:
    """Take the first free name: comment its line out in place with the
    record, under an exclusive lock, written temp-then-replace so a reader
    never sees a half-written pool. None when the pool is absent or empty.
    Two drawers in one checkout serialise on the lock; across checkouts the
    push settles it (a rejected push on this file means someone else took
    that name: re-read and draw again, never force)."""
    if not path.is_file():
        return None
    lock = path.with_suffix(path.suffix + ".lock")
    with open(lock, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            lines = read_pool(path)          # re-read under the lock
            target = next((ln for ln in lines if not ln.spent and ln.name), None)
            if target is None:
                return None
            record = burn_record(taken_by, run_id, when)
            raw = path.read_text().splitlines(keepends=True)
            ending = "\n" if raw[target.index].endswith("\n") else ""
            raw[target.index] = f"# {target.name}  -- {record}{ending}"
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text("".join(raw))
            tmp.replace(path)
            return target.name
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def _new_machine(ctx: "GlobalTypeContext", instance: Any) -> bool:
    """Whether the launch parameters being computed are for a machine that
    does not exist yet: never launched, or a pending/follow replacement."""
    from .launch_params import will_replace
    recorded = ctx.meta_state.launch_params().get(instance.get_name()) or {}
    return not recorded.get("launched") or will_replace(ctx, instance)


def alias_for(ctx: "GlobalTypeContext", instance: Any, canonical: str) -> str | None:
    """The alias this instance's launch parameters carry: the recorded one
    for a machine that stands, a fresh draw for a new machine of a durable
    instance when THIS run can launch it, nothing otherwise."""
    name = instance.get_name()
    ms = ctx.meta_state
    recorded = ms.launch_params().get(name) or {}
    if not _new_machine(ctx, instance):
        return str(recorded["alias"]) if recorded.get("alias") else None
    if getattr(instance, "ephemeral", False):
        return None
    path = pool_path(ctx.working_path)
    if not path.is_file():
        return None
    key = (str(ctx.run_id), name)
    if key in _DRAWN:
        return _DRAWN[key]
    if str(recorded.get("run") or "") == str(ctx.run_id) and recorded.get("alias"):
        return str(recorded["alias"])              # drawn earlier in this run, already recorded
    from .utils import apply_enabled
    can_launch = (not ctx.dry_run) and apply_enabled("instances", str(instance.type_), [str(instance.runtime)])
    if not can_launch:
        would = peek(path)
        if would:
            log.info(f"Instance {name}: would take alias {would!r} from the pool for {canonical} "
                     f"({'dry run' if ctx.dry_run else 'this run cannot launch it'}; nothing drawn)")
        else:
            log.warning(f"Instance {name}: the alias pool is EMPTY; a launch proceeds without an alias")
        return None
    drawn = draw(path, taken_by=f"instance {name} as {canonical}", run_id=str(ctx.run_id))
    if drawn is None:
        log.warning(f"Instance {name}: the alias pool is EMPTY; launching {canonical} without an alias "
                    f"(append names to {path.name} to refill it)")
        return None
    _DRAWN[key] = drawn
    log.info(f"Instance {name}: took alias {drawn!r} from the pool for {canonical} (spent; the line is "
             f"commented out in {path.name})")
    return drawn
