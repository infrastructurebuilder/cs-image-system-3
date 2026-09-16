# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Re-stamp recorded fingerprints (stage 11.2).

Convergent bakes (§9) changed what the input fingerprint covers, so every
build recorded before it differs from what the tree computes now and the
next bake run would re-bake it once. For a runtime whose builds are known
to be current -- nothing about them changed but the hash recipe --
``lineage restamp --runtime <rt>`` records the current fingerprint on each
series head (the previous value and the run are kept under
``fingerprint_restamped``) and re-tags the cloud image's ``csis_fingerprint``
through the runtime's retag hook so the state query stays clean. Under the
global ``--dry-run`` it only reports. This is an operator statement about
those builds, recorded as such; `--force-bake` remains the way to re-bake.
"""
from __future__ import annotations

import logging
from ..models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Any

from ..global_context import GlobalTypeContext

log = logging.getLogger(__name__)


@dataclass(config=CSIS_MODEL_CONFIG)
class Restamp:
    build_id: str
    series: str
    runtime: str
    previous: str
    current: str
    retagged: bool | None = None       # None = dry run

    def as_dict(self) -> dict[str, Any]:
        return {"build_id": self.build_id, "series": self.series, "runtime": self.runtime,
                "previous": self.previous[:16], "current": self.current[:16], "retagged": self.retagged}


def restamp_plan(ctx: GlobalTypeContext, runtime: str, series: list[str] | None = None) -> list[Restamp]:
    from ..lineage import TAG_PREFIX, find_image, input_fingerprint  # noqa: F401
    ms = ctx.meta_state
    if runtime not in ctx.runtime_builders:
        raise ValueError(f"restamp: unknown runtime {runtime!r}; known: {sorted(ctx.runtime_builders)}")
    names = sorted({str(b.get("series")) for b in ms.builds() if str(b.get("runtime") or "") == runtime})
    heads: dict[str, dict[str, Any]] = {}
    for s in names:
        if series and s not in series:
            continue
        head = ms.series_head(s, runtime)           # the system's own definition of a head
        if head is not None:
            heads[s] = head
    out: list[Restamp] = []
    for s, head in sorted(heads.items()):
        image = find_image(ctx, s, runtime)
        if image is None:
            log.warning(f"restamp: series {s!r} has no image on {runtime} in the tree; skipped")
            continue
        current = input_fingerprint(ctx, image, runtime)
        previous = str(head.get("input_fingerprint") or "")
        if previous != current:
            out.append(Restamp(str(head["build_id"]), s, runtime, previous, current))
    return out


def restamp(runtime: str, series: list[str] | None = None) -> list[Restamp]:
    from ..lineage import TAG_PREFIX
    ctx = GlobalTypeContext()
    ms = ctx.meta_state
    plan = restamp_plan(ctx, runtime, series)
    if ctx.dry_run:
        for r in plan:
            log.info(f"restamp (dry run): {r.build_id} ({r.series}@{r.runtime}) "
                     f"{r.previous[:12] or 'unrecorded'} -> {r.current[:12]}")
        return plan
    rtb = ctx.runtime_builders[runtime]
    for r in plan:
        data = ms.read("lineage.yaml")
        for b in data.get("builds", []):
            if b.get("build_id") == r.build_id:
                b["input_fingerprint"] = r.current
                b.setdefault("fingerprint_restamped", []).append(
                    {"run": ctx.run_id, "previous": r.previous, "reason": "fingerprint recipe change (stage 9/§11.2)"})
        ms.write("lineage.yaml", data)
        try:
            r.retagged = bool(rtb.retag_image(r.build_id, {f"{TAG_PREFIX}fingerprint": r.current[:16]}))
        except Exception as e:  # noqa: BLE001 - the record is right; the tag can be fixed by the next retag pass
            log.warning(f"restamp: could not retag {r.build_id}: {e}")
            r.retagged = False
        log.info(f"restamped {r.build_id} ({r.series}@{r.runtime}): {r.previous[:12] or 'unrecorded'} -> "
                 f"{r.current[:12]}, retagged={r.retagged}")
    return plan
