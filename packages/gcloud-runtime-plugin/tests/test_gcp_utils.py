# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the GCP-native image query utilities (no network access)."""
from typing import Any, cast

import pytest
from google.cloud import compute_v1

from cs_image_system.gcloud_runtime import gcp_utils
from cs_image_system.gcloud_runtime.gcp_utils import (
    build_filter_expression,
    get_image_owner,
    query_image,
    remap_for_image_query,
    resolve_projects,
)


class FakeSubconfig:
    """Duck-typed stand-in for OSBuilderBaseImageBuilderSubconfig."""

    def __init__(self, owners: list[str], query: dict[str, Any]):
        self._owners = owners
        self._query = query

    def get_owners(self) -> list[str]:
        return self._owners

    def get_query(self) -> dict[str, Any]:
        return self._query


class FakeImagesClient:
    """Fake compute_v1.ImagesClient returning canned images from list()."""

    def __init__(self, images: list[compute_v1.Image]):
        self._images = images
        self.requests: list[Any] = []

    def list(self, request: Any) -> list[compute_v1.Image]:
        self.requests.append(request)
        return self._images


SESSION = {"project": "my-project"}


def _img(name: str, ts: str, **kw: Any) -> compute_v1.Image:
    return compute_v1.Image(name=name, creation_timestamp=ts, **kw)


def test_remap_translates_aws_shaped_query_to_gcp_filter():
    rc = FakeSubconfig(
        owners=["self", "amazon"],
        query={
            "filters": {
                "name": "RHEL-9.5*x86_64*",
                "root_device_type": "ebs",           # AWS-only: dropped
                "virtualization_type": "hvm",        # AWS-only: dropped
                "architecture": "x86_64",
                "state": "available",
            }
        },
    )
    q, missed = remap_for_image_query(cast(Any, rc))
    assert q["projects"] == ["self", "amazon"]
    assert '(name = "RHEL-9.5*x86_64*")' in q["filter"]
    assert '(status = "READY")' in q["filter"]
    assert '(architecture = "X86_64")' in q["filter"]
    assert "root_device_type" not in q["filter"]
    assert "virtualization" not in q["filter"]
    # AWS-only keys must not leak into the post-query filter either
    assert missed == {}


def test_remap_defaults_status_ready_and_maps_tags_to_labels():
    rc = FakeSubconfig(owners=[], query={"filters": {"tag:Environment": "prod"}})
    q, _ = remap_for_image_query(cast(Any, rc))
    assert '(labels.Environment = "prod")' in q["filter"]
    assert '(status = "READY")' in q["filter"]


def test_remap_unknown_keys_go_to_missed():
    rc = FakeSubconfig(owners=[], query={"filters": {"totally_custom": "x"}})
    _, missed = remap_for_image_query(cast(Any, rc))
    assert missed == {"totally_custom": "x"}


def test_build_filter_expression_quotes_strings_and_lowers_bools():
    expr = build_filter_expression({"name": "deb-11*", "auto": True})
    assert expr == '(name = "deb-11*") AND (auto = true)'


def test_resolve_projects_maps_self_aliases_and_drops_invalid():
    projects = resolve_projects(
        ["self", "amazon", "debian", "136693071363", "rhel-cloud"], SESSION
    )
    assert projects == ["my-project", "debian-cloud", "rhel-cloud"]


def test_resolve_projects_self_requires_project():
    with pytest.raises(ValueError):
        resolve_projects(["self"], {})


def test_query_image_returns_most_recent(caplog):
    fake = FakeImagesClient(
        [
            _img("old", "2024-01-01T00:00:00Z"),
            _img("new", "2026-01-01T00:00:00Z"),
            _img("mid", "2025-01-01T00:00:00Z"),
        ]
    )
    result = query_image(
        query={"projects": ["self"], "filter": '(status = "READY")'},
        session_config=dict(SESSION),
        images_client=fake,
    )
    assert result is not None
    assert result["name"] == "new"
    assert result["project"] == "my-project"


def test_query_image_applies_post_query_filter():
    fake = FakeImagesClient(
        [
            _img("a", "2026-01-01T00:00:00Z", family="other"),
            _img("b", "2024-01-01T00:00:00Z", family="wanted"),
        ]
    )
    result = query_image(
        query={"projects": ["self"], "filter": '(status = "READY")'},
        post_query_filter={"family": "wanted"},
        session_config=dict(SESSION),
        images_client=fake,
    )
    assert result is not None
    assert result["name"] == "b"


def test_query_image_returns_none_when_no_match():
    fake = FakeImagesClient([])
    result = query_image(
        query={"projects": ["self"], "filter": '(name = "nope")'},
        session_config=dict(SESSION),
        images_client=fake,
    )
    assert result is None


def test_query_image_rejects_empty_inputs():
    with pytest.raises(ValueError):
        query_image(query={}, session_config=dict(SESSION))
    with pytest.raises(ValueError):
        query_image(query={"filter": "x"}, session_config=None)


def test_get_image_owner_prefers_project_then_self_link():
    assert get_image_owner({"project": "debian-cloud"}) == {"project": "debian-cloud"}
    assert get_image_owner(
        {"self_link": "https://www.googleapis.com/compute/v1/projects/rhel-cloud/global/images/rhel-9-v1"}
    ) == {"project": "rhel-cloud"}
    assert get_image_owner({}) is None


def test_generic_architecture_roundtrip():
    assert gcp_utils._generic_architecture("X86_64") == "x86_64"
    assert gcp_utils._generic_architecture("ARM64") == "arm64"
    assert gcp_utils._generic_architecture("ARCHITECTURE_UNSPECIFIED") == "x86_64"
