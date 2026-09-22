# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 56 step 3: after the identity lifecycle applied for real, every
managed group whose builder names the team's workload connection and role
gets its CI login policy reconciled -- a copy of the group's user policy
with the workload role as the only principal, created, updated or left
alone -- and the identity read-model records what happened.

The write is gated exactly like the terraform apply beside it
(``apply_identity``); a dry run never reaches an after-apply hook, and the
state query reports an absent or diverged policy as drift until an apply
creates it. A group released from management (``unmanaged``) is left as it
stands, like its user policy: the identity lifecycle never destroys.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .basic.builder_base_group import GroupBuilderBase
from .lifecycles import Lifecycle

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)


def reconcile_workload_access(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    if lifecycle != Lifecycle.IDENTITY:
        return
    from .utils import apply_enabled
    if not apply_enabled("identity"):
        return
    model = ctx.meta_state.identity_read_model()
    groups: dict[str, Any] = model.setdefault("groups", {})
    touched = False
    for _, gb in sorted(ctx.group_builders.items()):
        if not isinstance(gb, GroupBuilderBase) or not gb.can_manage_workload_access():
            continue
        for g in sorted(gb.get_groups_for_builder(), key=lambda g: g.get_name()):
            if getattr(g, "unmanaged", False):
                continue
            name = g.get_name()
            try:
                result = gb.ensure_workload_access(name)
            except Exception as e:  # noqa: BLE001 - loud, never fatal to the apply that already happened
                log.error(f"Group {name}: its CI login policy was NOT reconciled ({e}); the CI login "
                          "proof for this group fails until it is")
                result = {"action": "failed", "error": str(e)[:200]}
            else:
                log.info(f"Group {name}: CI login policy {result.get('policy')} {result.get('action')}")
            rec = groups.setdefault(name, {})
            if not isinstance(rec, dict):
                rec = groups[name] = {}
            workload = rec.setdefault("workload", {})
            workload.update(result)
            workload["run"] = ctx.run_id
            touched = True
    if touched:
        ctx.meta_state.write_identity_read_model(model)


def register(runner) -> None:
    runner.register_after_apply(reconcile_workload_access)
