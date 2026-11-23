# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A run's POSIX ids: every builder's claims and pools gathered from the
run's context, resolved by ``posix_ids`` with the tree's recorded ids, and
the answer kept for the run (``ctx.plugin_state``) so that validation, the
recording step and the builders (through ``IdentityService.resolved_id``)
read one resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .posix_ids import Claim, Pool, Resolution, resolve_posix_ids

if TYPE_CHECKING:
    from cs_image_system.base.run_context import RunContext

#: where a run keeps its resolution (``ctx.plugin_state``)
POSIX_RESOLUTION_KEY = "cs-image-system/posix-ids"


def posix_claims(ctx: RunContext) -> list[Claim]:
    """Every id claim of every group and user builder."""
    claims: list[Claim] = []
    for gb in ctx.group_builders.values():
        claims += gb.posix_id_claims()
    for ub in ctx.user_builders.values():
        claims += ub.posix_id_claims()
    return claims


def posix_pools(ctx: RunContext, claims: list[Claim]) -> list[Pool]:
    """Every builder's pool (``id_pool()``), external when the builder's
    claims are, or when the records say the pool was read."""
    read = {str(k) for k, v in (ctx.meta_state.recorded_ids().get("pools") or {}).items()
            if isinstance(v, dict) and v.get("how") == "read"}
    external = {c.identity for c in claims if c.external and c.identity}
    pools: list[Pool] = []
    for b in [*ctx.group_builders.values(), *ctx.user_builders.values()]:
        bounds = b.id_pool()
        if bounds is not None:
            name = b.get_name()
            pools.append(Pool(name, int(bounds[0]), int(bounds[1]), external=name in external or name in read))
    return pools


def resolve_run_ids(ctx: RunContext) -> tuple[Resolution, list[Pool]] | None:
    """Resolve the run's ids afresh and keep the answer for the run (None
    when no builder claims any)."""
    box = ctx.plugin_state(POSIX_RESOLUTION_KEY, dict)
    claims = posix_claims(ctx)
    if not claims:
        box["r"] = None
        return None
    pools = posix_pools(ctx, claims)
    box["r"] = (resolve_posix_ids(claims, recorded=ctx.meta_state.recorded_ids(), pools=pools), pools)
    return box["r"]


def run_ids(ctx: RunContext) -> tuple[Resolution, list[Pool]] | None:
    """The run's resolution, resolved on the first ask."""
    box = ctx.plugin_state(POSIX_RESOLUTION_KEY, dict)
    return box["r"] if "r" in box else resolve_run_ids(ctx)


def resolved_id(ctx: RunContext, kind: str, name: str) -> int | None:
    """The id the run resolved for ``kind`` ``name``, or None."""
    resolved = run_ids(ctx)
    if resolved is None:
        return None
    return next((i for (k, n), i in resolved[0].ids.items() if k == kind and n == name), None)
