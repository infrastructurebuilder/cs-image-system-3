# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The sanctioned image disposal (stage 8.4).

``dispose image <build-id>...`` / ``dispose image --runtime <rt> --all``
deletes RECORDED images from their runtime and drops their lineage record
and any image pin at them in the same operation -- what was done by hand
four times (the finding-46 shape). Refusals, all up front and before any
deletion: an unrecorded build (foreign images are adopted with ``state
import`` or left to the orphan sweep -- never deleted blind), a build a
recorded instance is pinned to or was launched from (decommission first),
a runtime that cannot dispose. Under the global ``--dry-run`` (the
default) nothing is deleted: the plan is reported.
"""
from __future__ import annotations

import logging
from dataclasses import field
from ..models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Any

from ..global_context import GlobalTypeContext

log = logging.getLogger(__name__)


@dataclass(config=CSIS_MODEL_CONFIG)
class Disposal:
    build_id: str
    runtime: str
    series: str | None
    deleted: bool | None = None          # None = dry run; False = already gone
    unpinned: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"build_id": self.build_id, "runtime": self.runtime, "series": self.series,
                "deleted": self.deleted, "unpinned": list(self.unpinned)}


def select_builds(ctx: GlobalTypeContext, build_ids: list[str] | None,
                  runtime: str | None, all_on_runtime: bool) -> list[dict[str, Any]]:
    ms = ctx.meta_state
    if all_on_runtime:
        if not runtime:
            raise ValueError("dispose: --all needs --runtime <name>")
        if runtime not in ctx.runtime_builders:
            raise ValueError(f"dispose: unknown runtime {runtime!r}; known: {sorted(ctx.runtime_builders)}")
        return [b for b in ms.builds() if b.get("runtime") == runtime]
    if not build_ids:
        raise ValueError("dispose: name build id(s), or --runtime <name> --all")
    out = []
    for bid in build_ids:
        rec = ms.build(bid)
        if rec is None:
            raise ValueError(
                f"dispose: build {bid!r} is not recorded in lineage; an unrecorded image is "
                "adopted with `state import` or left to the orphan sweep, never deleted blind")
        if runtime and rec.get("runtime") != runtime:
            raise ValueError(f"dispose: build {bid!r} was baked on {rec.get('runtime')!r}, not {runtime!r}")
        out.append(rec)
    return out


def refuse_if_in_use(ctx: GlobalTypeContext, records: list[dict[str, Any]]) -> None:
    ms = ctx.meta_state
    ids = {str(r.get("build_id")) for r in records}
    pinned = {name: b for name, b in ms.instance_pins().items() if b in ids}
    launched = {name: p.get("build") for name, p in ms.launch_params().items() if p.get("build") in ids}
    if pinned or launched:
        users = sorted(set(pinned) | set(launched))
        raise ValueError(
            f"dispose: instance(s) {users} are pinned to / launched from the build(s) "
            f"{sorted(ids & (set(pinned.values()) | set(launched.values())))}; decommission them first")
    for rec in records:
        rt = str(rec.get("runtime") or "")
        rtb = ctx.runtime_builders.get(rt)
        if rtb is None:
            raise ValueError(f"dispose: build {rec.get('build_id')!r} records runtime {rt!r}, which is not configured")


def retention_keep_for(ctx: GlobalTypeContext, series: str, runtime: str) -> int | None:
    """How many builds of ``series`` survive on ``runtime``: 0 on an ephemeral
    runtime (stage 10.4), else the image's ``retention.keep`` (stage 10.3),
    else the runtime's ``retention_keep``, else None = keep everything."""
    rtb = ctx.runtime_builders.get(runtime)
    model = getattr(rtb, "model", None)
    if getattr(model, "ephemeral", False):
        return 0
    image = ctx.images_map.get(series)
    retention = getattr(image, "retention", None) if image is not None else None
    if isinstance(retention, dict) and retention.get("keep") is not None:
        return int(retention["keep"])
    keep = getattr(model, "retention_keep", None)
    return int(keep) if keep is not None else None


def retention_plan(ctx: GlobalTypeContext, runtime: str | None = None
                   ) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str]]]:
    """``(disposable, debt)``: the recorded builds retention no longer keeps
    (oldest first within a series), and those retention would drop but an
    instance is pinned to / launched from (kept, reported)."""
    ms = ctx.meta_state
    in_use = set(ms.instance_pins().values()) | {p.get("build") for p in ms.launch_params().values()}
    # stage 14.4 (operator, 2026-09-09): released builds are exempt from
    # retention and from an ephemeral runtime's disposal -- kept, reported
    # like debt, removed only by an explicit `dispose image <id>`
    from ..release import releases
    released = {str(b) for images in (releases(ms).get("current") or {}).values() for b in images.values()}
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for b in ms.builds():
        rt = str(b.get("runtime") or "")
        if runtime and rt != runtime:
            continue
        by_key.setdefault((str(b.get("series")), rt), []).append(b)
    disposable: list[dict[str, Any]] = []
    debt: list[tuple[dict[str, Any], str]] = []
    for (series, rt), builds in sorted(by_key.items()):
        keep = retention_keep_for(ctx, series, rt)
        if keep is None:
            continue
        ordered = sorted(builds, key=lambda b: str(b.get("run") or ""))   # run ids sort chronologically
        drop = ordered[:len(ordered) - keep] if keep < len(ordered) else []
        for b in drop:
            if str(b.get("build_id")) in released:
                debt.append((b, "it is a RELEASED build (kept by decision; dispose it explicitly)"))
            elif str(b.get("build_id")) in in_use:
                debt.append((b, "an instance is pinned to it or was launched from it"))
            else:
                disposable.append(b)
    return disposable, debt


def dispose_images(build_ids: list[str] | None = None, runtime: str | None = None,
                   all_on_runtime: bool = False, retention: bool = False) -> list[Disposal]:
    ctx = GlobalTypeContext()
    ms = ctx.meta_state
    if retention:
        records, debt = retention_plan(ctx, runtime)
        for b, why in debt:
            log.warning(f"retention debt: {b.get('build_id')} ({b.get('series')}@{b.get('runtime')}) "
                        f"would be disposed but {why}")
    else:
        records = select_builds(ctx, build_ids, runtime, all_on_runtime)
    refuse_if_in_use(ctx, records)
    # Children before parents: a parent's disposal unpins the child's parent
    # pin, and a child still recorded is the more surprising leftover.
    parents = {str(r.get("build_id")) for r in records}
    ordered = sorted(records, key=lambda r: (str(r.get("parent")) not in parents, str(r.get("build_id"))))
    results: list[Disposal] = []
    for rec in ordered:
        bid = str(rec.get("build_id"))
        rt = str(rec.get("runtime"))
        rtb = ctx.runtime_builders[rt]
        d = Disposal(bid, rt, rec.get("series"))
        if ctx.dry_run:
            d.unpinned = [k for k, b in ms.image_pins().items() if b == bid]
            log.info(f"dispose (dry run): would delete {bid} from {rt}, drop its lineage record"
                     f"{' and unpin ' + ', '.join(d.unpinned) if d.unpinned else ''}")
            results.append(d)
            continue
        d.deleted = rtb.dispose_image(bid)        # raises NotImplementedError: nothing recorded
        d.unpinned = ms.unpin_images_at(bid, ctx.run_id)
        ms.remove_build(bid)
        log.info(f"disposed {bid} ({rt}): deleted={d.deleted}, lineage record dropped"
                 f"{', unpinned ' + ', '.join(d.unpinned) if d.unpinned else ''}")
        results.append(d)
    return results
