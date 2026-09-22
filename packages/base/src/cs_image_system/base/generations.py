# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An instance has generations, and each one is a machine (stage 60).

The system already controls WHETHER a machine may be replaced -- the
immutability check refuses a changed launch parameter and names the three
sanctioned exits -- but until this stage it kept no identity for the machine
that resulted. ``launch-params.yaml`` holds one record per name, overwritten
on every relaunch; no provider id appeared anywhere in meta-state. Three
``coops-model`` registrations piled up in OPA because nothing knew a second
machine had happened.

A generation is one machine. It opens when a machine comes into being and
closes when THAT machine is destroyed. Storage already has the concept
(``storage_generation``); this is the same word for the same thing.

**The machine decides, not our bookkeeping.** Control flow -- ``launched``
flipping to true, a pending replacement clearing -- is the tempting signal
and the wrong one: it infers a new machine from our own records, and the
failure this stage exists to end is records that did not notice a new
machine. So a generation is DEFINED by observation: the provider's instance
id (stage 58's ``query_instance_identity``) differs from the one recorded.
A machine replaced out of band -- a taint, a console terminate and
re-apply -- is caught. Control flow still opens a generation (a run that
launched clearly made a machine), but marked ``inferred``; the observation
pass upgrades it to ``observed`` when it sees the id, or closes it and opens
the next when it sees a DIFFERENT id.

**What is not a new generation.** A reboot. A stop and start (stage 57: a
stopped machine is the same machine). A mount detach. An image pin that
moved but was not applied. And -- the trap -- an identity query that
returned nothing: "cannot read the id" is never "the id changed". A stopped
instance may well fail the query; nothing here acts on silence.

**Nothing is fabricated.** A machine that stood before this ledger existed
becomes generation 1 marked ``adopted`` -- the first generation of the
RECORD, not of the name. Its predecessors are visible only in
``pins.yaml.upgrades`` and stay there.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .lifecycles import Lifecycle

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)

DURABLE, EPHEMERAL = "durable", "ephemeral"
OBSERVED, INFERRED, ADOPTED = "observed", "inferred", "adopted"

#: Why a generation closed.
WHY_DECOMMISSION = "decommission"          # the declaration went away and the destroy applied
WHY_EPHEMERAL = "ephemeral"                # verified and torn down within its run
WHY_REPLACED = "replaced"                  # a sanctioned replacement applied (upgrade / follow)
WHY_REPLACED_OUT_OF_BAND = "replaced-out-of-band"   # a different machine bears the name; we did not do it


def kind_of(params: dict[str, Any]) -> str:
    """Which counter a generation belongs to: its own ``ephemeral`` flag,
    per instance NAME -- so ``gce-test`` churning never advances
    ``coops-model``'s number, and a name whose declaration flipped between
    ephemeral and durable keeps two honest counts."""
    return EPHEMERAL if params.get("ephemeral") else DURABLE


# -------------------------------------------------- control-flow signals
def on_launched(ctx: "GlobalTypeContext", name: str, params: dict[str, Any], *, replaced: bool) -> None:
    """Called by ``mark_launched`` for a declared instance whose root applied.
    Opens a generation when none is open -- inferred: the run launched, so
    a machine exists. When a sanctioned replacement just applied over an
    open generation, closes it (``replaced``) and opens the next, inferred;
    the observation pass then confirms it against the provider's id."""
    ms = ctx.meta_state
    cur = ms.current_generation(name)
    if cur is not None and not replaced:
        # A follow moves its pin with pending=False ("already happened"), so
        # the pending marker alone misses it. The generation's own snapshot
        # does not: it holds the hostname the standing machine booted with,
        # and the canonical name changes ONLY inside a replacement -- so a
        # launch record bearing a different hostname is a new machine.
        booted_as = (cur.get("launch_params") or {}).get("hostname")
        replaced = bool(booted_as) and bool(params.get("hostname")) and booted_as != params.get("hostname")
    if cur is not None and replaced:
        ms.close_generation(name, run_id=ctx.run_id, why=WHY_REPLACED)
        log.info(f"Instance {name}: generation {cur.get('kind')} {cur.get('number')} closed -- replaced")
        cur = None
    if cur is None:
        n = ms.open_generation(name, kind=kind_of(params), run_id=ctx.run_id, how=INFERRED, launch_params=params)
        log.info(f"Instance {name}: {kind_of(params)} generation {n} opened (inferred from the launch; "
                 "the provider's id confirms it after apply)")


def on_gone(ctx: "GlobalTypeContext", name: str, *, why: str) -> dict[str, Any] | None:
    """Called where a launch record is forgotten (decommission, ephemeral
    teardown): the open generation closes into the history with why, and
    keeps the launch parameters it booted with."""
    closed = ctx.meta_state.close_generation(name, run_id=ctx.run_id, why=why)
    if closed:
        log.info(f"Instance {name}: generation {closed.get('kind')} {closed.get('number')} closed -- {why}"
                 + (f" (was {closed['instance_id']})" if closed.get("instance_id") else ""))
    return closed


# ------------------------------------------------------- the observation
def reconcile_generations(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner applied for real: ask the provider
    which machine bears each launched name, and let THAT decide.

    * no open generation, machine launched: adopt it (generation 1 of the
      record, ``adopted``);
    * open generation without an id: record the id (``inferred`` becomes
      ``observed``);
    * open generation whose id differs from the provider's: the machine we
      knew is gone and another stands -- close it ``replaced-out-of-band``
      and open the next, ``observed``;
    * the provider could not answer: nothing. Silence is not a change."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    from .utils import apply_enabled
    if not apply_enabled("instances"):
        return
    ms = ctx.meta_state
    recorded = ms.launch_params()
    for instance in ctx.instances:
        name = instance.get_name()
        if not apply_enabled("instances", str(instance.type_), [str(instance.runtime)]):
            continue
        params = recorded.get(name) or {}
        if not params.get("launched"):
            continue
        rtb = ctx.runtime_builders.get(str(instance.runtime)) if instance.runtime else None
        if rtb is None or not rtb.can_query_instance_identity():
            continue
        identity = rtb.query_instance_identity(name)
        seen_now = str((identity or {}).get("instance_id") or "")
        if not seen_now:
            log.debug(f"Instance {name}: provider identity unavailable; its generation stands as recorded")
            continue
        cur = ms.current_generation(name)
        if cur is None:
            n = ms.open_generation(name, kind=kind_of(params), run_id=ctx.run_id, how=ADOPTED,
                                   launch_params=params, identity=identity)
            log.info(f"Instance {name}: {kind_of(params)} generation {n} ADOPTED as {seen_now} -- the first "
                     "generation of the record, not of the name")
            continue
        known = str(cur.get("instance_id") or "")
        if not known:
            if ms.note_generation_identity(name, identity or {}):
                log.info(f"Instance {name}: generation {cur.get('kind')} {cur.get('number')} is {seen_now} (observed)")
            continue
        if known == seen_now:
            continue
        ms.close_generation(name, run_id=ctx.run_id, why=WHY_REPLACED_OUT_OF_BAND)
        n = ms.open_generation(name, kind=kind_of(params), run_id=ctx.run_id, how=OBSERVED,
                               launch_params=params, identity=identity)
        log.warning(f"Instance {name}: the machine bearing this name is {seen_now}, not {known} -- "
                    f"generation {cur.get('kind')} {cur.get('number')} closed as replaced out of band, "
                    f"{kind_of(params)} generation {n} opened. Nothing in this system did that.")


def register(runner) -> None:
    runner.register_after_apply(reconcile_generations)
