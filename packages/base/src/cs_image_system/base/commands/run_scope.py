# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Run scoping safe by construction (stage 12).

On 2026-09-09 an ad-hoc ``run … --apply-runtime gcloud-east1`` without
``--only-runtime`` baked two AMIs on AWS (ledger 68): ``--apply-runtime``
scopes the terraform applies, while the bake surface is the convergent
rule filtered only by ``--only`` / ``--only-runtime``. Two rules close it:

* the CLI implies ``--only-runtime <rt>`` from ``--apply-runtime <rt>``
  unless the operator selected images explicitly (``bake_plan`` says
  ``skip: outside the apply scope``);
* when the run's APPLY SCOPE is a proper subset of the runtimes (a
  list-valued ``apply_*`` flag or ``--apply-runtime``) and the bake plan
  would still bake outside it, a ``--no-dry-run`` run refuses before any
  bake unless the operator allowed it (``--allow-unscoped-bakes``) or
  selected the images explicitly; a dry run warns. Bakes are additive and
  never gated by apply flags (decision 2026-09-02): this is a scope check,
  not a bake flag -- a run with no apply scope at all bakes wherever the
  tree says.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

APPLY_FLAGS = ("apply_storage", "apply_instances")
ALLOW_FLAG = "--allow-unscoped-bakes"


def _runtime_of_root(ctx: Any, name: str) -> str | None:
    """The runtime of a storage/instance root named in an apply flag list."""
    for builders in (getattr(ctx, "storage_builders", None) or {}, getattr(ctx, "instance_builders", None) or {}):
        for key, b in builders.items():
            bname = str(b.get_name()) if hasattr(b, "get_name") else str(key)
            if bname == name:
                get_rt = getattr(getattr(b, "model", None), "get_runtime_provider", None)
                return str(get_rt()) if callable(get_rt) and get_rt() else None
    return None


def apply_scope_runtimes(ctx: Any) -> set[str] | None:
    """The runtimes this run may apply on, or ``None`` when the run has no
    scope (a bool-valued flag enables every root; no flag and no
    ``--apply-runtime`` means a pure generation/bake run)."""
    scoped: set[str] = set()
    restricted = False
    if getattr(ctx, "apply_runtime", None):
        scoped.add(str(ctx.apply_runtime))
        restricted = True
    config = getattr(ctx, "config", {}) or {}
    for flag in APPLY_FLAGS:
        value = config.get(flag)
        if isinstance(value, bool):
            if value:
                return None                                   # the whole lifecycle: no scope
            continue
        if isinstance(value, str):
            value = [value]
        if isinstance(value, (list, tuple, set)):
            for entry in value:
                name = str(entry).strip()
                if not name:
                    continue
                restricted = True
                if name in (getattr(ctx, "runtime_builders", None) or {}):
                    scoped.add(name)
                else:
                    rt = _runtime_of_root(ctx, name)
                    if rt:
                        scoped.add(rt)
    return scoped if restricted else None


def unscoped_bakes(ctx: Any, plan: dict[str, str]) -> list[str]:
    """``<series>@<runtime>`` keys the plan would BAKE on a runtime outside
    the apply scope (empty when the run has no scope)."""
    scope = apply_scope_runtimes(ctx)
    if scope is None:
        return []
    out = []
    for key, decision in sorted(plan.items()):
        if not decision.startswith("bake:"):
            continue
        rt = key.rsplit("@", 1)[1] if "@" in key else ""
        if rt and rt not in scope:
            out.append(key)
    return out


def check_bake_scope(ctx: Any, plan: dict[str, str]) -> str | None:
    """Apply the rule to a run's bake plan: ``None`` when the run may
    proceed, else the refusal message. Warns (never refuses) under dry
    run, an explicit selection or the allow flag."""
    outside = unscoped_bakes(ctx, plan)
    if not outside:
        return None
    scope = sorted(apply_scope_runtimes(ctx) or [])
    message = (f"bake(s) outside the apply scope {scope}: {', '.join(outside)} -- "
               f"pass {ALLOW_FLAG}, or select images with --only / --only-runtime")
    if getattr(ctx, "dry_run", True):
        log.warning(f"run scope (dry run, not refused): {message}")
        return None
    if getattr(ctx, "allow_unscoped_bakes", False) or getattr(ctx, "explicit_bake_selection", False):
        log.warning(f"run scope (allowed by the operator): {message}")
        return None
    return message
