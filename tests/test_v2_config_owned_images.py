# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 82: an image says which configuration owns it.

Found walking the daily driver (stage 65, finding F11): a second
configuration repository in the reference account reported the reference
configuration's 36 AMIs as ``foreign``, because an image carried the
system's lineage tags and nothing that said whose lineage. Every bake now
tags ``csis_config=<the configuration's id>``; the state query and ``state
import`` leave another configuration's images alone; ``lineage relabel``
adds the tag to recorded images that lack it.
"""
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from tests.v2_support import V2Run, copy_config

OURS = "cs-image-action-test"          # the fixture's top-level id
AWS = "aws-east2-runtime"


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path), dry_run=False)
    try:
        yield r
    finally:
        r.restore_cwd()


def _image(image_id: str, series: str, config: str | None) -> dict[str, Any]:
    tags = {"csis_series": series, "csis_run": "2026_10_05t00_00_00_000000", "csis_parent": "vendor"}
    if config is not None:
        tags["csis_config"] = config
    return {"image_id": image_id, "name": image_id, "state": "available", "created": "", "tags": tags}


def test_the_tag_is_the_configuration_id_made_label_safe(run):
    from cs_image_system.base.lineage import CONFIG_TAG, configuration_tag, find_image, lineage_tags
    assert CONFIG_TAG == "csis_config"
    assert configuration_tag(run.ctx) == OURS
    odd = SimpleNamespace(_read_config=SimpleNamespace(id="  My Team.Images/2026!  "))
    assert configuration_tag(cast(Any, odd)) == "my-team-images-2026-"
    long = SimpleNamespace(_read_config=SimpleNamespace(id="x" * 80))
    assert len(configuration_tag(cast(Any, long))) == 63                    # a GCE label value's limit
    assert configuration_tag(cast(Any, SimpleNamespace())) == ""
    image = find_image(run.ctx, "basic-rh-10", AWS)
    assert lineage_tags(run.ctx, image, AWS)[CONFIG_TAG] == OURS


def test_every_generated_packer_source_carries_the_tag(run):
    assert run.run(["base-image", "instance-image"], apply=False).ok
    sources = list(run.generated.rglob("*source-*.pkr.hcl"))
    assert sources
    missing = [str(p.relative_to(run.generated)) for p in sources if "csis_config" not in p.read_text()]
    assert not missing, missing


def test_another_configurations_image_is_not_foreign_and_an_untagged_one_still_is(run, caplog):
    from cs_image_system.base import state_query as sq
    images = {AWS: [_image("ami-0theirs001", "team-node", "cs-image-system-walk"),
                    _image("ami-0theirs002", "el10", "cs-image-system-walk"),
                    _image("ami-0legacy001", "imgfile-old", None),          # baked before the stage
                    _image("ami-0ours00001", "imgfile-unrecorded", OURS)]}
    with caplog.at_level(logging.INFO):
        drift = sq.image_drift(run.ctx, images)
    foreign = sorted(d.name for d in drift if d.drift == sq.DRIFT_FOREIGN)
    assert foreign == ["ami-0legacy001", "ami-0ours00001"]
    assert any("2 image(s) on aws-east2-runtime belong to configuration 'cs-image-system-walk'" in r.getMessage()
               for r in caplog.records)


def test_state_import_never_adopts_another_configurations_image(run):
    from cs_image_system.base import state_query as sq
    report = sq.StateReport(run=run.ctx.run_id, reality={"images": {AWS: [
        _image("ami-0theirs001", "team-node", "cs-image-system-walk"),
        _image("ami-0legacy001", "imgfile-old", None)]}, "storages": {}})
    done = sq.import_foreign(run.ctx, report, storages=False)
    assert done == ["image ami-0legacy001 -> lineage series imgfile-old"]
    assert run.ctx.meta_state.build("ami-0theirs001") is None


def test_relabel_adds_the_tag_to_a_recorded_image_that_lacks_it(run, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.base.commands.relabel import relabel, relabel_plan
    run.ctx.meta_state.add_build({"build_id": "ami-0mine00001", "series": "basic-rh-10", "runtime": AWS,
                                  "parent": "vendor", "run": "2026_10_05t00_00_00_000000",
                                  "input_fingerprint": "", "mods": [], "chain": []})
    monkeypatch.setattr(AwsCloudBuilder, "query_images",
                        lambda self, series: [_image("ami-0mine00001", "basic-rh-10", None)])
    retagged: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(AwsCloudBuilder, "retag_image",
                        lambda self, image_id, tags: retagged.append((image_id, tags)) or True)
    plan = relabel_plan(run.ctx, AWS)
    assert [(r.build_id, r.differences) for r in plan] == [
        ("ami-0mine00001", [f"config: tag absent, record's configuration is {OURS}"])]
    assert relabel(AWS)[0].retagged is True
    assert retagged[-1][0] == "ami-0mine00001" and retagged[-1][1]["csis_config"] == OURS
    monkeypatch.setattr(AwsCloudBuilder, "query_images",
                        lambda self, series: [_image("ami-0mine00001", "basic-rh-10", OURS)])
    assert relabel_plan(run.ctx, AWS) == []                                  # tagged: nothing left to do
