# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Image pins are keyed per runtime (`<image>@<runtime>`), the follow-up the
GCP exploration asked for: the same logical image baked on AWS and GCE has
two parents, two builds and two pins, and an AMI id must never become a
GCE bake's parent. Legacy single-runtime pins keep working."""
from __future__ import annotations

import yaml

from tests.v2_support import V2Run

from cs_image_system.base import lineage
from cs_image_system.base.commands.upgrade import upgrade

AWS = "aws-east2-runtime"
GCE = "gcloud-east1"


def _build(build_id: str, series: str, runtime: str) -> dict:
    return {"build_id": build_id, "series": series, "runtime": runtime, "name": build_id,
            "parent": "vendor", "input_fingerprint": "f", "run": "run-1",
            "capabilities": {"identity_types": ["okta"], "storage_types": ["ebs"]}, "mods": [], "chain": []}


def test_pins_and_series_heads_are_per_runtime(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        ms = run.ctx.meta_state
        ms.add_build(_build("ami-1", "basic-rh-10", AWS))
        ms.add_build(_build("rhel8-gce-1", "basic-rh-10", GCE))
        assert (ms.series_head("basic-rh-10") or {})["build_id"] == "rhel8-gce-1"      # any runtime: latest
        assert (ms.series_head("basic-rh-10", AWS) or {})["build_id"] == "ami-1"
        assert (ms.series_head("basic-rh-10", GCE) or {})["build_id"] == "rhel8-gce-1"
        ms.bind_image("imgfile-basic-dask", "ami-1", "run-2", AWS)
        ms.bind_image("imgfile-basic-dask", "rhel8-gce-1", "run-2", GCE)
        assert ms.image_pin("imgfile-basic-dask", AWS) == "ami-1"
        assert ms.image_pin("imgfile-basic-dask", GCE) == "rhel8-gce-1"
        pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
        assert pins["images"] == {"imgfile-basic-dask@aws-east2-runtime": "ami-1",
                                  "imgfile-basic-dask@gcloud-east1": "rhel8-gce-1"}
        assert all(u["runtime"] for u in pins["upgrades"])
    finally:
        run.restore_cwd()


def test_legacy_pin_never_crosses_runtimes(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        ms = run.ctx.meta_state
        ms.add_build(_build("ami-1", "basic-rh-10", AWS))
        ms.bind_image("imgfile-basic-dask", "ami-1", "run-1")          # legacy, unkeyed
        assert ms.image_pin("imgfile-basic-dask") == "ami-1"
        assert ms.image_pin("imgfile-basic-dask", AWS) == "ami-1"      # lineage says AWS: honoured
        assert ms.image_pin("imgfile-basic-dask", GCE) is None         # an AMI is no GCE parent
        # a build lineage does not know is honoured for any runtime (pre-lineage data)
        ms.bind_image("imgfile-basic-cloudflow", "ami-unknown", "run-1")
        assert ms.image_pin("imgfile-basic-cloudflow", GCE) == "ami-unknown"
        # re-binding with a runtime supersedes the legacy key
        ms.bind_image("imgfile-basic-dask", "ami-1", "run-2", AWS)
        pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
        assert "imgfile-basic-dask" not in pins["images"] and pins["images"]["imgfile-basic-dask@aws-east2-runtime"] == "ami-1"
    finally:
        run.restore_cwd()


def test_pinned_parent_build_follows_the_bake_runtime(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        ctx = run.ctx
        ms = ctx.meta_state
        ms.add_build(_build("ami-1", "basic-rh-10", AWS))
        ms.add_build(_build("rhel8-gce-1", "basic-rh-10", GCE))
        image = ctx.images_map["imgfile-basic-dask"]
        assert lineage.primary_runtime_of(ctx, image) == AWS
        # first bind on each runtime picks THAT runtime's series head
        assert lineage.pinned_parent_build(ctx, image, GCE) == "rhel8-gce-1"
        assert lineage.pinned_parent_build(ctx, image) == "ami-1"        # primary runtime
        assert lineage.parent_reference(ctx, image, GCE) == "rhel8-gce-1"
        assert lineage.lineage_tags(ctx, image, GCE)["csis_parent"] == "rhel8-gce-1"
        assert lineage.lineage_tags(ctx, image, AWS)["csis_parent"] == "ami-1"
        assert lineage.input_fingerprint(ctx, image, AWS) != lineage.input_fingerprint(ctx, image, GCE)
    finally:
        run.restore_cwd()


def test_upgrade_image_moves_one_runtime_pin(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        ms = run.ctx.meta_state
        ms.add_build(_build("ami-1", "basic-rh-10", AWS))
        ms.add_build(_build("ami-2", "basic-rh-10", AWS))
        ms.add_build(_build("rhel8-gce-1", "basic-rh-10", GCE))
        ms.bind_image("imgfile-basic-dask", "ami-1", "run-1", AWS)
        # single-runtime image: --runtime optional, head is the AWS head
        previous, to = upgrade("image", "imgfile-basic-dask", runtime="aws-east2-runtime")
        assert (previous, to) == ("ami-1", "ami-2")
        assert ms.image_pin("imgfile-basic-dask", AWS) == "ami-2"
        # a build from another runtime is refused
        try:
            upgrade("image", "imgfile-basic-dask", to="rhel8-gce-1", runtime=AWS)
            assert False, "expected refusal"
        except ValueError as e:
            assert "baked on runtime" in str(e)
        # dask bakes on GCE too since GCP readiness, so a GCE upgrade of it
        # is legal; the config-level refusal still holds for an image that
        # stays AWS-only
        try:
            upgrade("image", "imgfile-data-science", runtime=GCE)
            assert False, "expected refusal"
        except ValueError as e:
            assert "not baked on runtime" in str(e)
        assert ms.image_pin("imgfile-basic-dask", AWS) == "ami-2"
    finally:
        run.restore_cwd()
