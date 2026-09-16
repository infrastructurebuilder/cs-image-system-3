# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Read-model writers (DESIGN §3D/§3E, N6/N7/N10).

After a lifecycle generates, its read-model is written to meta-state as a
committed file carrying STRUCTURAL facts only -- never runtime values such
as gids, which travel exclusively by reference through terraform remote
state (N7). The storage read-model is the instance inventory the
instance-image lifecycle consumes at attach time (N10).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .basic.builder_base_group import GroupBuilderBase
from .basic.builder_base_storage import StorageBuilderBase
from .lifecycles import Lifecycle
from .storage_state import all_transitions, attachments, record_applied_transitions

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)


def identity_read_model(ctx: "GlobalTypeContext") -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for builder in ctx.group_builders.values():
        if not isinstance(builder, GroupBuilderBase):
            continue
        for g in builder.get_groups_for_builder():
            groups[g.get_name()] = {
                "builder": builder.get_name(),
                "identity_type": builder.identity_type(),
                "gid_policy": builder.gid_policy(),
                "managed": not getattr(g, "unmanaged", False),
                "is_root": bool(g.is_root),
                "members": sorted(g.members or set()),
                "admins": sorted(g.admins or set()),
            }
    users = sorted(u.get_name() for u in ctx.users)
    user_builders = {b.get_name(): b.get_type() for b in ctx.user_builders.values()}
    return {
        "run": ctx.run_id,
        "groups": groups,
        "users": users,
        "user_builders": user_builders,
        "note": "structural facts only; gids flow by terraform remote-state reference (N7)",
    }


def storage_read_model(ctx: "GlobalTypeContext") -> dict[str, Any]:
    attached = attachments(ctx)
    storages: dict[str, Any] = {}
    for s in ctx.storages:
        builder = ctx.storage_builders.get(s.type_)
        rec: dict[str, Any] = {
            "builder": s.type_,
            "requested_state": s.state,
            "current_state": ctx.meta_state.storage_state(s.get_name()),
            "generation": ctx.meta_state.storage_generation(s.get_name()),
            "allowed_groups": list(s.groups),
            "public_read": bool(s.public_read),
            "share_mode": s.share_mode,
            "lifecycle": dict(getattr(s, "lifecycle", None) or {}),
            "attachments": sorted(attached.get(s.get_name(), [])),
        }
        if isinstance(builder, StorageBuilderBase):
            rec["type"] = builder.capability_type()
            rec["plugin"] = builder.get_type()
            rec["attachment_cardinality"] = builder.attachment_cardinality()
            rec["posix"] = builder.is_posix()
        storages[s.get_name()] = rec
    return {"run": ctx.run_id, "storages": storages}


def write_read_model(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    if lifecycle == Lifecycle.IDENTITY:
        p = ctx.meta_state.write_identity_read_model(identity_read_model(ctx))
        log.info(f"Wrote identity read-model to {p}")
    elif lifecycle == Lifecycle.STORAGE:
        p = ctx.meta_state.write_storage_read_model(storage_read_model(ctx))
        log.info(f"Wrote storage read-model to {p}")


def record_storage_transitions(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    """After the storage runner completed for real, requested states become
    authoritative and the read-model reflects them."""
    if lifecycle != Lifecycle.STORAGE:
        return
    from .utils import apply_enabled
    if not apply_enabled("storage"):
        # A reality-claiming record requires a real apply (finding 21: this
        # hook once recorded None -> active on a run whose flag was off, so
        # zero applies executed and meta-state lied until the state query's
        # HARD drift caught it). Same guard as mark_launched.
        return
    # Per-root scoping (stage 7): a transition became real only if the
    # storage's own root (its builder name / that builder's runtime) applied.
    by_name = {s.get_name(): s for s in ctx.storages}

    def _root_applied(t) -> bool:
        storage = by_name.get(t.storage)
        root = str(storage.type_) if storage is not None else t.builder
        builder = ctx.storage_builders.get(str(root)) if root else None
        get_rt = getattr(getattr(builder, "model", None), "get_runtime_provider", None)
        rt = str(get_rt()) if callable(get_rt) else None
        return apply_enabled("storage", root, [rt] if rt else ())

    # declared transitions AND the demise of undeclared storages (stage 10.11)
    transitions = [t for t in all_transitions(ctx) if _root_applied(t)]
    record_applied_transitions(ctx, transitions)
    if transitions:
        log.info(f"Recorded storage transitions: {[(t.storage, t.from_state, t.to_state) for t in transitions]}")
    ctx.meta_state.write_storage_read_model(storage_read_model(ctx))


def register(runner) -> None:
    runner.register_after_generate(write_read_model)
    runner.register_after_apply(record_storage_transitions)
