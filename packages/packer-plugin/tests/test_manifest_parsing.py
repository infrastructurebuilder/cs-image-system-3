# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins packer manifest parsing (image name -> AMI id)."""
import json

from cs_image_system.packer_plugin.packer_ebs_builder import parse_packer_manifest


def _write(tmp_path, data):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(data))
    return p


def test_parses_last_run_builds(tmp_path):
    p = _write(tmp_path, {
        "builds": [
            {"name": "imgfile-basic-dask", "builder_type": "amazon-ebs",
             "artifact_id": "us-east-2:ami-0aaa", "packer_run_uuid": "old"},
            {"name": "imgfile-basic-dask", "builder_type": "amazon-ebs",
             "artifact_id": "us-east-2:ami-0bbb", "packer_run_uuid": "new"},
            {"name": "imgfile-data-science", "builder_type": "amazon-ebs",
             "artifact_id": "us-east-2:ami-0ccc", "packer_run_uuid": "new"},
        ],
        "last_run_uuid": "new",
    })
    assert parse_packer_manifest(p) == {
        "imgfile-basic-dask": "ami-0bbb",
        "imgfile-data-science": "ami-0ccc",
    }


def test_missing_manifest_returns_empty(tmp_path):
    assert parse_packer_manifest(tmp_path / "nope.json") == {}


def test_malformed_manifest_returns_empty(tmp_path):
    p = tmp_path / "manifest.json"
    p.write_text("{not json")
    assert parse_packer_manifest(p) == {}


def test_artifact_without_region_prefix(tmp_path):
    p = _write(tmp_path, {
        "builds": [{"name": "img", "artifact_id": "ami-0ddd", "packer_run_uuid": "r"}],
        "last_run_uuid": "r",
    })
    assert parse_packer_manifest(p) == {"img": "ami-0ddd"}
