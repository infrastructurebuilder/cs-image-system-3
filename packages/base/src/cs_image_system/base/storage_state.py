# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The storage state machine (DESIGN §3E, N19/N21/N22).

Storages are one of the two "actually problematic" parts of the system; they
get a REAL state machine: the YAML declares the *requested* state, meta-state
holds the *authoritative* current state and the full transition history, and
this module owns legality and ordering. Terraform is one executor of a
transition; the storage plugin's transition actions are another.

States: ``active`` (default on create) <-> ``archived`` -> ``destroyed``.
Guards: leaving ``active`` requires the storage to be unattached.

Operator semantics (stage 10.11-12, 2026-09-08): a storage EXISTS exactly as
long as its declaration. Deleting the entry is its demise -- the next
storage run plans the whitelisted destroy of the *undeclared* storage and
records the tombstone. A tombstone keeps history, not the name: a name that
is declared again after its demise is a NEW storage, recorded as the next
*generation* (no data continuity is implied). ``state: destroyed`` in the
YAML remains as a staging/testing device.
"""
from __future__ import annotations

from .models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import TYPE_CHECKING

from .models.storage import (
    STORAGE_STATE_ACTIVE,
    STORAGE_STATE_ARCHIVED,
    STORAGE_STATE_DESTROYED,
    Storage,
)

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

# (current, requested) pairs that are legal transitions. ``None`` = never
# applied (a new storage). Same-state pairs are no-ops, handled separately.
LEGAL_TRANSITIONS: set[tuple[str | None, str]] = {
    (None, STORAGE_STATE_ACTIVE),
    (STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED),
    (STORAGE_STATE_ARCHIVED, STORAGE_STATE_ACTIVE),
    (STORAGE_STATE_ACTIVE, STORAGE_STATE_DESTROYED),
    (STORAGE_STATE_ARCHIVED, STORAGE_STATE_DESTROYED),
    # regeneration (stage 10.12): a declared storage whose record is a
    # tombstone is a new generation of the name
    (STORAGE_STATE_DESTROYED, STORAGE_STATE_ACTIVE),
}

# Transitions that require the storage to have NO attachments (N19/N21).
UNATTACHED_ONLY: set[str] = {STORAGE_STATE_ARCHIVED, STORAGE_STATE_DESTROYED}


@dataclass(frozen=True, config=CSIS_MODEL_CONFIG)
class Transition:
    storage: str
    from_state: str | None
    to_state: str
    undeclared: bool = False          # stage 10.11: the entry left the YAML -> demise
    builder: str | None = None        # the root that owns an undeclared storage

    @property
    def action(self) -> str | None:
        if self.undeclared:
            return "undeclared"
        if self.from_state == STORAGE_STATE_DESTROYED and self.to_state == STORAGE_STATE_ACTIVE:
            return "regenerate"
        return None


def attachments(ctx: "GlobalTypeContext") -> dict[str, list[str]]:
    """``{storage name: [instance names]}`` from the instance declarations."""
    out: dict[str, list[str]] = {}
    for inst in ctx.instances:
        for mapping in inst.storage_mappings():
            out.setdefault(mapping.get_name(), []).append(inst.get_name())
    return out


def current_state(ctx: "GlobalTypeContext", storage: Storage) -> str | None:
    return ctx.meta_state.storage_state(storage.get_name())


def pending_transitions(ctx: "GlobalTypeContext") -> list[Transition]:
    """Requested-vs-current differences for every declared storage."""
    out: list[Transition] = []
    for storage in ctx.storages:
        cur = current_state(ctx, storage)
        if cur != storage.state:
            out.append(Transition(storage.get_name(), cur, storage.state))
    return out


def undeclared_transitions(ctx: "GlobalTypeContext") -> list[Transition]:
    """Recorded, not destroyed, no longer declared: each is a destroy the
    next storage run plans (stage 10.11). The owning root comes from the
    record's facts (or the last read-model); a record that names no root
    cannot be planned and is reported instead."""
    declared = {s.get_name() for s in ctx.storages}
    out: list[Transition] = []
    for name, entry in sorted(ctx.meta_state.storage_states().items()):
        state = entry.get("state")
        if name in declared or state == STORAGE_STATE_DESTROYED:
            continue
        builder = (entry.get("facts") or {}).get("builder") or \
            ((ctx.meta_state.storage_read_model().get("storages") or {}).get(name) or {}).get("builder")
        out.append(Transition(name, state, STORAGE_STATE_DESTROYED, undeclared=True, builder=builder))
    return out


def all_transitions(ctx: "GlobalTypeContext") -> list[Transition]:
    return pending_transitions(ctx) + undeclared_transitions(ctx)


def storage_facts(ctx: "GlobalTypeContext", storage: Storage) -> dict:
    """Structural facts recorded with a storage's state so an UNDECLARED
    storage can still be planned (its root) and wiped (its bucket)."""
    builder = ctx.storage_builders.get(str(storage.type_))
    facts = {"builder": str(storage.type_)}
    cap = getattr(builder, "capability_type", None)
    if callable(cap):
        facts["type"] = str(cap())
    for key in ("bucket_name",):
        v = getattr(storage, key, None) or getattr(getattr(builder, "model", None), key, None)
        if v:
            facts[key] = str(v)
    archive = getattr(builder, "archive_name", None)
    if callable(archive) and getattr(builder, "supports_archive", lambda: False)():
        facts["archive"] = str(archive(storage))
    return facts


def validate_transitions(ctx: "GlobalTypeContext") -> list[str]:
    """Every illegal request is a hard generation-time failure."""
    errors: list[str] = []
    attached = attachments(ctx)
    declared = {s.get_name(): s for s in ctx.storages}
    for storage in ctx.storages:
        name = storage.get_name()
        cur = current_state(ctx, storage)
        req = storage.state
        if cur == req:
            if req in UNATTACHED_ONLY and attached.get(name):
                errors.append(f"storage '{name}' is {req} but instances attach it: {attached[name]}")
            continue
        if (cur, req) not in LEGAL_TRANSITIONS:
            if cur is None:
                errors.append(f"storage '{name}' has never been applied; a new storage must start 'active', "
                              f"not {req!r}")
            else:
                errors.append(f"storage '{name}': transition {cur} -> {req} is not legal")
            continue
        if req in UNATTACHED_ONLY and attached.get(name):
            errors.append(f"storage '{name}' cannot move {cur or 'new'} -> {req} while attached by "
                          f"{attached[name]} (detach in one run, transition in the next; N21)")
        if req == STORAGE_STATE_ARCHIVED:
            builder = ctx.storage_builders.get(str(storage.type_))
            if not getattr(builder, "supports_archive", lambda: False)():
                errors.append(f"storage '{name}' ({storage.type_}) requests archived, which its builder does not "
                              "realize (snapshot + restore); only builders that support archiving may (stage 11.6)")
    # stage 10.11 replaced N22: a managed storage that left the YAML is a
    # planned destroy, not an error -- unless nothing records which root
    # owns it, in which case the destroy cannot be planned.
    for t in undeclared_transitions(ctx):
        if not t.builder:
            errors.append(f"storage '{t.storage}' is recorded {t.from_state} but no longer declared, and its "
                          "record names no storage builder: re-declare it (or record it with `state import`) "
                          "so the destroy can be planned")
    # Attaching non-active storages is illegal.
    for name, instances in attached.items():
        st = declared.get(name)
        if st is None:
            errors.append(f"instances {instances} attach unknown storage '{name}'")
        elif not st.is_attachable:
            errors.append(f"instances {instances} attach storage '{name}' which is {st.state}")
    return errors


def record_applied_transitions(ctx: "GlobalTypeContext", transitions: list[Transition]) -> None:
    """After the storage runner completed, the requested states become the
    authoritative states (with the action and the structural facts)."""
    by_name = {s.get_name(): s for s in ctx.storages}
    for t in transitions:
        storage = by_name.get(t.storage)
        facts = storage_facts(ctx, storage) if storage is not None else None
        ctx.meta_state.record_storage_transition(t.storage, t.from_state, t.to_state, ctx.run_id,
                                                 action=t.action, facts=facts)
