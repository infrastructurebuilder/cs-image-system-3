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
fingerprint prefix) is re-tagged through the runtime's retag hook. One
tag is ADDED when absent: ``csis_config``, which says the image belongs to
this configuration (stage 82) -- every image baked before that stage lacks
it, and another configuration in the same account would call it foreign.
Since stage 93 the same id is what every storage and machine the system
makes carries, and relabel gives it to the ones that stand without it: a
declared storage whose cloud resource lacks the tag (through the storage
builder's ``retag_storage``) and a launched instance whose machine lacks it
(through the runtime's ``retag_instance``); a builder that cannot retag says
so and the thing stays as it is. No meta-state changes. Under the global
``--dry-run`` it only reports.
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
    build_id: str                           # the image's build id; a storage's or machine's cloud id (stage 93)
    series: str                             # the image series; the storage's or instance's declared name
    runtime: str
    tags: dict[str, str]                    # what the thing will carry (record truth)
    differences: list[str] = field(default_factory=list)
    retagged: bool | None = None            # None = dry run
    kind: str = "image"                     # image | storage | instance (stage 93)

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "build_id": self.build_id, "series": self.series, "runtime": self.runtime,
                "tags": dict(self.tags), "differences": list(self.differences), "retagged": self.retagged}


def record_tags(record: dict[str, Any]) -> dict[str, str]:
    """The lineage tags a record says its image must carry."""
    from ..lineage import FINGERPRINT_TAG_LENGTH, TAG_PREFIX
    from ..state_query import _TAGGED_FACTS
    tags = {f"{TAG_PREFIX}{fact}": str(record.get(fact) or "") for fact in _TAGGED_FACTS}
    tags[f"{TAG_PREFIX}fingerprint"] = str(record.get("input_fingerprint") or "")[:FINGERPRINT_TAG_LENGTH]
    return {k: v for k, v in tags.items() if v}


def relabel_plan(ctx: GlobalTypeContext, runtime: str, builds: list[str] | None = None) -> list[Relabel]:
    from ..lineage import CONFIG_TAG, TAG_PREFIX, configuration_tag
    ms = ctx.meta_state
    if runtime not in ctx.runtime_builders:
        raise ValueError(f"relabel: unknown runtime {runtime!r}; known: {sorted(ctx.runtime_builders)}")
    rtb = ctx.runtime_builders[runtime]
    recorded = [b for b in ms.builds() if str(b.get("runtime") or "") == runtime
                and (not builds or str(b.get("build_id")) in builds)]
    out: list[Relabel] = []
    real = {str(r.get("image_id")): r for r in
            rtb.query_images(sorted({str(b.get("series")) for b in recorded}))} if recorded else {}
    for b in recorded:
        bid = str(b.get("build_id"))
        image = real.get(bid)
        if image is None:
            log.warning(f"relabel: {bid} is not in {runtime}; nothing to relabel (state query reports it)")
            continue
        tags = image.get("tags") or {}
        wanted = record_tags(b)
        diffs = []
        # stage 82: a recorded image is this configuration's, and its tag must
        # say so -- the one tag relabel ADDS when absent, since every image
        # baked before the stage lacks it and another configuration in the
        # account would otherwise call it foreign
        owner = configuration_tag(ctx)
        if owner:
            wanted[CONFIG_TAG] = owner
            if tags.get(CONFIG_TAG) is None:
                diffs.append(f"config: tag absent, record's configuration is {owner}")
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
    if not builds:
        out += resource_relabel_plan(ctx, runtime)
    return out


def resource_relabel_plan(ctx: GlobalTypeContext, runtime: str) -> list[Relabel]:
    """Stage 93: the declared storages on ``runtime`` whose cloud resource
    stands without the configuration's id, and the launched instances there
    whose machine stands without it. Nothing else about them is compared:
    the id is the one thing they must carry and did not, before the stage."""
    from ..basic.builder_base_storage import StorageBuilderBase
    from ..lineage import CONFIG_TAG, configuration_tag, owner_of
    owner = configuration_tag(ctx)
    if not owner:
        return []
    out: list[Relabel] = []
    for name, sb in sorted(ctx.storage_builders.items()):
        if not isinstance(sb, StorageBuilderBase):
            continue
        model = getattr(sb, "model", None)
        try:
            on_runtime = str(model.get_runtime_provider()) == runtime if model is not None else False
        except ValueError:
            on_runtime = False
        if not on_runtime:
            continue
        try:
            real = sb.query_state()
        except NotImplementedError:
            continue
        for storage in list(getattr(model, "_storages", None) or []):
            rec = real.get(storage.get_name()) or {}
            if not rec.get("present") or owner_of(rec.get("tags")) == owner:
                continue
            if owner_of(rec.get("tags")):
                continue                                   # another configuration's: never ours to relabel
            out.append(Relabel(str(rec.get("id") or storage.get_name()), storage.get_name(), runtime,
                               {CONFIG_TAG: owner}, [f"config: tag absent on the {rec.get('type') or 'storage'} "
                                                      f"{rec.get('id') or ''}, this configuration is {owner}"],
                               kind="storage"))
    rtb = ctx.runtime_builders.get(runtime)
    launched = ctx.meta_state.launch_params()
    for inst in sorted(ctx.instances, key=lambda i: i.get_name()):
        if str(getattr(inst, "runtime", "") or "") != runtime or not (launched.get(inst.get_name()) or {}).get("launched"):
            continue
        try:
            tags = rtb.instance_tags(inst.get_name()) if rtb is not None else None
        except NotImplementedError:
            break
        except Exception as e:  # noqa: BLE001 - read-only probe
            log.warning(f"relabel: could not read the tags of {inst.get_name()}: {e}")
            continue
        if tags is None or owner_of(tags):
            continue                                       # absent, ours already, or another configuration's
        hostname = str((launched.get(inst.get_name()) or {}).get("hostname") or inst.get_name())
        out.append(Relabel(hostname, inst.get_name(), runtime, {CONFIG_TAG: owner},
                           [f"config: tag absent on the machine {hostname}, this configuration is {owner}"],
                           kind="instance"))
    return out


def _storage_builder_of(ctx: GlobalTypeContext, name: str):
    from ..basic.builder_base_storage import StorageBuilderBase
    for sb in ctx.storage_builders.values():
        if isinstance(sb, StorageBuilderBase):
            for storage in list(getattr(getattr(sb, "model", None), "_storages", None) or []):
                if storage.get_name() == name:
                    return sb, storage
    return None, None


def relabel(runtime: str, builds: list[str] | None = None) -> list[Relabel]:
    ctx = GlobalTypeContext()
    plan = relabel_plan(ctx, runtime, builds)
    if ctx.dry_run:
        for r in plan:
            log.info(f"relabel (dry run): {r.kind} {r.build_id} ({r.series}@{r.runtime}): {'; '.join(r.differences)}")
        return plan
    rtb = ctx.runtime_builders[runtime]
    for r in plan:
        try:
            if r.kind == "storage":
                sb, storage = _storage_builder_of(ctx, r.series)
                r.retagged = (bool(sb.retag_storage(storage, dict(r.tags)))
                              if sb is not None and storage is not None else False)
            elif r.kind == "instance":
                r.retagged = bool(rtb.retag_instance(r.series, dict(r.tags)))
            else:
                r.retagged = bool(rtb.retag_image(r.build_id, dict(r.tags)))
        except Exception as e:  # noqa: BLE001 - the record is right; the state query keeps showing the tag
            log.warning(f"relabel: could not retag {r.kind} {r.build_id}: {e}")
            r.retagged = False
        log.info(f"relabelled {r.kind} {r.build_id} ({r.series}@{r.runtime}): {'; '.join(r.differences)}; "
                 f"retagged={r.retagged}")
    return plan
