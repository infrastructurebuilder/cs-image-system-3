# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Identity attributes: declare, validate, plan, probe -- and (not yet) apply
(EXPLORE "User and Group Management").

Users and groups may declare provider ``attributes:`` (OPA: ``unix_uid``,
``unix_user_name``, ``unix_gid``, ``unix_group_name``, ...). The terraform
providers cannot carry them, so they travel a separate, resource-shaped
path:

1. **validate** at generation: names and types per plugin, hard failures;
2. **plan**: ``generated/identity/attributes-plan.json`` -- the desired
   values, written after the identity lifecycle generates (only when
   something is declared, so a plain configuration changes nothing);
3. **probe** (read-only): the plugin's live attributes for every item in
   the plan, the resulting ``changes`` and the provider's own
   ``conflicts`` report;
4. **apply**: deliberately *disabled*. It prints exactly what it would
   change and refuses to write until DESIGN Q7 ("IaC-managed users may
   reappear") is confirmed by the stakeholder. Nothing here has ever
   written to Okta or OPA.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .basic.builder_base_group import GroupBuilderBase
from .basic.builder_base_user import UserBuilderBase
from .lifecycles import Lifecycle

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)

PLAN_FILENAME = "attributes-plan.json"


class AttributeApplyDisabled(RuntimeError):
    """Writing identity attributes is switched off (DESIGN Q7)."""


# ---------------------------------------------------------------- declare

def declared_attributes(ctx: "GlobalTypeContext") -> dict[str, dict[str, dict[str, Any]]]:
    """``{"groups": {name: {attr: value}}, "users": {...}}`` -- every declared
    attribute map, empty maps dropped."""
    groups: dict[str, dict[str, Any]] = {g.get_name(): _attrs_of(g) for g in ctx.groups if _attrs_of(g)}
    users: dict[str, dict[str, Any]] = {u.get_name(): _attrs_of(u) for u in ctx.users if _attrs_of(u)}
    return {"groups": groups, "users": users}


def _attrs_of(item: Any) -> dict[str, Any]:
    attrs = getattr(item, "attributes", None)
    return {str(k): v for k, v in attrs.items()} if isinstance(attrs, dict) else {}


def _group_builder_of(ctx: "GlobalTypeContext", group: Any) -> GroupBuilderBase | None:
    for b in ctx.group_builders.values():
        if isinstance(b, GroupBuilderBase) and any(g is group for g in b.local_groups):
            return b
    return None


def _user_builder_of(ctx: "GlobalTypeContext", user: Any) -> UserBuilderBase | None:
    for b in ctx.user_builders.values():
        if isinstance(b, UserBuilderBase) and any(u is user for u in b.local_users):
            return b
    return None


# --------------------------------------------------------------- validate

def validate_identity_items(ctx: "GlobalTypeContext", requested: list[Lifecycle]) -> list[str]:
    """Per-item management mode and attribute declarations are checked by
    the owning plugin; any complaint aborts the run."""
    errors: list[str] = []
    for u in ctx.users:
        b = _user_builder_of(ctx, u)
        if b is None:
            continue
        errors += b.validate_user(u)
        if _attrs_of(u):
            errors += b.validate_attributes(u, _attrs_of(u))
    for g in ctx.groups:
        b = _group_builder_of(ctx, g)
        if b is None or not _attrs_of(g):
            continue
        errors += b.validate_attributes(g, _attrs_of(g))
    return errors


# ------------------------------------------------------------------- plan

def plan_path(ctx: "GlobalTypeContext") -> Path:
    return ctx.lifecycle_generation_path(Lifecycle.IDENTITY) / PLAN_FILENAME


def attributes_plan(ctx: "GlobalTypeContext") -> dict[str, Any]:
    return {"run": ctx.run_id, "desired": declared_attributes(ctx)}


def write_attributes_plan(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    """after-generate hook: the plan exists iff something is declared."""
    if lifecycle != Lifecycle.IDENTITY:
        return
    plan = attributes_plan(ctx)
    p = plan_path(ctx)
    if not plan["desired"]["groups"] and not plan["desired"]["users"]:
        if p.exists():
            p.unlink()
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    log.info(f"Wrote identity attributes plan to {p}")


def read_attributes_plan(ctx: "GlobalTypeContext") -> dict[str, Any] | None:
    p = plan_path(ctx)
    if not p.is_file():
        return None
    data = json.loads(p.read_text())
    return data if isinstance(data, dict) else None


# ------------------------------------------------------------------ probe

def probe(ctx: "GlobalTypeContext", plan: dict[str, Any]) -> dict[str, Any]:
    """Read-only: current provider values for every planned item, the
    changes needed, and the provider's conflict report. Items whose plugin
    cannot answer are listed under ``unavailable``."""
    items_by_kind: dict[str, dict[str, Any]] = {
        "groups": {g.get_name(): g for g in ctx.groups},
        "users": {u.get_name(): u for u in ctx.users},
    }
    current: dict[str, dict[str, Any]] = {"groups": {}, "users": {}}
    changes: list[dict[str, Any]] = []
    unavailable: list[str] = []
    for kind in ("groups", "users"):
        for name, desired in sorted(plan.get("desired", {}).get(kind, {}).items()):
            item: Any = items_by_kind[kind].get(name)
            b: Any = None
            if item is not None:
                b = _group_builder_of(ctx, item) if kind == "groups" else _user_builder_of(ctx, item)
            if b is None:
                unavailable.append(f"{kind}/{name}: not in the configuration")
                continue
            try:
                live = b.query_attributes(item)
            except NotImplementedError:
                unavailable.append(f"{kind}/{name}: {b.get_type()} cannot query attributes")
                continue
            except Exception as e:
                unavailable.append(f"{kind}/{name}: {e}")
                continue
            if live is None:
                unavailable.append(f"{kind}/{name}: no provider record")
                continue
            current[kind][name] = live
            for attr, value in sorted(desired.items()):
                have = live.get(attr)
                if have != value:
                    changes.append({"kind": kind[:-1], "name": name, "attribute": attr,
                                    "from": have, "to": value})
    conflicts: list[dict[str, Any]] | None = None
    for b in ctx.group_builders.values():
        if not isinstance(b, GroupBuilderBase):
            continue
        try:
            c = b.attribute_conflicts()
        except NotImplementedError:
            continue
        except Exception as e:
            unavailable.append(f"conflicts/{b.get_name()}: {e}")
            continue
        if c is not None:
            conflicts = (conflicts or []) + list(c)
    return {**plan, "current": current, "changes": changes,
            "conflicts": conflicts, "unavailable": sorted(unavailable)}


# ------------------------------------------------------------------ apply

def apply(ctx: "GlobalTypeContext", probed: dict[str, Any], *, dry_run: bool) -> list[str]:
    """What an apply WOULD do, one line per attribute write. A real apply
    raises :class:`AttributeApplyDisabled` -- switched off by design until
    DESIGN Q7 is confirmed; there is no code path that writes."""
    lines = [f"{c['kind']} {c['name']}: {c['attribute']} {c['from']!r} -> {c['to']!r}"
             for c in probed.get("changes", [])]
    if probed.get("conflicts"):
        raise ValueError(f"identity attributes: the provider reports conflicts; refusing: {probed['conflicts']}")
    if not dry_run and lines:
        raise AttributeApplyDisabled(
            "writing identity attributes is disabled (DESIGN Q7 not confirmed); "
            f"{len(lines)} change(s) were NOT applied")
    return lines


def register(runner) -> None:
    runner.register_validator(validate_identity_items)
    runner.register_after_generate(write_attributes_plan)
