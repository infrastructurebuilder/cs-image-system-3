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
"""
from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from .capabilities import group_builder_of, storage_type_of
from .lifecycles import Lifecycle

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext
    from .models.instance import Instance

log = logging.getLogger(__name__)

# Device names handed to EBS attachments in declaration order.
EBS_DEVICES = ["/dev/xvdf", "/dev/xvdg", "/dev/xvdh", "/dev/xvdi", "/dev/xvdj", "/dev/xvdk"]
ENROLLMENT_TOKEN_VARIABLE = "sft_enrollment_token"

# Keys that may legitimately differ between generations of an instance's
# launch params without meaning "replacement".
_VOLATILE = ("run", "user_data_sha256", "launched", "launched_run", "build")


def _storage_by_name(ctx: "GlobalTypeContext"):
    return {s.get_name(): s for s in ctx.storages}


def _gce_device_name(value: str) -> str:
    """The GCE device name a storage is attached under -- the same rule as the
    gcloud plugin's ``gce_name`` (lowercase; anything outside ``[a-z0-9-]``
    becomes ``-``), kept here so the base package stays plugin-free; the
    GCE instance builder attaches with the identical name (finding 50)."""
    import re
    v = re.sub(r"[^a-z0-9-]+", "-", str(value).lower()).strip("-")
    return v or "disk"


def compute_launch_params(ctx: "GlobalTypeContext", instance: "Instance") -> dict[str, Any]:
    image = ctx.images_map.get(str(instance.image)) if instance.image else None
    group = getattr(image, "group", None) if image is not None else None
    storages = _storage_by_name(ctx)
    mounts: list[dict[str, Any]] = []
    ebs_index = 0
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
        if stype == "ebs":
            mount["device"] = EBS_DEVICES[ebs_index] if ebs_index < len(EBS_DEVICES) else f"/dev/xvd{chr(ord('l') + ebs_index - len(EBS_DEVICES))}"
            ebs_index += 1
        elif stype == "pd":
            # GCE names attached disks by device_name under /dev/disk/by-id
            # as "google-<device_name>"; the GCE instance builder attaches
            # with exactly this sanitized name (finding 50: the two once
            # disagreed -- "gce_data" attached, "google-gce-data" mounted --
            # and the startup script died at the missing device)
            mount["device"] = "/dev/disk/by-id/google-" + _gce_device_name(storage.get_name())
        mounts.append(mount)
    gb = group_builder_of(ctx, group) if group else None
    group_obj = None
    if gb is not None:
        group_obj = next((g for g in gb.get_groups_for_builder() if g.get_name() == group), None)
    enrollment = gb.launch_parameters(group_obj) if (gb is not None and group_obj is not None) else {}
    rtb = ctx.runtime_builders.get(instance.runtime) if instance.runtime else None
    session = rtb.session_mechanism() if rtb is not None else None
    return {
        "image": str(instance.image),
        "build": ctx.meta_state.instance_pin(instance.get_name()) or "unbound",
        "group": group,
        "identity_type": gb.identity_type() if gb is not None else None,
        "mounts": mounts,
        "enrollment": enrollment,
        "session": session,
        "hostname": instance.get_name(),
        "ephemeral": bool(getattr(instance, "ephemeral", False)),   # stage 10.1
        # the instance's own startup lines (ledger 68): part of what the machine
        # booted with, hence immutable like every other launch parameter
        # (present only when declared, so records from before it stay comparable)
        **({"userdata": ud} if (ud := str(getattr(instance, "userdata", "") or "").strip()) else {}),
    }


def user_data_template(params: dict[str, Any]) -> str:
    """The cloud-init shell script as a terraform ``templatefile`` template.

    Template variables (supplied by the instance root, all by reference):
    ``group_gid`` (number), ``efs`` (map storage -> {file_system_id,
    access_point_id}), ``filestore`` (map storage -> {ip_address,
    share_name}), ``sft_enrollment_token`` (sensitive; empty when no
    enrollment). Shell parameter expansion is written ``$${...}`` so
    terraform passes it through.
    """
    lines = [
        "#!/usr/bin/env bash",
        f"# cs-image-system launch parameters for instance {params['hostname']} (N26).",
        "# Generated from validated configuration; immutable after launch --",
        "# changing them means replacing the instance.",
        "set -euo pipefail",
        f"hostnamectl set-hostname '{params['hostname']}' || true",
    ]
    group = params.get("group")
    if group:
        lines.append(f"# owning group: {group} (gid by reference)")
        lines.append('GID="${group_gid}"')
    for m in params.get("mounts", []):
        mp = m["mount_point"]
        name = m["storage"]
        lines.append(f"# mount storage {name} ({m['type']}) at {mp}")
        lines.append(f"mkdir -p '{mp}'")
        if m["type"] in ("ebs", "pd"):
            dev = m["device"]
            lines.append(f"DEV='{dev}'")
            if m["type"] == "ebs":
                # On Nitro instances (t3+) EBS volumes surface as /dev/nvme*
                # and RHEL-family AMIs create no legacy symlinks (found live:
                # user-data died at mkfs and everything after never ran), so
                # fall back to the stable by-id name built from the volume id.
                lines += [
                    f"VOL=\"${{ebs[\"{name}\"].volume_id}}\"",
                    "BYID=\"/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_"
                    "$(printf '%s' \"$VOL\" | tr -d -)\"",
                ]
            else:
                lines.append('BYID="$DEV"')
            lines += [
                "# the attachment lands after boot: wait for either name",
                'for i in $(seq 1 60); do [ -e "$DEV" ] && break;'
                ' [ -e "$BYID" ] && DEV="$BYID" && break; sleep 2; done',
                'if ! blkid "$DEV" >/dev/null 2>&1; then mkfs -t xfs "$DEV"; fi',
                f"grep -q ' {mp} ' /etc/fstab || echo \"$DEV {mp} xfs defaults,nofail 0 2\" >> /etc/fstab",
                f"mount '{mp}' || mount \"$DEV\" '{mp}'",
            ]
        elif m["type"] == "efs":
            lines += [
                f"EFS_ID=\"${{efs[\"{name}\"].file_system_id}}\"",
                f"EFS_AP=\"${{efs[\"{name}\"].access_point_id}}\"",
                f"grep -q ' {mp} ' /etc/fstab || echo \"$EFS_ID:/ {mp} efs _netdev,tls,accesspoint=$EFS_AP,nofail 0 0\" >> /etc/fstab",
                f"mount '{mp}' || true",
            ]
        elif m["type"] == "filestore":
            lines += [
                f"FS_IP=\"${{filestore[\"{name}\"].ip_address}}\"",
                f"FS_SHARE=\"${{filestore[\"{name}\"].share_name}}\"",
                f"grep -q ' {mp} ' /etc/fstab || echo \"$FS_IP:/$FS_SHARE {mp} nfs defaults,_netdev,nofail 0 0\" >> /etc/fstab",
                f"mount '{mp}' || true",
            ]
        elif m["type"] in ("s3", "gcs"):
            lines.append(f"# {m['type']} storage {name}: object access via the cloud CLI; no mount")
            continue
        if group and m["type"] in ("ebs", "pd", "filestore"):
            # per-group private subtree (N13/N15) -- EFS access points create theirs
            lines += [
                f"mkdir -p '{mp}/{group}'",
                f"chgrp \"$GID\" '{mp}/{group}'",
                f"chmod {m['share_mode']} '{mp}/{group}'",
            ]
    enrollment = params.get("enrollment") or {}
    if enrollment.get("enrollment") == "sftd-token":
        lines += [
            "# advertise the reachable private address: the auto-discovered public",
            "# IP is unroutable when the VPC has no internet gateway (found live)",
            "PRIV_IP=$(hostname -I | awk '{print $1}')",
            "mkdir -p /etc/sft",
            "grep -q '^AccessAddress:' /etc/sft/sftd.yaml 2>/dev/null"
            " || printf 'AccessAddress: %s\\n' \"$PRIV_IP\" >> /etc/sft/sftd.yaml",
            "# identity enrollment trigger (token supplied at apply time, never recorded)",
            "%{ if sft_enrollment_token != \"\" }",
            "mkdir -p /var/lib/sftd",
            "printf '%s' '${sft_enrollment_token}' > /var/lib/sftd/enrollment.token",
            "chmod 0600 /var/lib/sftd/enrollment.token",
            "systemctl restart sftd || systemctl start sftd",
            "%{ endif }",
        ]
    # Completion marker (stage 11.1): the last act of the script under `set -e`,
    # so its presence means every launch parameter above was applied. The
    # AWS verification reads it over SSM; GCE has the guest agent's own line.
    if params.get("userdata"):
        # the declaration's own lines run last, under the same `set -e`: a
        # failing line is a failed startup, which a verification reports
        lines += ["# instance userdata (declared on the instance)", *str(params["userdata"]).splitlines()]
    lines += ["mkdir -p /var/lib/csis", "date -u +%FT%TZ > /var/lib/csis/launch-applied"]
    return "\n".join(lines) + "\n"


def record_launch_params(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
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
        params["user_data_sha256"] = hashlib.sha256(user_data_template(params).encode()).hexdigest()
        params["run"] = ctx.run_id
        old = existing.get(instance.get_name()) or {}
        params["launched"] = bool(old.get("launched", False))
        if old.get("launched_run"):
            params["launched_run"] = old["launched_run"]
        ms.record_launch_params(instance.get_name(), params)
    # Decommissioned instances are forgotten AFTER the real apply that
    # destroys them (see forget_decommissioned); doing it here, at
    # generation, let a dry run erase the record first -- after which the
    # gate had nothing to whitelist and the VM stayed orphaned (finding 53,
    # the finding-21 truthful-recorders shape).


def forget_decommissioned(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner completed WITH applies enabled, the
    recorded instances no longer declared were destroyed through the gate's
    decommission whitelist: forget their launch parameters and pins (N19)."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    from .utils import apply_enabled, roots_on_runtime
    # same guard as mark_launched (finding 21): an after-apply hook runs only
    # when the apply step ran, and the flag decides whether it applied for real
    if not apply_enabled("instances"):
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
        if rt is not None and not apply_enabled("instances", rt, roots_on_runtime(ctx.instance_builders, rt)):
            continue
        log.info(f"Instance {name} is no longer declared and its destroy applied: "
                 "dropping its launch parameters and pin (decommission)")
        ms.remove_launch_params(name)
        ms.remove_instance_pin(name, ctx.run_id)


def record_detachments(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner completed for real: a launched
    instance whose detach applied (its root was allowed to apply) is
    re-recorded without the mount (stage 10.14)."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    from .utils import apply_enabled
    if not apply_enabled("instances"):
        return
    ms = ctx.meta_state
    for instance in ctx.instances:
        removed = detachments(ctx, instance)
        if not removed or not apply_enabled("instances", str(instance.type_), [str(instance.runtime)]):
            continue
        old = ms.launch_params().get(instance.get_name()) or {}
        params = compute_launch_params(ctx, instance)
        params["user_data_sha256"] = hashlib.sha256(user_data_template(params).encode()).hexdigest()
        params["run"] = ctx.run_id
        params["launched"] = bool(old.get("launched", False))
        if old.get("launched_run"):
            params["launched_run"] = old["launched_run"]
        ms.record_launch_params(instance.get_name(), params)
        log.info(f"Instance {instance.get_name()}: detached {[m.get('storage') for m in removed]}; "
                 "launch parameters re-recorded without the mount(s)")


def forget_ephemerals(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner completed for real, every declared
    EPHEMERAL instance whose root applied was verified and torn down by
    its own sequence (stage 10.1): its launch parameters and pin are
    forgotten; the verification record in verifications.yaml remains."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    from .utils import apply_enabled
    if not apply_enabled("instances"):
        return
    from .commands.verify_instance import ON_FAILURE_TEARDOWN, VerificationFailed, failure_policy, last_verification
    ms = ctx.meta_state
    failed: list[dict[str, Any]] = []
    for inst in ctx.instances:
        if not getattr(inst, "ephemeral", False):
            continue
        if not apply_enabled("instances", str(inst.type_), [str(inst.runtime)]):
            continue
        name = inst.get_name()
        log.info(f"Ephemeral instance {name}: verified and torn down this run; forgetting its launch record")
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


def mark_launched(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner completed WITH applies enabled,
    every declared instance is launched: its parameters are now immutable."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    from .utils import apply_enabled
    if not apply_enabled("instances"):
        return
    ms = ctx.meta_state
    declared = {i.get_name(): i for i in ctx.instances}
    for name, params in ms.launch_params().items():
        inst = declared.get(name)
        # Per-root scoping (stage 7): a declared instance is launched only
        # when ITS root (builder name / runtime) was allowed to apply.
        if inst is not None and not apply_enabled("instances", str(inst.type_), [str(inst.runtime)]):
            continue
        if inst is not None:
            params = dict(params)
            params["launched"] = True
            params["launched_run"] = ctx.run_id
            ms.record_launch_params(name, params)
        ms.clear_pending_replacement(name)


def _comparable(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k not in _VOLATILE}


def detachments(ctx: "GlobalTypeContext", instance: Any) -> list[dict[str, Any]]:
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


def validate_immutability(ctx: "GlobalTypeContext", requested: list[Lifecycle]) -> list[str]:
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
        from .lineage import instance_follow_target
        if instance_follow_target(ctx, instance):
            continue   # a policy-driven replacement (stage 9.5) is a replacement
        new = compute_launch_params(ctx, instance)
        # stage 10.14: a mount REMOVAL is the one in-place change allowed (a
        # detach, unmounted first); everything else stays immutable
        removed = {str(m.get("storage")) for m in detachments(ctx, instance)}
        if removed and _without_mounts(old, removed) == _comparable(new):
            continue
        if _comparable(old) != _comparable(new):
            changed = sorted(k for k in set(_comparable(old)) | set(_comparable(new))
                             if _comparable(old).get(k) != _comparable(new).get(k))
            errors.append(
                f"instance '{name}' was launched (run {old.get('launched_run')}) and its launch "
                f"parameters changed ({', '.join(changed)}); launch parameters are immutable after "
                "launch -- replace the instance (upgrade instance, or decommission and redeclare) (N26)")
    return errors


def register(runner) -> None:
    runner.register_after_generate(record_launch_params)
    runner.register_after_apply(mark_launched)
    runner.register_after_apply(forget_decommissioned)
    runner.register_after_apply(forget_ephemerals)
    runner.register_after_apply(record_detachments)
    runner.register_validator(validate_immutability)
