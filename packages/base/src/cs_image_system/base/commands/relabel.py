# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Re-label cloud images from their lineage records (ledger 66).

The state query's ``changed`` drift means a cloud image's lineage tags
disagree with its record. The record is the truth (it was written after
the bake, when the parent build was known; the tags were written at
generation time by packer). ``lineage restamp`` fixes the RECORD side
when the fingerprint recipe changed; ``lineage relabel --runtime <rt>``
fixes the TAG side: every recorded build on the runtime whose real tags
differ on the drift rule's facts (``series``, ``parent``, ``run``, the
fingerprint prefix) is re-tagged through the runtime's retag hook. No
meta-state changes. Under the global ``--dry-run`` it only reports.
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
class Relabel:
    build_id: str
    series: str
    runtime: str
    tags: dict[str, str]                    # what the image will carry (record truth)
    differences: list[str] = field(default_factory=list)
    retagged: bool | None = None            # None = dry run

    def as_dict(self) -> dict[str, Any]:
        return {"build_id": self.build_id, "series": self.series, "runtime": self.runtime,
                "tags": dict(self.tags), "differences": list(self.differences), "retagged": self.retagged}


def record_tags(record: dict[str, Any]) -> dict[str, str]:
    """The lineage tags a record says its image must carry."""
    from ..lineage import TAG_PREFIX
    from ..state_query import _TAGGED_FACTS
    tags = {f"{TAG_PREFIX}{fact}": str(record.get(fact) or "") for fact in _TAGGED_FACTS}
    tags[f"{TAG_PREFIX}fingerprint"] = str(record.get("input_fingerprint") or "")[:16]
    return {k: v for k, v in tags.items() if v}


def relabel_plan(ctx: GlobalTypeContext, runtime: str, builds: list[str] | None = None) -> list[Relabel]:
    from ..lineage import TAG_PREFIX
    ms = ctx.meta_state
    if runtime not in ctx.runtime_builders:
        raise ValueError(f"relabel: unknown runtime {runtime!r}; known: {sorted(ctx.runtime_builders)}")
    rtb = ctx.runtime_builders[runtime]
    recorded = [b for b in ms.builds() if str(b.get("runtime") or "") == runtime
                and (not builds or str(b.get("build_id")) in builds)]
    if not recorded:
        return []
    real = {str(r.get("image_id")): r for r in
            rtb.query_images(sorted({str(b.get("series")) for b in recorded}))}
    out: list[Relabel] = []
    for b in recorded:
        bid = str(b.get("build_id"))
        image = real.get(bid)
        if image is None:
            log.warning(f"relabel: {bid} is not in {runtime}; nothing to relabel (state query reports it)")
            continue
        tags = image.get("tags") or {}
        wanted = record_tags(b)
        diffs = []
        for key, value in wanted.items():
            have = tags.get(key)
            if have is None:
                continue                                  # a tag the image never carried is not drift
            if key == f"{TAG_PREFIX}fingerprint":
                if not str(b.get("input_fingerprint", "")).startswith(str(have)):
                    diffs.append(f"fingerprint: tag={have} record={value}")
            elif str(have) != value:
                diffs.append(f"{key[len(TAG_PREFIX):]}: tag={have} record={value}")
        if diffs:
            out.append(Relabel(bid, str(b.get("series")), runtime, wanted, diffs))
    return out


def relabel(runtime: str, builds: list[str] | None = None) -> list[Relabel]:
    ctx = GlobalTypeContext()
    plan = relabel_plan(ctx, runtime, builds)
    if ctx.dry_run:
        for r in plan:
            log.info(f"relabel (dry run): {r.build_id} ({r.series}@{r.runtime}): {'; '.join(r.differences)}")
        return plan
    rtb = ctx.runtime_builders[runtime]
    for r in plan:
        try:
            r.retagged = bool(rtb.retag_image(r.build_id, dict(r.tags)))
        except Exception as e:  # noqa: BLE001 - the record is right; the state query keeps showing the tag
            log.warning(f"relabel: could not retag {r.build_id}: {e}")
            r.retagged = False
        log.info(f"relabelled {r.build_id} ({r.series}@{r.runtime}): {'; '.join(r.differences)}; "
                 f"retagged={r.retagged}")
    return plan
