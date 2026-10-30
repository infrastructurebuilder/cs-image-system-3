# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the GCP-native image query utilities (no network access)."""
from typing import Any

import pytest
from google.cloud import compute_v1

from cs_image_system.gcloud_runtime import gcp_utils
from cs_image_system.gcloud_runtime.gcp_utils import (
    build_filter_expression,
    get_image_owner,
    query_image,
    resolve_projects,
    translate_image_query,
)
from cs_image_system.contract.image import ImageQuery


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


def test_translate_puts_the_systems_query_in_compute_engines_words():
    # stage 106: the vocabulary is the system's; the values are mapped
    q = translate_image_query(ImageQuery.from_mapping({
        "publisher": ["self", "rhel-cloud"], "name": "rhel-9-v*", "architecture": "x86_64", "state": "available"}))
    assert q["projects"] == ["self", "rhel-cloud"]
    assert q["terms"] == {"name": "rhel-9-v*", "architecture": "X86_64", "status": "READY"}
    assert '(name = "rhel-9-v*")' in q["filter"] and '(status = "READY")' in q["filter"]
    assert '(architecture = "X86_64")' in q["filter"] and q["most_recent"] is True


def test_translate_defaults_status_ready_maps_tags_to_labels_and_passes_native():
    q = translate_image_query(ImageQuery.from_mapping({"tag:Environment": "prod", "family": "debian-12",
                                                       "native": {"deprecated.state": "ACTIVE"}}))
    assert q["terms"] == {"family": "debian-12", "status": "READY", "labels.Environment": "prod",
                          "deprecated.state": "ACTIVE"}


def test_translate_refuses_the_ec2_particulars_by_name():
    # the keys GCE used to drop with a debug line are refused, named (validate refuses them first)
    with pytest.raises(ValueError, match="root_device, virtualization"):
        translate_image_query(ImageQuery.from_mapping({"filters": {"root_device_type": "ebs", "virtualization_type": "hvm"}}))


def test_an_unknown_key_is_refused_by_the_vocabulary_not_buried():
    with pytest.raises(ValueError, match="totally_custom"):
        ImageQuery.from_mapping({"filters": {"totally_custom": "x"}})


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
