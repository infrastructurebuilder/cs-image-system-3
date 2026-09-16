# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The explicit upgrade operation (DESIGN §3F5, N5, N17).

``upgrade instance <name> [--to <build>]`` / ``upgrade image <name> [--to
<build>]`` moves exactly one pinned edge -- never cascading -- and records the
move in meta-state. For an instance it is understood as a destroy-and-recreate
of that instance: the next instance-image run emits the new build and plans a
whitelisted replacement.
"""
from __future__ import annotations

import logging

from ..global_context import GlobalTypeContext

log = logging.getLogger(__name__)


def upgrade(kind: str, name: str, to: str | None = None,
            runtime: str | None = None) -> tuple[str | None, str]:
    ctx = GlobalTypeContext()
    ms = ctx.meta_state
    kind = kind.strip().lower()
    if kind not in ("instance", "image"):
        raise ValueError(f"upgrade: kind must be 'instance' or 'image', got {kind!r}")
    pin_name = name
    if kind == "instance":
        instances = {i.get_name(): i for i in ctx.instances}
        if name not in instances:
            raise ValueError(f"upgrade: instance {name!r} is not defined in the configuration")
        series = str(instances[name].image)
    else:
        images = ctx.images_map
        if name not in images:
            raise ValueError(f"upgrade: instance image {name!r} is not defined in the configuration")
        source = images[name].source_image
        if not source:
            raise ValueError(f"upgrade: image {name!r} has no source image to pin to")
        series = str(source)
        # image pins are per runtime: the primary runtime unless named; an
        # image baked on several runtimes must say which pin moves
        from ..lineage import primary_runtime_of
        image = images[name]
        runtimes = sorted({r for r in [primary_runtime_of(ctx, image)]
                           + [b.model.get_runtime_provider() for b in getattr(image, "extra_image_builders", [])] if r})
        if runtime is None:
            if len(runtimes) > 1:
                raise ValueError(f"upgrade: image {name!r} is baked on runtimes {runtimes}; pass --runtime")
            runtime = runtimes[0] if runtimes else None
        elif runtimes and runtime not in runtimes:
            raise ValueError(f"upgrade: image {name!r} is not baked on runtime {runtime!r} (has {runtimes})")
        pin_name = ms.image_pin_key(name, runtime)
    if to is None:
        head = ms.series_head(series, runtime if kind == "image" else None)
        if head is None:
            raise ValueError(
                f"upgrade: no build of series {series!r} is recorded in lineage; "
                "build it first or pass --to <build id>")
        to = str(head["build_id"])
    else:
        record = ms.build(to)
        if record is None:
            raise ValueError(f"upgrade: build {to!r} is not recorded in lineage")
        if record.get("series") != series:
            raise ValueError(
                f"upgrade: build {to!r} belongs to series {record.get('series')!r}, "
                f"not {series!r}")
    current = ms.instance_pin(name) if kind == "instance" else ms.image_pin(name, runtime)
    if current == to:
        raise ValueError(f"upgrade: {kind} {name!r} is already pinned to {to}")
    if kind == "image" and record_runtime_mismatch(ms, to, runtime):
        raise ValueError(f"upgrade: build {to!r} was baked on runtime {ms.build(to).get('runtime')!r}, not {runtime!r}")  # type: ignore[union-attr]
    previous = ms.move_pin(kind, pin_name, to, ctx.run_id)
    log.info(f"upgrade: {kind} {name} pin moved {previous} -> {to} (run {ctx.run_id})")
    return previous, to


def record_runtime_mismatch(ms, build_id: str, runtime: str | None) -> bool:
    record = ms.build(build_id)
    return bool(runtime and record and record.get("runtime") and record.get("runtime") != runtime)
