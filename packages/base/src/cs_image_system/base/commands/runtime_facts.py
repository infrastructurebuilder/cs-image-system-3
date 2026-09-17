# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Configuration-driven facts about a runtime (stage 11.5), so recipes need
no hardcoded project names: ``runtime describe <rt>`` and the emptiness
check ``empty --runtime <rt>`` (reality minus the declared storages must be
nothing, and the strict state query must agree).
"""
from __future__ import annotations

import logging
from typing import Any

from ..global_context import GlobalTypeContext

log = logging.getLogger(__name__)


def images_on_runtime(ctx: GlobalTypeContext, runtime: str) -> list[str]:
    """Every series baked on the runtime: base images with a runtime entry
    there, instance images with an image builder there."""
    from ..lineage import base_image_runtimes
    out: list[str] = []
    for series in ctx.os_builders:
        if runtime in base_image_runtimes(ctx, series):
            out.append(series)
    for builder in ctx.image_builders.values():
        model = getattr(builder, "model", None)
        if model is None or str(model.get_runtime_provider()) != runtime:
            continue
        for image in getattr(builder, "local_items", None) or []:
            if image is not None and image.get_name() not in out:
                out.append(image.get_name())
    return out


def declared_storage_names(ctx: GlobalTypeContext, runtime: str) -> dict[str, dict[str, Any]]:
    """``{storage: {"builder", "type", "cloud_name"}}`` for storages declared
    on the runtime, with the name the cloud knows them by (a disk name, a
    bucket name) from the builder's module arguments."""
    out: dict[str, dict[str, Any]] = {}
    for storage in ctx.storages:
        builder = ctx.storage_builders.get(str(storage.type_))
        model = getattr(builder, "model", None)
        if model is None or str(model.get_runtime_provider()) != runtime:
            continue
        cloud_name = storage.get_name()
        args_fn = getattr(builder, "module_args", None)
        if callable(args_fn):
            try:
                args: Any = args_fn(storage)
                cloud_name = str(args.get("bucket_name") or args.get("name") or cloud_name)
            except Exception as e:  # noqa: BLE001 - a fact, never fatal
                log.debug(f"module args of {storage.get_name()} unavailable: {e}")
        cap = getattr(builder, "capability_type", None)
        out[storage.get_name()] = {"builder": str(storage.type_), "type": str(cap()) if callable(cap) else None,
                                   "cloud_name": cloud_name, "state": storage.state}
    return out


def describe_runtime(runtime: str) -> dict[str, Any]:
    ctx = GlobalTypeContext()
    rtb = ctx.runtime_builders.get(runtime)
    if rtb is None:
        raise ValueError(f"unknown runtime {runtime!r}; known: {sorted(ctx.runtime_builders)}")
    model = rtb.model
    facts: dict[str, Any] = {"runtime": runtime, "type": rtb.get_type()}
    for key in ("project_id", "zone", "region", "account_id", "default_machine_type"):
        v = getattr(model, key, None)
        if v:
            facts[key] = str(v)
    facts["ephemeral"] = bool(getattr(model, "ephemeral", False))
    facts["retention_keep"] = getattr(model, "retention_keep", None)
    facts["images"] = images_on_runtime(ctx, runtime)
    facts["storages"] = declared_storage_names(ctx, runtime)
    facts["instances"] = sorted(i.get_name() for i in ctx.instances if str(getattr(i, "runtime", "")) == runtime)
    facts["ephemeral_instances"] = sorted(i.get_name() for i in ctx.instances
                                          if str(getattr(i, "runtime", "")) == runtime and getattr(i, "ephemeral", False))
    facts["builders"] = builders_on_runtime(ctx, runtime)
    facts["emission"] = emission_dirs(ctx, runtime)
    return facts


def builders_on_runtime(ctx: GlobalTypeContext, runtime: str) -> dict[str, list[str]]:
    """``{"image": [...], "storage": [...], "instance": [...]}`` -- the
    builders bound to the runtime (stage 45). Each emits under
    ``generated/<lifecycle>/<builder name>/``, so this is also the map of
    which emission belongs to the runtime."""
    families = {"image": ctx.image_builders, "storage": ctx.storage_builders, "instance": ctx.instance_builders}
    out: dict[str, list[str]] = {}
    for family, builders in families.items():
        names: list[str] = []
        for name, builder in builders.items():
            model = getattr(builder, "model", None)
            try:
                bound = str(model.get_runtime_provider()) if model is not None else None
            except ValueError:
                bound = None
            if bound == runtime:
                names.append(str(name))
        out[family] = sorted(names)
    return out


def emission_dirs(ctx: GlobalTypeContext, runtime: str) -> list[str]:
    """The ``<lifecycle>/<builder>`` directories under ``generated/`` that
    hold the runtime's emission and exist right now (stage 45): what a run
    scoped to another runtime leaves untouched, and what the CI job compares
    across records to know whether the runtime's declarations changed."""
    from ..lifecycles import all_lifecycles
    names = {n for family in builders_on_runtime(ctx, runtime).values() for n in family}
    root = ctx.root_generation_path
    out: list[str] = []
    for lc in all_lifecycles():
        for name in sorted(names):
            if (root / lc.value / name).is_dir():
                out.append(f"{lc.value}/{name}")
    return out


def emptiness(runtime: str) -> dict[str, Any]:
    """Reality on the runtime minus what the tree declares there: instances
    (any), images (any custom), disks and buckets other than the declared
    storages' cloud names. ``leftovers`` empty = empty."""
    ctx = GlobalTypeContext()
    rtb = ctx.runtime_builders.get(runtime)
    if rtb is None:
        raise ValueError(f"unknown runtime {runtime!r}; known: {sorted(ctx.runtime_builders)}")
    inv = rtb.inventory()
    declared = {v["cloud_name"] for v in declared_storage_names(ctx, runtime).values()}
    leftovers = {
        "instances": list(inv.get("instances") or []),
        # stage 14.4: a RELEASED build is declared to stay (kept by decision)
        "images": [i for i in (inv.get("images") or []) if i not in released_ids(ctx, runtime)],
        "disks": [d for d in (inv.get("disks") or []) if d not in declared],
        "buckets": [b for b in (inv.get("buckets") or []) if b not in declared],
    }
    return {"runtime": runtime, "declared_storages": sorted(declared), "inventory": inv,
            "leftovers": leftovers, "empty": not any(leftovers.values())}



def released_ids(ctx: Any, runtime: str) -> set[str]:
    """Build ids of released builds recorded on ``runtime`` (stage 14.4:
    they are declared to stay, so `empty --runtime` does not list them)."""
    from ..release import releases
    ms = ctx.meta_state
    current = {str(b) for images in (releases(ms).get("current") or {}).values() for b in images.values()}
    return {str(b.get("build_id")) for b in ms.builds()
            if str(b.get("build_id")) in current and str(b.get("runtime") or "") == runtime}
