# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Launch parameterization (DESIGN N26; §3F2, §3M).

The image carries all tooling and policy (baked). Launch parameters carry
only instance-specific bindings -- which storages to mount (and where), the
enrollment trigger, hostname-class values -- generated from validated
configuration, recorded in meta-state, and IMMUTABLE after launch: changing
them means instance replacement, an intentional operation.

This module computes the structural launch parameters for an instance and
the user-data template the instance root feeds through ``templatefile``;
runtime values (gids, filesystem ids, the enrollment token) enter only by
terraform reference at apply time, never as literals here.

The device and mount lines are the storage's. The core knows no storage
kind: each mount's record keys beyond the universal ones, its block of the
script and of the playbook, and the template variables it reads come from
the storage builder's ``launch_*`` hooks (the base's defaults in
``basic/builder_base_storage.py``); this module assembles them in
declaration order and adds what every instance shares -- the hostname, the
gid, the enrollment, the declared userdata and the completion marker.
"""
from __future__ import annotations


import hashlib
import logging
from typing import TYPE_CHECKING, Any

from .basic.builder_base_storage import MOUNT_MARK, StorageBuilderBase, mount_mark_line  # noqa: F401 - the mark is read here by name
from .capabilities import group_builder_of, storage_type_of
from .launch_enrollment import enrollment_kind_for
from . import generations
from cs_image_system.contract.lifecycles import Lifecycle
from .lineage import instance_follow_target
from cs_image_system.contract.runtime import LAUNCH_DELIVERY_BOOT
from .utils import apply_enabled, roots_on_runtime

if TYPE_CHECKING:
    from .run_context import RunContext
    from .models.instance import Instance

log = logging.getLogger(__name__)

# The variable's name is the contract's vocabulary (`contract.launch_vocabulary`)
from cs_image_system.contract.launch_vocabulary import (  # noqa: F401, E402 - re-exported
    ENROLLMENT_TOKEN_VARIABLE, HOSTNAME_LABEL_MAX, hostname_problems)

# Keys that may legitimately differ between generations of an instance's
# launch params without meaning "replacement".
_VOLATILE = ("run", "user_data_sha256", "launched", "launched_run", "build")


def mount_script_lines(mount: dict[str, Any], group: str | None, ctx: "RunContext | None") -> list[str]:
    """One mount's block of the launch script: its storage builder's
    ``launch_script_lines`` (the record's ``builder`` names it in ``ctx``;
    ``None`` configures no builder). A mount whose builder is not configured
    renders the shared header alone, as an unknown kind always did."""
    builder = _mount_builder(mount, ctx)
    if builder is None:
        return StorageBuilderBase.mount_header_lines(mount)
    return list(builder.launch_script_lines(mount, group))


def mount_tasks(mount: dict[str, Any], group: str | None, ctx: "RunContext | None") -> list[dict[str, Any]]:
    """One mount's ansible tasks: its storage builder's ``launch_tasks``;
    the directory task alone for a builder that is not configured."""
    builder = _mount_builder(mount, ctx)
    if builder is None:
        return [StorageBuilderBase.mount_directory_task(mount)]
    return list(builder.launch_tasks(mount, group))


def _mount_builder(mount: dict[str, Any], ctx: "RunContext | None") -> Any:
    if ctx is None:
        return None                     # no context: no storage builder is configured
    return ctx.storage_builders.get(str(mount.get("builder") or ""))


def mounted_points(params: dict[str, Any], ctx: "RunContext | None") -> list[str]:
    """The mount points the startup script mounts: every mount whose storage
    block carries the mount mark (an object store reached through its cloud
    CLI renders a comment and no mark)."""
    group = params.get("group")
    return [str(m["mount_point"]) for m in params.get("mounts", [])
            if mount_mark_line(str(m["mount_point"])) in mount_script_lines(m, group, ctx)]


def launch_variables(ctx: "RunContext") -> tuple[str, ...]:
    """The names a launch template (and the playbook's extra-vars) takes by
    reference: ``group_gid``, then every storage builder's own in
    declaration order (each once), then the enrollment token."""
    names: list[str] = ["group_gid"]
    for builder in ctx.storage_builders.values():
        for name in getattr(builder, "launch_variables", tuple)():
            if name not in names:
                names.append(str(name))
    names.append(ENROLLMENT_TOKEN_VARIABLE)
    return tuple(names)


def will_replace(ctx: "RunContext", instance: Any) -> bool:
    """Whether THIS run replaces the instance's machine: an explicit upgrade
    left a pending replacement, or a follow policy has a newer head to move
    to. The same two exemptions validate_immutability honours -- so a name
    that changes here is exactly a name immutability lets change."""
    name = instance.get_name()
    return name in ctx.meta_state.pending_replacements() or instance_follow_target(ctx, instance) is not None


def canonical_hostname(ctx: "RunContext", instance: Any) -> str:
    """The name the machine is given at boot and enrolls in OPA under
    (stage 55 step 4, operator decision 2026-09-21): the declared name plus
    its generation, zero-padded to three digits -- ``coops-model-003``.

    Two rules, in this order:

    * **A machine that stands keeps the name it booted with.** When the
      instance is launched and this run does not replace it, the answer is
      the RECORDED hostname, whatever it is -- which also grandfathers a
      machine launched before the suffix existed (``coops-model``, adopted
      as generation 1) until its first sanctioned replacement. The name
      changes only inside a replacement; nothing renames a running machine.
    * **A new machine takes its kind's NEXT generation.** Never launched,
      decommissioned, or being replaced this run: the durable count (or the
      ephemeral count, for an ephemeral instance -- each kind keeps its own
      number) plus one. ``mark_launched`` opens exactly that generation
      after the apply, so the name on the machine and the number in the
      ledger are the same fact decided once, here.

    The pad is a minimum width: generation 1000 renders ``-1000``. Change
    the seam HERE and nowhere else."""
    name = str(instance.get_name())
    ms = ctx.meta_state
    recorded = ms.launch_params().get(name) or {}
    if recorded.get("launched") and recorded.get("hostname") and not will_replace(ctx, instance):
        return str(recorded["hostname"])
    kind = generations.kind_of({"ephemeral": bool(getattr(instance, "ephemeral", False))})
    return f"{name}-{ms.instance_generation(name, kind) + 1:03d}"


def _storage_by_name(ctx: "RunContext"):
    return {s.get_name(): s for s in ctx.storages}


def effective_machine_type(instance: "Instance", rtb: Any) -> str:
    """The type the instance launches on: its own ``machine_type``, else the
    runtime's default -- the same rule as both instance builders apply."""
    own = str(getattr(instance, "machine_type", "") or "").strip()
    if own:
        return own
    get = getattr(rtb, "get_default_machine_type", None)
    return str(get() or "").strip() if callable(get) else ""


def resize_of(ctx: "RunContext", instance: "Instance") -> tuple[str, str] | None:
    """``(from, to)`` when a LAUNCHED instance's declaration names a different
    machine type than its record -- the in-place change hygiene VIII item 2
    allows. None when the instance is unlaunched, the type is unchanged, or
    the record predates the key (then the key is adopted, not resized)."""
    old = ctx.meta_state.launch_params().get(instance.get_name()) or {}
    if not old.get("launched") or not old.get("machine_type"):
        return None
    rtb = ctx.runtime_builders.get(instance.runtime) if instance.runtime else None
    new = effective_machine_type(instance, rtb)
    if new and new != str(old["machine_type"]):
        return str(old["machine_type"]), new
    return None


def compute_launch_params(ctx: "RunContext", instance: "Instance") -> dict[str, Any]:
    image = ctx.images_map.get(str(instance.image)) if instance.image else None
    group = getattr(image, "group", None) if image is not None else None
    storages = _storage_by_name(ctx)
    mounts: list[dict[str, Any]] = []
    seen: dict[str, int] = {}      # mounts so far per capability type: a block store's device index
    for mapping in instance.storage_mappings():
        storage = storages.get(mapping.get_name())
        if storage is None:
            continue
        stype = storage_type_of(ctx, storage.get_name())
        mount: dict[str, Any] = {
            "storage": storage.get_name(),
            "type": stype,
            "builder": storage.type_,
            "mount_point": mapping.get_mount_point(),
            "group": group,
            "share_mode": storage.share_mode,
            "public_read": bool(storage.public_read),
        }
        builder = ctx.storage_builders.get(storage.type_)
        if builder is not None:
            # the storage's own keys (a device name, a platform-mounted flag):
            # its hook, with how many mounts of its type came before it
            mount.update(builder.launch_mount(storage, mapping, seen.get(str(stype), 0)))
        seen[str(stype)] = seen.get(str(stype), 0) + 1
        mounts.append(mount)
    gb = group_builder_of(ctx, group) if group else None
    group_obj = None
    if gb is not None:
        group_obj = next((g for g in gb.get_groups_for_builder() if g.get_name() == group), None)
    enrollment = gb.launch_parameters(group_obj) if (gb is not None and group_obj is not None) else {}
    rtb = ctx.runtime_builders.get(instance.runtime) if instance.runtime else None
    session = rtb.session_mechanism() if rtb is not None else None
    delivery = str(rtb.launch_delivery()) if rtb is not None and hasattr(rtb, "launch_delivery") else LAUNCH_DELIVERY_BOOT
    hostname = canonical_hostname(ctx, instance)
    from .alias_pool import alias_for   # lazy: alias_pool imports this module
    alias = alias_for(ctx, instance, hostname)     # stage 59: a pool name, spent once, for a new machine
    machine_type = effective_machine_type(instance, rtb)
    return {
        "image": str(instance.image),
        "build": ctx.meta_state.instance_pin(instance.get_name()) or "unbound",
        # hygiene VIII item 2: the type the machine booted on -- the ONE launch
        # parameter that may change in place (a resize: the provider stops the
        # machine, changes its type and starts it; the same machine, recorded
        # on the same generation). Present only when resolvable, so a record
        # from before the key existed is adopted, not refused.
        **({"machine_type": machine_type} if machine_type else {}),
        "group": group,
        "identity_type": gb.identity_type() if gb is not None else None,
        "mounts": mounts,
        "enrollment": enrollment,
        "session": session,
        # stage 103 branch 2: how the script reaches the machine -- present
        # only when it is not the platform's first boot, so every cloud
        # record stays as it was
        **({"launch_delivery": delivery} if delivery != LAUNCH_DELIVERY_BOOT else {}),
        "hostname": hostname,
        **({"alias": alias} if alias else {}),
        "ephemeral": bool(getattr(instance, "ephemeral", False)),   # stage 10.1
        # the instance's own startup lines (ledger 68): part of what the machine
        # booted with, hence immutable like every other launch parameter
        # (present only when declared, so records from before it stay comparable)
        **({"userdata": ud} if (ud := str(getattr(instance, "userdata", "") or "").strip()) else {}),
    }


def user_data_template(params: dict[str, Any], ctx: "RunContext | None" = None) -> str:
    """The cloud-init shell script as a terraform ``templatefile`` template.

    Template variables (supplied by the instance root, all by reference):
    ``group_gid`` (number), one map per storage kind that reads values at
    boot (storage name -> the values its root binds; the storage builder's
    ``launch_variables`` names them), the enrollment token under
    ``ENROLLMENT_TOKEN_VARIABLE`` (sensitive;
    empty when no enrollment; the name is historical -- it carries whatever
    credential the group's identity plugin enrolls a machine with, and that
    plugin's registered enrollment kind renders the lines that use it).
    Shell parameter expansion is written ``$${...}`` so terraform passes it
    through. Each mount's block is its storage builder's (``ctx`` is the
    configured context unless given).
    """
    lines = [
        "#!/usr/bin/env bash",
        f"# cs-image-system launch parameters for instance {params['hostname']} (N26).",
        "# Generated from validated configuration; immutable after launch --",
        "# changing them means replacing the instance.",
        "set -euo pipefail",
    ]
    if params.get("launch_delivery"):
        # stage 103 branch 2: delivered through the session after the apply,
        # to a machine the platform already named (a container's hostname is
        # set when it is created, and it has no hostnamectl to run)
        lines.append(f"# delivered by the runtime's session ({params['launch_delivery']}); the platform "
                     f"named the machine {params['hostname']}")
    else:
        lines.append(f"hostnamectl set-hostname '{params['hostname']}' || true")
    group = params.get("group")
    if group:
        lines.append(f"# owning group: {group} (gid by reference)")
        lines.append('GID="${group_gid}"')
    for m in params.get("mounts", []):
        # the mount's whole block -- header, device, mount, mark, the
        # group's subtree -- is the storage's; the core adds nothing to it
        lines += mount_script_lines(m, group, ctx)
    # stage 75 step 2: the identity plugin that issued the enrollment renders
    # its steps (the agent's address and the token, for the kind it registered); the
    # core names no agent, and a kind nothing renders is refused
    kind = enrollment_kind_for(params)
    if kind is not None:
        lines += kind.script_lines(params)
    # Completion marker (stage 11.1): the last act of the script under `set -e`,
    # so its presence means every launch parameter above was applied. The
    # first cloud's verification reads it over the session mechanism; the
    # second's guest agent writes its own line.
    if params.get("userdata"):
        # the declaration's own lines run last, under the same `set -e`: a
        # failing line is a failed startup, which a verification reports
        lines += ["# instance userdata (declared on the instance)", *str(params["userdata"]).splitlines()]
    lines += ["mkdir -p /var/lib/csis", "date -u +%FT%TZ > /var/lib/csis/launch-applied"]
    return "\n".join(lines) + "\n"


def record_launch_params(ctx: "RunContext", lifecycle: Lifecycle) -> None:
    """After the instance-image lifecycle generated: record every instance's
    launch parameters (structural facts only), preserving the launched
    marker of instances already launched."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    ms = ctx.meta_state
    existing = ms.launch_params()
    for instance in ctx.instances:
        if detachments(ctx, instance):
            # the mount stays recorded until the detach APPLIED (truthful
            # recorders): record_detachments re-records it after the apply
            continue
        params = compute_launch_params(ctx, instance)
        params["user_data_sha256"] = hashlib.sha256(user_data_template(params, ctx).encode()).hexdigest()
        params["run"] = ctx.run_id
        old = existing.get(instance.get_name()) or {}
        params["launched"] = bool(old.get("launched", False))
        if old.get("launched_run"):
            params["launched_run"] = old["launched_run"]
        resize = resize_of(ctx, instance)
        if resize:
            # truthful recorders: the record keeps the type the machine RUNS
            # on until the resize applied (record_resizes writes the new one)
            params["machine_type"] = resize[0]
        ms.record_launch_params(instance.get_name(), params)
    # Decommissioned instances are forgotten AFTER the real apply that
    # destroys them (see forget_decommissioned); doing it here, at
    # generation, let a dry run erase the record first -- after which the
    # gate had nothing to whitelist and the VM stayed orphaned (finding 53,
    # the finding-21 truthful-recorders shape).


def forget_decommissioned(ctx: "RunContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner completed WITH applies enabled, the
    recorded instances no longer declared were destroyed through the gate's
    decommission whitelist: forget their launch parameters and pins (N19)."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    # same guard as mark_launched (finding 21): an after-apply hook runs only
    # when the apply step ran, and the flag decides whether it applied for real
    if not apply_enabled(ctx, "instances"):
        return
    ms = ctx.meta_state
    declared = {i.get_name() for i in ctx.instances}
    params, pins = ms.launch_params(), ms.instance_pins()
    for name in sorted((set(params) | set(pins)) - declared):
        # Per-root scoping (stage 7): the destroy was planned in the root of
        # the runtime the build was baked on (the decommission whitelist's
        # rule); forget the record only when THAT root applied.
        build_id = pins.get(name) or (params.get(name) or {}).get("build")
        rec = ms.build(str(build_id)) if build_id else None
        rt = str(rec.get("runtime")) if rec and rec.get("runtime") else None
        if rt is not None and not apply_enabled(ctx, "instances", rt, roots_on_runtime(ctx.instance_builders, rt)):
            continue
        log.info(f"Instance {name} is no longer declared and its destroy applied: "
                 "dropping its launch parameters and pin (decommission)")
        # stage 60: the machine is gone -- its generation closes into the
        # history with the launch parameters it booted with, BEFORE the
        # launch record is forgotten
        generations.on_gone(ctx, name, why=generations.WHY_DECOMMISSION)
        # stage 55: the OPA server registration is the THIRD record of the
        # same launch, and the one that used to outlive the machine. Same
        # hook, same guard -- and a failure to retire is reported, not
        # swallowed, because the whole point is that nothing silently leaves
        # a dead machine answering to a live name.
        _retire_registration(ctx, name, params.get(name) or {})
        ms.remove_launch_params(name)
        ms.remove_instance_pin(name, ctx.run_id)


def record_detachments(ctx: "RunContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner completed for real: a launched
    instance whose detach applied (its root was allowed to apply) is
    re-recorded without the mount (stage 10.14)."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    if not apply_enabled(ctx, "instances"):
        return
    ms = ctx.meta_state
    for instance in ctx.instances:
        removed = detachments(ctx, instance)
        if not removed or not apply_enabled(ctx, "instances", str(instance.type_), [str(instance.runtime)]):
            continue
        old = ms.launch_params().get(instance.get_name()) or {}
        params = compute_launch_params(ctx, instance)
        params["user_data_sha256"] = hashlib.sha256(user_data_template(params, ctx).encode()).hexdigest()
        params["run"] = ctx.run_id
        params["launched"] = bool(old.get("launched", False))
        if old.get("launched_run"):
            params["launched_run"] = old["launched_run"]
        ms.record_launch_params(instance.get_name(), params)
        log.info(f"Instance {instance.get_name()}: detached {[m.get('storage') for m in removed]}; "
                 "launch parameters re-recorded without the mount(s)")


def record_resizes(ctx: "RunContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner completed for real: a launched
    instance whose declaration named a different machine type was resized
    IN PLACE by the apply -- the provider stopped it, changed its type and
    started it; the same machine (hygiene VIII item 2). Its record and its
    open generation's snapshot take the new type, and the ledger's history
    gains a ``resized`` event. Registered before record_detachments, which
    recomputes the record and would otherwise write the new type unnoticed."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    if not apply_enabled(ctx, "instances"):
        return
    ms = ctx.meta_state
    for instance in ctx.instances:
        resize = resize_of(ctx, instance)
        if not resize or not apply_enabled(ctx, "instances", str(instance.type_), [str(instance.runtime)]):
            continue
        name = instance.get_name()
        rec = dict(ms.launch_params().get(name) or {})
        rec["machine_type"] = resize[1]
        ms.record_launch_params(name, rec)
        generations.on_resized(ctx, name, resize[0], resize[1])


def forget_ephemerals(ctx: "RunContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner completed for real, every declared
    EPHEMERAL instance whose root applied was verified and torn down by
    its own sequence (stage 10.1): its launch parameters and pin are
    forgotten; the verification record in verifications.yaml remains."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    if not apply_enabled(ctx, "instances"):
        return
    from .commands.verify_instance import (   # lazy: commands.verify_instance imports this module
        ON_FAILURE_TEARDOWN, VerificationFailed, failure_policy, last_verification)
    ms = ctx.meta_state
    failed: list[dict[str, Any]] = []
    for inst in ctx.instances:
        if not getattr(inst, "ephemeral", False):
            continue
        if not apply_enabled(ctx, "instances", str(inst.type_), [str(inst.runtime)]):
            continue
        name = inst.get_name()
        log.info(f"Ephemeral instance {name}: verified and torn down this run; forgetting its launch record")
        # stage 60: it EXISTED -- it booted and enrolled -- so its generation
        # closes into the history rather than vanishing with the record
        generations.on_gone(ctx, name, why=generations.WHY_EPHEMERAL)
        ms.remove_launch_params(name)
        ms.remove_instance_pin(name, ctx.run_id, op="ephemeral")
        # stage 11.3 `teardown` (ledger 68): the instance was torn down
        # regardless, its records are now consistent with reality, and a
        # failed verdict still fails the run -- from here, not from the script
        policy, _ = failure_policy(ctx, inst)
        last = last_verification(ctx, name)
        if policy == ON_FAILURE_TEARDOWN and last is not None and not last.get("ok"):
            failed.append(last)
    if failed:
        for rec in failed[1:]:
            log.error(str(VerificationFailed(rec)))
        raise VerificationFailed(failed[0])


def mark_launched(ctx: "RunContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner completed WITH applies enabled,
    every declared instance is launched: its parameters are now immutable."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    if not apply_enabled(ctx, "instances"):
        return
    ms = ctx.meta_state
    declared = {i.get_name(): i for i in ctx.instances}
    pending = ms.pending_replacements()
    for name, params in ms.launch_params().items():
        inst = declared.get(name)
        # Per-root scoping (stage 7): a declared instance is launched only
        # when ITS root (builder name / runtime) was allowed to apply.
        if inst is not None and not apply_enabled(ctx, "instances", str(inst.type_), [str(inst.runtime)]):
            continue
        if inst is not None:
            params = dict(params)
            params["launched"] = True
            params["launched_run"] = ctx.run_id
            ms.record_launch_params(name, params)
            # stage 60: a machine now exists (or a sanctioned replacement
            # just made a new one) -- open its generation, inferred; the
            # observation pass confirms it against the provider's id
            previous = ms.current_generation(name)
            generations.on_launched(ctx, name, params, replaced=name in pending)
            # stage 55 meets stage 60: the machine this launch REPLACED
            # answered to a different name (`<name>-NNN`, stage 55 step 4).
            # Its registration is the third record of that machine, and the
            # one that would outlive it -- and it would claim the bare alias
            # stage 58 gives the new machine. Retire it now that the apply
            # has destroyed the machine behind it. Found in review before the
            # first live replacement (2026-09-22).
            booted_as = str(((previous or {}).get("launch_params") or {}).get("hostname") or "")
            if booted_as and params.get("hostname") and booted_as != params.get("hostname"):
                _retire_registration(ctx, name, {"group": params.get("group"), "hostname": booted_as})
        ms.clear_pending_replacement(name)


def _comparable(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k not in _VOLATILE}


def detachments(ctx: "RunContext", instance: Any) -> list[dict[str, Any]]:
    """Mounts recorded for a LAUNCHED instance that its declaration no
    longer lists (stage 10.14): each is a detach the instance root plans,
    after the unmount the runtime performs."""
    old = ctx.meta_state.launch_params().get(instance.get_name())
    if not old or not old.get("launched"):
        return []
    declared = {m.get_name() for m in instance.storage_mappings()}
    return [m for m in (old.get("mounts") or []) if m.get("storage") not in declared]


def _without_mounts(params: dict[str, Any], names: set[str]) -> dict[str, Any]:
    out = _comparable(params)
    out["mounts"] = [m for m in (params.get("mounts") or []) if m.get("storage") not in names]
    return out


def validate_immutability(ctx: "RunContext", requested: list[Lifecycle]) -> list[str]:
    """N26: launched instances may not change their launch parameters except
    through replacement (an explicit upgrade, or decommission + recreate)."""
    errors: list[str] = []
    ms = ctx.meta_state
    recorded = ms.launch_params()
    pending = ms.pending_replacements()
    for instance in ctx.instances:
        name = instance.get_name()
        old = recorded.get(name)
        if not old or not old.get("launched"):
            continue
        if name in pending:
            continue
        if instance_follow_target(ctx, instance):
            continue   # a policy-driven replacement (stage 9.5) is a replacement
        new = compute_launch_params(ctx, instance)
        old_cmp, new_cmp = _comparable(old), _comparable(new)
        # hygiene VIII item 2: the machine type may change in place (a resize
        # -- the same machine, recorded by record_resizes after the apply),
        # and a record from before the key existed adopts it; either way it
        # is not what immutability compares
        old_cmp.pop("machine_type", None)
        new_cmp.pop("machine_type", None)
        # stage 10.14: a mount REMOVAL is the other in-place change allowed (a
        # detach, unmounted first); everything else stays immutable
        removed = {str(m.get("storage")) for m in detachments(ctx, instance)}
        if removed and _without_mounts(old_cmp, removed) == new_cmp:
            continue
        if old_cmp != new_cmp:
            changed = sorted(k for k in set(old_cmp) | set(new_cmp) if old_cmp.get(k) != new_cmp.get(k))
            errors.append(
                f"instance '{name}' was launched (run {old.get('launched_run')}) and its launch "
                f"parameters changed ({', '.join(changed)}); launch parameters are immutable after "
                "launch -- replace the instance (upgrade instance, or decommission and redeclare) (N26)")
    return errors


def _retire_registration(ctx: "RunContext", name: str, recorded: dict[str, Any]) -> None:
    """Retire every OPA registration of a decommissioned instance's canonical
    hostname (stage 55 step 1). The recorded launch parameters say which
    group it enrolled under and which hostname it took; the group's builder
    owns the registry. A provider without one makes no claim."""
    group = str(recorded.get("group") or "")
    hostname = str(recorded.get("hostname") or name)
    gb = group_builder_of(ctx, group) if group else None
    if gb is None or not gb.can_query_servers():
        return
    try:
        gone = gb.retire_servers_named(group, hostname)
    except Exception as e:  # noqa: BLE001 - reported loudly, never fatal to the forget
        log.error(f"Instance {name}: its OPA registration as {hostname!r} was NOT retired ({e}); "
                  f"a stale server will answer to that name until it is deregistered by hand")
        return
    log.info(f"Instance {name}: retired {len(gone)} OPA registration(s) of {hostname!r}"
             if gone else f"Instance {name}: no OPA registration of {hostname!r} to retire")


def validate_claimed_hostnames(ctx: "RunContext", requested: list[Lifecycle]) -> list[str]:
    """A canonical hostname is claimed once (stage 55 step 2). Before a run
    that can LAUNCH, every declared instance's hostname is checked against
    the group's server registry: an unlaunched instance whose name is already
    registered would enroll a second server under it, and a launched one with
    more than one registration already has -- both are refusals naming the
    records, because that ambiguity is what made a login by name unusable.

    Two deliberate limits. It runs only when the instance-image lifecycle is
    requested AND applies are enabled AND the run is not a dry run, so a dry
    run or an unrelated command never makes a network call (stage 63 item
    10: until 2026-09-24 the dry-run flag was not read, so a dry run with
    the apply flag on asked the registry and could refuse on silence). And an unreachable registry is a refusal
    saying the claim COULD NOT BE CHECKED -- never "the name is free" (stage
    57's rule: silence is not an answer), because an unreachable OPA is
    exactly when a duplicate would otherwise slip through."""
    if Lifecycle.INSTANCE_IMAGE not in requested:
        return []
    if not apply_enabled(ctx, "instances") or getattr(ctx, "dry_run", False):
        return []
    errors: list[str] = []
    recorded = ctx.meta_state.launch_params()
    registries: dict[str, list[dict[str, Any]] | None] = {}
    for instance in ctx.instances:
        if not apply_enabled(ctx, "instances", str(instance.type_), [str(instance.runtime)]):
            continue
        image = ctx.images_map.get(str(instance.image))
        group = str(getattr(image, "group", None) or "") if image is not None else ""
        gb = group_builder_of(ctx, group) if group else None
        if gb is None or not gb.can_query_servers():
            continue
        if group not in registries:
            registries[group] = gb.registered_servers(group)
        servers = registries[group]
        name, hostname = instance.get_name(), canonical_hostname(ctx, instance)
        if servers is None:
            errors.append(
                f"instance '{name}': could not check whether canonical hostname {hostname!r} is "
                f"already claimed (group {group!r}'s server registry did not answer); refusing to "
                "launch on silence -- an unreachable registry is not a free name")
            continue
        claims = [s for s in servers if s.get("hostname") == hostname]
        launched = bool((recorded.get(name) or {}).get("launched"))
        if not launched and claims:
            errors.append(
                f"instance '{name}': canonical hostname {hostname!r} is already registered to "
                f"{len(claims)} server(s) in group {group!r} ({', '.join(f'{c['id']} at {c['address'] or '?'}' for c in claims)}); "
                "launching would enroll a second machine under the same name. Retire the stale "
                "registration first (a decommission does this; or deregister it by hand)")
        elif launched and len(claims) > 1:
            errors.append(
                f"instance '{name}': canonical hostname {hostname!r} is registered to {len(claims)} servers "
                f"in group {group!r} ({', '.join(f'{c['id']} at {c['address'] or '?'}' for c in claims)}), "
                "and only one of them is this machine; a login by name cannot choose. Deregister the others")
    return errors


def register(runner) -> None:
    runner.register_after_generate(record_launch_params)
    runner.register_after_apply(mark_launched)
    runner.register_after_apply(forget_decommissioned)
    runner.register_after_apply(forget_ephemerals)
    runner.register_after_apply(record_resizes)        # before record_detachments (it recomputes the record)
    runner.register_after_apply(record_detachments)
    runner.register_validator(validate_immutability)
    runner.register_validator(validate_claimed_hostnames)
