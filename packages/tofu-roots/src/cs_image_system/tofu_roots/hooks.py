# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The terraform roots' run hooks, registered under the
``cs_image_system.plugins.hooks`` entry-point group.

The core knows lifecycles, builders and meta-state; it knows nothing of
terraform state backends. What a terraform root needs from a run -- its
state location checked before anything is generated, recorded after its
lifecycle generates, and shown beside the others as the state-isolation
evidence -- comes from here, through the runner's hook seams:

* ``state_location_problems`` (a validator): every root's location
  resolved from the declarations, collisions and unsafe moves refused;
* ``record_state_locations`` (after generate): each generated root's
  resolved location written to ``meta-state/state-locations.yaml``, the
  memory a later run's move guard compares against;
* ``lifecycle_state_bindings`` (state bindings): ``{lifecycle:
  {workspace: state file}}``, which the runner-script headers and the run
  summary carry.

A tree with no terraform roots installs the same hooks and they find
nothing to say.
"""
from __future__ import annotations

import logging

from cs_image_system.contract.constants import NONE
from cs_image_system.contract.context import RunContextProtocol
from cs_image_system.contract.hooks import HookSet
from cs_image_system.contract.lifecycles import LifecycleLike
from cs_image_system.hashicorp_utils.collector import StateLocation, terraform_collector

log = logging.getLogger(__name__)


def state_location_problems(ctx: RunContextProtocol) -> list[Exception]:
    """Every terraform root's state location resolved from the declarations,
    then two refusals. Collisions: two roots that would write one state
    object -- the same bucket and normalised prefix under two backend names,
    two names that collapse under super_safe_name, a doubled slash against a
    single one. Moves: a root whose resolved location differs from the one
    meta-state recorded while the records show live resources in it -- the
    new location is empty, so the next plan would create everything again
    and strand the old state. A root with nothing deployed moves freely. The
    escape is an operation, ``--migrate-state <workspace>``, never an
    override; giving resources up is a records correction, not a
    rebinding."""
    col = terraform_collector(ctx)
    if not col.backends_enabled():
        return []
    errors: list[Exception] = []
    resolved: dict[str, StateLocation] = {}
    for workspace, (own, runtime_value) in ctx.services.workspaces.terraform_workspaces().items():
        # `none` reads as unset in the chain below (it is in OOPS_DEFAULTS so
        # nothing can be named after it), which would put this root's state
        # on the default backend -- the opposite of what `none` says. There
        # is no "no state backend", so the word is refused here.
        if NONE in (own, runtime_value):
            errors.append(Exception(
                f"workspace '{workspace}' names state backend 'none', which names nothing -- there is "
                f"no 'no state backend': declare one of type `local` for state on disk, or leave the "
                f"field out for the default backend"))
            continue
        name = col.effective_backend_name(own, runtime_value)
        try:
            reg = col.resolve_backend(name)
        except Exception as ex:                       # more than one default: the existing guard
            errors.append(ex)
            continue
        if reg is None:
            errors.append(Exception(f"workspace '{workspace}' names state backend '{name}', which is not declared"))
            continue
        try:
            resolved[workspace] = reg.state_location(workspace)
        except ValueError as ex:                      # a `.` or `..` segment in the prefix
            errors.append(Exception(f"workspace '{workspace}': {ex}"))
    for message in col.state_collisions(resolved):
        errors.append(Exception(f"state location collision: {message}"))
    recorded = ctx.meta_state.state_locations()
    migrating = set(getattr(ctx, "migrate_state", None) or [])
    for workspace, location in sorted(resolved.items()):
        old = recorded.get(workspace)
        if not old:
            continue
        old_text = ctx.meta_state.location_key(old)
        if old_text == str(location) or workspace in migrating:
            continue
        deployed = ctx.services.workspaces.deployed_in_workspace(workspace)
        if not deployed:
            log.info(f"workspace '{workspace}' moves its state from {old_text} to {location}: "
                     "nothing is deployed from it, so nothing is at risk")
            continue
        errors.append(Exception(
            f"workspace '{workspace}' would move its state from {old_text} to {location} while "
            f"{', '.join(deployed)} stand(s) in it: the new location is empty, so the next plan would "
            f"create everything again and strand the old state. To MOVE the state: "
            f"`run --no-dry-run ... --migrate-state {workspace}` (backs the old state up, copies it, "
            f"accepts only a clean plan at the new location and records the move). If those resources "
            f"are gone or being given up, correct the records instead (the state query's import and "
            f"forget paths); never rebind past this refusal."))
    return errors


def validate_state_locations(ctx: RunContextProtocol, requested: list[LifecycleLike]) -> list[str]:
    """The validator hook: ``state_location_problems`` as the error strings
    the runner collects. Every requested set is checked whole: a root's
    location is a property of the tree, not of the lifecycles asked for."""
    return [str(e) for e in state_location_problems(ctx)]


def record_state_locations(ctx: RunContextProtocol, lifecycle: LifecycleLike) -> None:
    """Every workspace this lifecycle generated records its resolved state
    location in meta-state: the record, not the emission, is the memory a
    later run's move guard compares against (``generated/`` can be pruned
    or regenerated). A workspace migrating this run keeps its old record
    until the migration's ``finish`` step moves it, which is what ``begin``
    reads."""
    col = terraform_collector(ctx)
    if not col.backends_enabled():
        return
    migrating = set(getattr(ctx, "migrate_state", None) or [])
    mine = {b.get_name() for b in ctx.all_sorted_builders
            if b.get_classification() in ctx.services.lifecycles.builder_vcts_of(lifecycle)}
    records = {}
    for workspace in col.bound_workspaces():
        if workspace in migrating or workspace not in mine:
            continue
        record = col.backend_record(workspace)
        if record is not None:
            records[workspace] = record
    if records:
        ctx.meta_state.record_state_locations(records, ctx.run_id)


def lifecycle_state_bindings(ctx: RunContextProtocol) -> dict[str, dict[str, str]]:
    """``{lifecycle: {workspace: state file}}`` -- the state-isolation
    evidence. A workspace is a builder; a builder belongs to exactly one
    lifecycle, so 'apply identity only' provably touches only identity
    state files. Every lifecycle is named, bound to nothing when it has no
    terraform root."""
    col = terraform_collector(ctx)
    lifecycles = ctx.services.lifecycles
    out: dict[str, dict[str, str]] = {lc.value: {} for lc in lifecycles.all_lifecycles()}
    for lifecycle in lifecycles.all_lifecycles():
        for builder in ctx.all_sorted_builders:
            if builder.get_classification() not in lifecycles.builder_vcts_of(lifecycle):
                continue
            reg = col.workspace_backend(builder.get_name())
            if reg is not None:
                out[lifecycle.value][builder.get_name()] = str(reg.state_location(builder.get_name()))
    return out


def initialize() -> HookSet:
    """The entry point: the three hooks, installed once per process (the
    runner dedupes a hook by identity, so a forced reload installs nothing
    twice)."""
    return HookSet(validators=[validate_state_locations],
                   after_generate=[record_state_locations],
                   state_bindings=[lifecycle_state_bindings])
