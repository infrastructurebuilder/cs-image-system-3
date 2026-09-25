# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 63, the first chain (20 then 21): the zone check reads a storage's
BUILDER's runtime, and a persistent disk honours its own zone. Every test
here failed before its fix.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from tests.v2_support import copy_config, load_context, reset_singletons, stub_environment


def _runtimes(data: dict) -> list[dict]:
    for key in ("runtime_builders", "runtimes"):
        if key in data:
            return data[key]
    raise AssertionError(f"no runtime list in {sorted(data)}")


def _zoned_copy(tmp_path: Path, disk_zone: str) -> Path:
    """A fixture copy whose DEFAULT runtime (AWS) asserts us-east-2a and whose
    GCE disk declares ``disk_zone`` without naming a runtime on the item."""
    root = copy_config(tmp_path)
    rb = root / "cfg" / "runtime-builders.yml"
    data = yaml.safe_load(rb.read_text())
    default = next(r for r in _runtimes(data) if r.get("is_default"))
    assert default["name"] == "aws-east2-runtime"
    subnet = next(s for s in default["networking"]["subnets"] if s.get("is_default"))
    subnet["availability_zone"] = "us-east-2a"
    rb.write_text(yaml.safe_dump(data, sort_keys=False))
    st = root / "storages" / "gce.yaml"
    sdata = yaml.safe_load(st.read_text())
    disk = next(s for s in sdata["storages"] if s["name"] == "gce_data")
    assert "runtime" not in disk, "the item must not name its runtime"
    disk["availability_zone"] = disk_zone
    st.write_text(yaml.safe_dump(sdata, sort_keys=False))
    return root


def _zone_errors(root: Path, monkeypatch) -> list[str]:
    from cs_image_system.base.commands.validate import check_availability_zones
    stub_environment(monkeypatch)
    ctx = load_context(root)
    try:
        return [str(e) for e in check_availability_zones(ctx)]
    finally:
        reset_singletons()


# ------------------------------------------ 20. the zone check's runtime

def test_a_gce_disk_in_its_runtimes_zone_passes_without_naming_the_runtime(tmp_path: Path, monkeypatch):
    errors = _zone_errors(_zoned_copy(tmp_path, "us-east1-b"), monkeypatch)
    assert errors == [], errors


def test_a_gce_disk_outside_its_runtimes_zone_is_refused_against_that_runtime(tmp_path: Path, monkeypatch):
    errors = _zone_errors(_zoned_copy(tmp_path, "us-east1-c"), monkeypatch)
    storage = [e for e in errors if e.startswith("storage 'gce_data'")]
    assert storage and "runtime 'gcloud-east1' is in 'us-east1-b'" in storage[0], errors
    assert not any("us-east-2a" in e for e in storage), "compared with the AWS default runtime"
    # the instance that mounts it is in the runtime's zone: two zones, refused
    assert any(e.startswith("instance 'gce-test'") and "us-east1-c" in e and "us-east1-b" in e
               for e in errors), errors
