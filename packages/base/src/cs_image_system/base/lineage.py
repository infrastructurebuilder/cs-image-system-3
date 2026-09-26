# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Image lineage and pinning (DESIGN §3F4/§3F5, §3M, N5, N11, N17, N23, N24).

Image generation is inherently non-idempotent: every run that bakes writes a
NEW image. The system embraces it:

* every build gets a unique name (series id + run discriminator) and carries
  lineage metadata as tags -- series, parent, run, input fingerprint, and
  the declared capabilities stamped at bake time;
* after a bake, each built artifact is recorded in ``meta-state/lineage.yaml``
  together with the modifications it received (operation, content hash,
  run id -- N23c); builds are never deleted;
* consumers bind to a series ONCE (first bind -> the series head, or the
  build of this very run) and stay pinned; only an explicit upgrade moves a
  pin, one edge at a time, never cascading.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .capabilities import declared_capabilities, effective_capabilities, image_chain
from .constants import SELF
from .encryption import MARKER_PREFIX, substitute_markers

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)

TAG_PREFIX = "csis_"

# Convergent bakes (stage 9)
POLICY_PINNED = "pinned"
POLICY_FOLLOW = "follow"
POLICIES = (POLICY_PINNED, POLICY_FOLLOW)
FORCE_ALL = "all"                      # `--force-bake all`
RUN_ID_FORMAT = "%Y_%m_%dt%H_%M_%S_%f"


def _sha(data: Any) -> str:
    text = json.dumps(data, sort_keys=True, default=str)
    # stage 49: hash the MATERIALISED form. An emission carries the ciphertext,
    # and age is randomised, so a `reencrypt` mints new ciphertext for the same
    # plaintext -- hashing the marker would move every fingerprint on every
    # rotation and mark every image DUE for a rebake that changes nothing.
    if MARKER_PREFIX in text:
        text = substitute_markers(text)
    return hashlib.sha256(text.encode()).hexdigest()


def is_base_image(ctx: "GlobalTypeContext", image: Any) -> bool:
    return image.get_name() in ctx.os_builders


def series_of(image: Any) -> str:
    """The stable series identifier: the logical image name."""
    return str(image.get_name())


def primary_runtime_of(ctx: "GlobalTypeContext", image: Any) -> str | None:
    """The runtime of the image's primary image builder (its ``type``); an
    image baked on several runtimes has one pin per runtime, and callers
    that know their runtime pass it explicitly."""
    ib = getattr(image, "image_builder", None)
    if ib is None:
        ib = ctx.image_builders.get(str(getattr(image, "type_", "") or ""))
    if ib is None and image.get_name() in ctx.os_builders:
        ib = ctx.image_builders.get(ctx.os_builders[image.get_name()].model.get_image_builder())
    model = getattr(ib, "model", None)
    return str(model.get_runtime_provider()) if model is not None else None


def capability_stamp(ctx: "GlobalTypeContext", image: Any, runtime: str | None = None) -> dict[str, list[str]]:
    """Base image: its own declaration. Instance image: the root's stamp,
    inherited through the pinned chain (N24) on the bake's runtime."""
    if is_base_image(ctx, image):
        return declared_capabilities(ctx, image.get_name())
    caps = effective_capabilities(ctx, image, runtime or primary_runtime_of(ctx, image))
    if caps is None:
        return {"identity_types": [], "storage_types": []}
    return {"identity_types": list(caps.identity_types), "storage_types": list(caps.storage_types)}


def mod_records(ctx: "GlobalTypeContext", image: Any) -> list[dict[str, Any]]:
    """Every modification applied at this bake: operation + content hash
    (N23c). Ansible playbooks hash their file contents when present, bash
    scripts their text; the mod's config participates too."""
    records: list[dict[str, Any]] = []
    for mod in getattr(image, "modifications", None) or []:
        if isinstance(mod, dict):
            records.append({"name": mod.get("name"), "type": mod.get("type"),
                            "content_hash": _sha(mod), "run": ctx.run_id})
            continue
        payload: dict[str, Any] = {"type": mod.get_type(), "config": getattr(mod, "config", {}) or {}}
        playbooks = getattr(mod, "playbooks", None)
        if playbooks:
            contents = []
            for pb in playbooks:
                p = Path(str(pb))
                candidates = [p] if p.is_absolute() else [Path(ctx.working_path) / p, p]
                text = next((c.read_text() for c in candidates if c.is_file()), str(pb))
                contents.append({"playbook": str(pb), "content": text})
            payload["playbooks"] = contents
        script = getattr(mod, "script", None)
        if script:
            payload["script"] = list(script)
        script_files = getattr(mod, "scripts", None)
        if script_files:
            contents = []
            for sf in script_files:
                p = Path(str(sf))
                candidates = [p] if p.is_absolute() else [Path(ctx.working_path) / p, p]
                text = next((c.read_text() for c in candidates if c.is_file()), str(sf))
                contents.append({"script": str(sf), "content": text})
            payload["scripts"] = contents
        ensure = getattr(mod, "ensure", None)
        if ensure:
            payload["ensure"] = ensure
        is_bash = bool(script or script_files or ensure)
        records.append({"name": mod.get_name(), "type": mod.get_type(),
                        "operation": "ansible" if playbooks else ("bash" if is_bash else mod.get_type()),
                        # ansible modules are idempotent by construction; bash only when declarative
                        "idempotent": "ansible" if playbooks else (getattr(mod, "idempotent", None) or "unknown"),
                        "content_hash": _sha(payload), "run": ctx.run_id})
    return records


def input_fingerprint(ctx: "GlobalTypeContext", image: Any, runtime: str | None = None) -> str:
    """Hash of everything that determines the build's CONTENT -- the bake
    decision (stage 9) compares it with the series head's recorded value.

    IN: series; the parent build the bake is FROM (the effective pin, so a
    moved parent changes the fingerprint); the capability stamp; every
    modification's content hash; the in-bake verification commands; the
    bake disk size (it becomes every instance's boot-disk size); and for
    base images the declared vendor source (family/version/architecture,
    the query, the runtime entry's image id/name), the admin user and keys,
    and the update policy.
    OUT (execution detail, not content): machine type, preemptible, IAP,
    ssh username, the run id and timestamps. Vendor-family MOVEMENT is
    also out -- the declared reference is hashed, not what the family
    resolves to today; `update.refresh_days` is the way to pick that up.
    """
    runtime = runtime or primary_runtime_of(ctx, image)
    payload: dict[str, Any] = {
        "series": series_of(image),
        "parent": parent_reference(ctx, image, runtime),
        "capabilities": capability_stamp(ctx, image, runtime),
        "mods": [{k: v for k, v in r.items() if k != "run"} for r in mod_records(ctx, image)],
        "tests": _verify_commands(ctx, image, runtime),
        "disk_size": _bake_disk_size(ctx, image, runtime),
    }
    if is_base_image(ctx, image):
        # every base-image input is read from the OS builder MODEL (by name), so
        # the plan-time stand-in and the resolved BaseImage hash identically
        model = ctx.os_builders[image.get_name()].model
        payload["mods"] = []
        payload["vendor"] = _vendor_source(ctx, image, runtime)
        payload["admin_user"] = model.get_admin_user()
        payload["admin_public_keys"] = model.get_admin_public_keys()
        payload["update"] = update_policy_of(ctx, image)
    return _sha(payload)


def _verify_commands(ctx: "GlobalTypeContext", image: Any, runtime: str | None) -> list[str]:
    try:
        from .image_tests import base_image_verify_commands, instance_image_verify_commands
        if is_base_image(ctx, image):
            return list(base_image_verify_commands(ctx, image, str(runtime))) if runtime else []
        return list(instance_image_verify_commands(ctx, image))
    except Exception as e:  # a half-configured tree must still fingerprint
        log.debug(f"verify commands unavailable for fingerprint of {series_of(image)}: {e}")
        return []


def bake_disk_size(ctx: "GlobalTypeContext", image: Any, runtime: str | None) -> int | str | None:
    """The disk a bake of ``image`` on ``runtime`` gets, in GB -- the ONE rule
    the packer sources and the fingerprint both use (stage 63): the runtime's
    own ``default_disk_size`` when it declares one (finding 51: a GCE boot
    disk is exactly its image's disk); for a base image, its OS builder
    entry's ``default_primary_disk_size`` for this runtime when declared, else
    the OS builder's; for an instance image, its own ``primary_disk_size``.
    Before stage 63 the fingerprint hashed the entry's value (default 100)
    while the bake used the OS builder's (200)."""
    rtb = ctx.runtime_builders.get(str(runtime)) if runtime else None
    rt_disk = getattr(getattr(rtb, "model", None), "default_disk_size", None)
    if rt_disk:
        return int(rt_disk)
    if is_base_image(ctx, image):
        model = ctx.os_builders[image.get_name()].model
        for sub in getattr(model, "runtimes", None) or []:
            if _subconfig_runtime(ctx, sub) == runtime and getattr(sub, "default_primary_disk_size", None):
                return int(sub.default_primary_disk_size)
        size = getattr(model, "default_primary_disk_size", None)
        return None if size in (None, "", "DEFAULT") else size
    size = getattr(image, "primary_disk_size", None)
    return None if size in (None, "", "DEFAULT") else size


_bake_disk_size = bake_disk_size


def _subconfig_runtime(ctx: "GlobalTypeContext", sub: Any) -> str | None:
    ib = ctx.image_builders.get(str(getattr(sub, "image_builder", "") or ""))
    model = getattr(ib, "model", None)
    return str(model.get_runtime_provider()) if model is not None else None


class BaseImageRef:
    """A plan-time stand-in for a base image (stage 9): the real BaseImage
    is synthesized only during the base-image lifecycle's resolution. It
    carries exactly the attributes the fingerprint's inputs read from the
    object (the verify commands: capability axes, admin user/keys, tests),
    set from the OS builder model the way the synthesizer sets them, so
    the stand-in and the resolved BaseImage hash identically."""
    __slots__ = ("name", "identity_types", "storage_types", "admin_user", "admin_public_keys", "tests")

    def __init__(self, name: str, model: Any = None) -> None:
        self.name = name
        self.identity_types = list(model.get_identity_types()) if model is not None else []
        self.storage_types = list(model.get_storage_types()) if model is not None else []
        self.admin_user = model.get_admin_user() if model is not None else None
        self.admin_public_keys = model.get_admin_public_keys() if model is not None else None
        self.tests = dict(getattr(model, "tests", None) or {}) if model is not None else {}

    def get_name(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"BaseImageRef({self.name!r})"


def base_image_runtimes(ctx: "GlobalTypeContext", series: str) -> list[str]:
    """Runtimes the named OS builder bakes on (one per runtime entry)."""
    osb = ctx.os_builders.get(series)
    model = getattr(osb, "model", None)
    out: list[str] = []
    for sub in getattr(model, "runtimes", None) or []:
        rt = _subconfig_runtime(ctx, sub)
        if rt and rt not in out:
            out.append(rt)
    return out


def _vendor_source(ctx: "GlobalTypeContext", image: Any, runtime: str | None) -> dict[str, Any]:
    osb = ctx.os_builders.get(image.get_name())
    model = getattr(osb, "model", None)
    if model is None:
        return {}
    out: dict[str, Any] = {k: getattr(model, k, None) for k in ("family", "family_version", "architecture")}
    out["query"] = dict(getattr(model, "query", None) or {})
    for sub in getattr(model, "runtimes", None) or []:
        sub_rt = _subconfig_runtime(ctx, sub)
        if runtime is None or sub_rt == runtime:
            out["runtime_source"] = {"image_id": getattr(sub, "image_id", None),
                                     "image_name": getattr(sub, "image_name", None),
                                     "query": dict(getattr(sub, "query", None) or {})}
            break
    return out


def update_policy_of(ctx: "GlobalTypeContext", image: Any) -> dict[str, Any] | None:
    """The base image's effective update policy (None for instance images)."""
    osb = ctx.os_builders.get(image.get_name())
    if osb is None:
        return None
    return osb.model.effective_update_policy().as_dict()


def parent_policy_of(image: Any) -> str:
    """``pinned`` (N17, default) or ``follow`` (stage 9)."""
    return str(getattr(image, "parent_policy", None) or POLICY_PINNED).strip().lower()


def effective_parent_build(ctx: "GlobalTypeContext", image: Any,
                           runtime: str | None = None) -> tuple[str | None, str | None]:
    """``(the parent build this image bakes FROM, the pin it supersedes)``.
    Pinned: the pin, superseding nothing. Follow: the parent series' head
    on this runtime when it is newer than the pin -- read-only here, so a
    dry run moves nothing; the pin moves when the bake is recorded."""
    if is_base_image(ctx, image):
        return None, None
    runtime = runtime or primary_runtime_of(ctx, image)
    ms = ctx.meta_state
    pin = ms.image_pin(image.get_name(), runtime)
    src = getattr(image, "source_image", None)
    if pin and parent_policy_of(image) == POLICY_FOLLOW and src and src != SELF:
        head = ms.series_head(str(src), runtime)
        head_id = str(head.get("build_id")) if head and head.get("build_id") else None
        if head_id and head_id != pin:
            return head_id, pin
    return pin, None


def parent_reference(ctx: "GlobalTypeContext", image: Any, runtime: str | None = None) -> str:
    """The build this image is baked FROM: the effective parent build id
    (the pin, or under ``follow`` a newer parent head) on this runtime,
    else the parent series (bound at bake), else the vendor source."""
    if is_base_image(ctx, image):
        return "vendor"
    build, _ = effective_parent_build(ctx, image, runtime)
    if build:
        return build
    src = getattr(image, "source_image", None)
    return f"series:{src}" if src and src != SELF else "vendor"


def _will_bake_this_run(ctx: "GlobalTypeContext", series: str, runtime: str | None) -> bool:
    """Whether the named image bakes in THIS run (convergent bakes, stage 9):
    it is in the run's surface and its bake decision is not `current`."""
    only = getattr(ctx, "only_images", None)
    if only is not None and series not in only and f"{series}@{runtime}" not in only:
        return False
    image = find_image(ctx, series, runtime)
    if image is None:
        return True   # unknown shape: keep the historical "built this run" reading
    return bake_reason(ctx, image, runtime) is not None


def find_image(ctx: "GlobalTypeContext", series: str, runtime: str | None = None) -> Any | None:
    """The image object a series name denotes: an instance image from the
    map, or a base image from the image builders' OS-builder items (on
    ``runtime`` when given)."""
    image = ctx.images_map.get(series)
    if image is not None:
        return image
    if series in ctx.os_builders and (runtime is None or runtime in base_image_runtimes(ctx, series)):
        return BaseImageRef(series, ctx.os_builders[series].model)
    return None


def validate_policies(ctx: "GlobalTypeContext") -> list[str]:
    """Hard generation-time errors for unknown policies (stage 9)."""
    errors: list[str] = []
    for image in ctx.images_map.values():
        if parent_policy_of(image) not in POLICIES:
            errors.append(f"image '{image.get_name()}': parent_policy {getattr(image, 'parent_policy', None)!r} "
                          f"is not one of {POLICIES}")
    for image in ctx.images_map.values():
        retention = getattr(image, "retention", None)
        if retention is not None:
            keep = retention.get("keep") if isinstance(retention, dict) else None
            if not isinstance(retention, dict) or not isinstance(keep, int) or keep < 0:
                errors.append(f"image '{image.get_name()}': retention must be {{keep: <non-negative int>}}, "
                              f"got {retention!r}")
        rel = getattr(image, "release", None)
        if rel is not None:
            model = rel.get("model") if isinstance(rel, dict) else None
            if not isinstance(rel, dict) or not isinstance(model, str) or not model.strip():
                errors.append(f"image '{image.get_name()}': release must be {{model: <name>}}, got {rel!r}")
    for rt, rtb in ctx.runtime_builders.items():
        keep = getattr(getattr(rtb, "model", None), "retention_keep", None)
        if keep is not None and (not isinstance(keep, int) or keep < 0):
            errors.append(f"runtime '{rt}': retention_keep must be a non-negative int, got {keep!r}")
    from .commands.verify_instance import ON_FAILURE_POLICIES, parse_duration
    for instance in ctx.instances:
        pol = getattr(instance, "on_failure", None)
        if pol is not None and str(pol).strip().lower() not in ON_FAILURE_POLICIES:
            errors.append(f"instance '{instance.get_name()}': on_failure {pol!r} is not one of {ON_FAILURE_POLICIES}")
        try:
            parse_duration(getattr(instance, "teardown_after", None))
        except ValueError as e:
            errors.append(f"instance '{instance.get_name()}': teardown_after: {e}")
    for rt, rtb in ctx.runtime_builders.items():
        pol = getattr(getattr(rtb, "model", None), "on_failure", None)
        if pol is not None and str(pol).strip().lower() not in ON_FAILURE_POLICIES:
            errors.append(f"runtime '{rt}': on_failure {pol!r} is not one of {ON_FAILURE_POLICIES}")
        try:
            parse_duration(getattr(getattr(rtb, "model", None), "teardown_after", None))
        except ValueError as e:
            errors.append(f"runtime '{rt}': teardown_after: {e}")
    for instance in ctx.instances:
        if image_policy_of(instance) not in POLICIES:
            errors.append(f"instance '{instance.get_name()}': image_policy {getattr(instance, 'image_policy', None)!r} "
                          f"is not one of {POLICIES}")
    return errors


def pinned_parent_build(ctx: "GlobalTypeContext", image: Any, runtime: str | None = None) -> str | None:
    """N17: a rebuild bakes FROM its pinned base build ON ITS RUNTIME (under
    ``follow``, from a newer parent head). First bind (no pin yet): the
    recorded head of the parent series on that runtime, pinned now --
    unless the parent is being built in this very run (the bind then
    happens after the bake, from the manifest). A parent that is in the
    run but skipped as current (stage 9) binds now, to its head."""
    if is_base_image(ctx, image):
        return None
    runtime = runtime or primary_runtime_of(ctx, image)
    ms = ctx.meta_state
    build, superseded = effective_parent_build(ctx, image, runtime)
    if build:
        if superseded:
            log.info(f"Image {image.get_name()} follows its parent: bakes from {build} (pin {superseded} moves after the bake)")
        return build
    src = getattr(image, "source_image", None)
    if not src or src == SELF:
        return None
    from .lifecycles import Lifecycle
    parent_built_this_run = ((src in ctx.os_builders and Lifecycle.BASE_IMAGE in ctx.generated_lifecycles) or (
        src in ctx.images_map and ctx.current_lifecycle == Lifecycle.INSTANCE_IMAGE)) \
        and _will_bake_this_run(ctx, str(src), runtime)
    if parent_built_this_run:
        return None
    head = ms.series_head(str(src), runtime)
    if head and head.get("build_id"):
        ms.bind_image(image.get_name(), str(head["build_id"]), ctx.run_id, runtime)
        log.info(f"First bind: image {image.get_name()} -> {src} build {head['build_id']} "
                 f"(series head on {runtime})")
        return str(head["build_id"])
    return None


def lineage_tags(ctx: "GlobalTypeContext", image: Any, runtime: str | None = None) -> dict[str, str]:
    caps = capability_stamp(ctx, image, runtime)
    return {
        f"{TAG_PREFIX}series": series_of(image),
        f"{TAG_PREFIX}parent": parent_reference(ctx, image, runtime),
        f"{TAG_PREFIX}run": ctx.run_id,
        f"{TAG_PREFIX}fingerprint": input_fingerprint(ctx, image, runtime)[:16],
        f"{TAG_PREFIX}identity_types": ",".join(caps["identity_types"]),
        f"{TAG_PREFIX}storage_types": ",".join(caps["storage_types"]),
    }


def _assertion_count(ctx: "GlobalTypeContext", image: Any, runtime: str) -> int:
    from .image_tests import assertion_count, base_image_verify_commands, instance_image_verify_commands
    cmds = (base_image_verify_commands(ctx, image, runtime) if is_base_image(ctx, image)
            else instance_image_verify_commands(ctx, image))
    return assertion_count(cmds)


def record_build(ctx: "GlobalTypeContext", image: Any, runtime: str, build_id: str,
                 name: str | None, resolve_parent) -> dict[str, Any]:
    """Append the lineage record of one built artifact and perform the
    first-bind of its parent edge when the parent was built this run."""
    ms = ctx.meta_state
    parent = parent_reference(ctx, image, runtime)
    if parent.startswith("series:"):
        resolved = resolve_parent(parent[len("series:"):])
        if resolved:
            parent = resolved
            if not ms.image_pin(image.get_name(), runtime):
                ms.bind_image(image.get_name(), resolved, ctx.run_id, runtime)
                log.info(f"First bind: image {image.get_name()} -> build {resolved} (built this run, {runtime})")
    else:
        # follow (stage 9): the bake used a newer parent head; now that the
        # bake succeeded, the pin moves to it -- one edge, recorded
        current_pin = ms.image_pin(image.get_name(), runtime)
        if current_pin and parent != current_pin and parent != "vendor":
            ms.move_pin("image", ms.image_pin_key(image.get_name(), runtime), parent, ctx.run_id, op="follow")
            log.info(f"Image {image.get_name()} pin moved {current_pin} -> {parent} (parent_policy: follow)")
    record = {
        "build_id": build_id,
        "series": series_of(image),
        "runtime": runtime,
        "name": name,
        "parent": parent,
        "input_fingerprint": input_fingerprint(ctx, image, runtime),
        "run": ctx.run_id,
        "capabilities": capability_stamp(ctx, image, runtime),
        "mods": mod_records(ctx, image),
        "local_mods": bool(getattr(image, "modifications", None)) and not is_base_image(ctx, image),
        # a build exists only because its bake -- verification included -- succeeded
        "tests": {"in_bake": True, "assertions": _assertion_count(ctx, image, runtime)},
        "update": update_policy_of(ctx, image),
        "chain": image_chain(ctx, image)[0] if not is_base_image(ctx, image) else [],
    }
    ms.add_build(record)
    return record


def pinned_instance_build(ctx: "GlobalTypeContext", instance: Any) -> str | None:
    """N5/F5: an instance stays on its pinned build. First bind at
    generation: the recorded head of its image's series (unless the image
    is being built this run, in which case binding follows the bake)."""
    ms = ctx.meta_state
    name = instance.get_name()
    pin = ms.instance_pin(name)
    if pin:
        target = instance_follow_target(ctx, instance)
        return target[1] if target else pin
    image = str(instance.image) if instance.image else None
    if not image:
        return None
    from .lifecycles import Lifecycle
    runtime = str(instance.runtime) if getattr(instance, "runtime", None) else None
    if (ctx.current_lifecycle == Lifecycle.INSTANCE_IMAGE and image in ctx.images_map
            and _will_bake_this_run(ctx, image, runtime)):
        return None  # being built now: bound from the manifest after the bake
    head = ms.series_head(image, runtime)
    if head and head.get("build_id"):
        ms.bind_instance(name, str(head["build_id"]), ctx.run_id)
        log.info(f"First bind: instance {name} -> build {head['build_id']} (series head)")
        return str(head["build_id"])
    return None



# ------------------------------------------------- convergent bakes (stage 9)

def image_policy_of(instance: Any) -> str:
    return str(getattr(instance, "image_policy", None) or POLICY_PINNED).strip().lower()


def instance_follow_target(ctx: "GlobalTypeContext", instance: Any) -> tuple[str, str] | None:
    """``(pin, head)`` when a launched-and-pinned instance declares
    ``image_policy: follow`` and its image's series head on its runtime is
    newer than its pin: the gated replacement to plan. Read-only; the pin
    moves after the apply (the instance builder's post-finalize hook)."""
    if image_policy_of(instance) != POLICY_FOLLOW:
        return None
    ms = ctx.meta_state
    pin = ms.instance_pin(instance.get_name())
    image = str(instance.image) if instance.image else None
    if not pin or not image:
        return None
    runtime = str(instance.runtime) if getattr(instance, "runtime", None) else None
    head = ms.series_head(image, runtime)
    head_id = str(head.get("build_id")) if head and head.get("build_id") else None
    if head_id and head_id != pin:
        return pin, head_id
    return None


def pending_instance_replacements(ctx: "GlobalTypeContext", instances: list[Any]) -> set[str]:
    """Instances to force-replace in this plan: explicit upgrades (pending
    replacements) plus ``follow`` targets."""
    pending = set(ctx.meta_state.pending_replacements())
    names = set()
    for i in instances:
        if i.get_name() in pending or instance_follow_target(ctx, i):
            names.add(i.get_name())
    return names


def _head_age_days(ctx: "GlobalTypeContext", head: dict[str, Any]) -> float | None:
    run = str(head.get("run") or "")
    try:
        built = datetime.strptime(run, RUN_ID_FORMAT)
    except ValueError:
        return None
    return (datetime.now() - built).total_seconds() / 86400.0


def _bake_reason(ctx: "GlobalTypeContext", image: Any, runtime: str | None) -> str | None:
    name = series_of(image)
    forced = getattr(ctx, "force_bake", None)
    if forced and (FORCE_ALL in forced or name in forced or f"{name}@{runtime}" in forced):
        return "forced (--force-bake)"
    ms = ctx.meta_state
    head = ms.series_head(name, runtime)
    if head is None or not head.get("build_id"):
        return f"no build of {name} on {runtime} yet"
    build, superseded = effective_parent_build(ctx, image, runtime)
    if superseded:
        return f"parent moved {superseded} -> {build} (parent_policy: follow)"
    # ledger 70: under `follow` a parent that BAKES IN THIS RUN is a move too
    # (its new head is not recorded yet at plan time, so the pin/head
    # comparison above sees nothing): the child bakes from the series and
    # its pin follows when the bake is recorded. Kept out of
    # effective_parent_build on purpose -- the fingerprint hashes the parent
    # reference, and a bake DECISION must never move a fingerprint.
    src = getattr(image, "source_image", None)
    if (build and parent_policy_of(image) == POLICY_FOLLOW and src and src != SELF
            and _will_bake_this_run(ctx, str(src), runtime)):
        return f"parent {build} re-bakes this run (parent_policy: follow)"
    fp = input_fingerprint(ctx, image, runtime)
    recorded = str(head.get("input_fingerprint") or "")
    if recorded != fp:
        return f"inputs changed ({recorded[:12] or 'unrecorded'} -> {fp[:12]})"
    policy = update_policy_of(ctx, image) or {}
    days = policy.get("refresh_days")
    if days:
        age = _head_age_days(ctx, head)
        if age is not None and age >= float(days):
            return f"update policy: head {head['build_id']} is {age:.0f} days old (refresh_days: {days})"
    return None


def bake_reason(ctx: "GlobalTypeContext", image: Any, runtime: str | None = None) -> str | None:
    """Why this image bakes on this runtime in THIS run, or None when it is
    current (the series head was built from the same inputs, its parent
    has not moved under ``follow``, no refresh is due, nothing forced).
    Cached per run so every path -- sources, provisioners, runner scripts,
    recording -- sees one decision."""
    runtime = runtime or primary_runtime_of(ctx, image)
    key = f"{series_of(image)}@{runtime}"
    cache = getattr(ctx, "bake_decisions", None)
    if cache is not None and key in cache:
        return cache[key]
    reason = _bake_reason(ctx, image, runtime)
    if cache is not None:
        cache[key] = reason
    return reason


def bake_plan(ctx: "GlobalTypeContext") -> dict[str, str]:
    """``{"<series>@<runtime>": "bake: <reason>" | "skip: current (build …)"
    | "skip: not selected (--only)"}`` for every image of every image
    builder -- the run's bake surface, explained. Journaled with the run."""
    plan: dict[str, str] = {}
    only = getattr(ctx, "only_images", None)
    surface: list[tuple[Any, str | None]] = []
    for series, osb in ctx.os_builders.items():         # base images, per runtime entry
        for rt in base_image_runtimes(ctx, series):
            surface.append((BaseImageRef(series, osb.model), rt))
    for builder in ctx.image_builders.values():          # instance images, per builder
        model = getattr(builder, "model", None)
        rt = str(model.get_runtime_provider()) if model is not None else None
        surface.extend((image, rt) for image in (getattr(builder, "local_items", None) or []) if image is not None)
    for image, rt in surface:
        if True:
            name = series_of(image)
            key = f"{name}@{rt}"
            if only is not None and name not in only and key not in only:
                implied = getattr(ctx, "implied_scope", None)
                if implied and rt != implied:                # stage 12: --apply-runtime implied the filter
                    plan[key] = f"skip: outside the apply scope (--apply-runtime {implied})"
                else:
                    plan[key] = "skip: not selected (--only)"
                continue
            reason = bake_reason(ctx, image, rt)
            if reason is None:
                head = ctx.meta_state.series_head(name, rt) or {}
                plan[key] = f"skip: current (build {head.get('build_id')})"
            else:
                plan[key] = f"bake: {reason}"
    return plan
