# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What the records say stands: the terraform workspaces' state
bindings read from the models, what a workspace's state holds, and the
launched instances a login proof can reach. Moved here from the command
modules (``commands.validate``, ``commands.login_proof``, which re-export
them) so the loader can hand them to a plugin as services without
importing the commands package, whose import runs the whole CLI wiring.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cs_image_system.contract.constants import STATE_BACKEND_FIELD

if TYPE_CHECKING:
    from .run_context import RunContext


def terraform_workspaces(ctx: RunContext) -> dict[str, tuple[str | None, str | None]]:
    """workspace -> (its builder's own ``state_configuration``, its runtime's)
    for every builder that owns a terraform root, read from the models alone
    so the tofu-roots state-location validator resolves the bindings without
    generating anything. The runtime rung belongs to the roots that have a runtime -- the
    storage and instance roots; an identity root resolves its own value or
    the default, exactly as the builders bind at generation."""
    out: dict[str, tuple[str | None, str | None]] = {}
    runtime_rooted = set(ctx.storage_builders) | set(ctx.instance_builders)
    for builder in ctx.all_sorted_builders:
        name = builder.get_name()
        if name in ctx.runtime_builders:
            continue
        model = getattr(builder, "model", None)
        if model is None or not hasattr(model, STATE_BACKEND_FIELD):
            continue
        runtime_value: str | None = None
        if name in runtime_rooted:
            try:
                runtime_name = model.get_runtime_provider()
            except ValueError:
                runtime_name = None
            rtb = ctx.runtime_builders.get(runtime_name) if runtime_name else None
            runtime_value = getattr(getattr(rtb, "model", None), STATE_BACKEND_FIELD, None) if rtb else None
        out[name] = (getattr(model, STATE_BACKEND_FIELD), runtime_value)
    return out


def deployed_in_workspace(ctx: RunContext, workspace: str) -> list[str]:
    """What the records say stands in a workspace's state:
    storages whose recorded state is not destroyed, the groups and users the
    identity read-model attributes to the root, and instances pinned to a
    build (a pin is a standing instance; a decommission removes it)."""
    ms = ctx.meta_state
    out: list[str] = []
    read_model = ms.storage_read_model().get("storages") or {}
    for name, rec in ms.storage_states().items():
        state = rec.get("state")
        if state in (None, "destroyed"):
            continue
        builder = (rec.get("facts") or {}).get("builder") or (read_model.get(name) or {}).get("builder")
        if builder == workspace:
            out.append(f"storage {name} ({state})")
    # the identity read-model is written at generation, so it is evidence only
    # once a recorded run has EXECUTED the identity lifecycle
    identity_applied = any((run.get("apply") or {}).get("identity") == "executed"
                           for run in (ms.read("runs.yaml").get("runs") or []))
    identity = ms.identity_read_model() if identity_applied else {}
    for kind in ("groups", "users"):
        entries = identity.get(kind) or {}
        for name, rec in (entries.items() if isinstance(entries, dict) else []):
            if isinstance(rec, dict) and rec.get("builder") == workspace:
                out.append(f"{kind[:-1]} {name}")
    builders_of = {inst.get_name(): getattr(inst, "type_", None) for inst in ctx.instances}
    for inst, build in ms.instance_pins().items():
        if builders_of.get(inst) == workspace:
            out.append(f"instance {inst} (build {build})")
    return out


def standing_instances(ctx: RunContext, *, runtime: str | None = None,
                       names: list[str] | None = None) -> list[Any]:
    """The declared instances a login proof can target: launched (the
    launch record says so), not ephemeral, on ``runtime`` when given, among
    ``names`` when given. A name that is not declared is an error."""
    declared = {i.get_name(): i for i in ctx.instances}
    for n in names or []:
        if n not in declared:
            raise ValueError(f"login proof: instance {n!r} is not declared")
    launched = ctx.meta_state.launch_params()
    out = []
    for name, inst in sorted(declared.items()):
        if names and name not in names:
            continue
        if runtime and str(getattr(inst, "runtime", "") or "") != runtime:
            continue
        if getattr(inst, "ephemeral", False):
            continue
        if not (launched.get(name) or {}).get("launched"):
            continue
        out.append(inst)
    return out
