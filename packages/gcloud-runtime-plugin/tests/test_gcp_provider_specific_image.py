# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the GCP provider-specific image query-asset shapes."""
from typing import Any, cast

from cs_image_system.base.models.provider_specific_image import PSISourceKind
from cs_image_system.gcloud_runtime.gcp_provider_specific_image import GcpProviderSpecificImage
from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder


def test_csis_name():
    assert GcpProviderSpecificImage.csis_name() == "gcloud"


def test_cloud_builder_hook():
    assert GCPCloudBuilder.provider_specific_image_class(cast(Any, object())) is GcpProviderSpecificImage


def test_resolved_query_assets_shape():
    psi = GcpProviderSpecificImage.resolved(
        source_name="basic-deb-11",
        source_kind=PSISourceKind.OS_BUILDER,
        runtime="gcloud",
        identifier="debian-11-bullseye-v20260101",
        owner="debian-cloud",
    )
    assert psi.get_query_assets() == {
        "filters": {"name": '"debian-11-bullseye-v20260101"'},
        "owners": ['"debian-cloud"'],
    }


def test_deferred_query_assets_shape():
    psi = GcpProviderSpecificImage.deferred(
        source_name="my-image",
        source_kind=PSISourceKind.IMAGE,
        runtime="gcloud",
        deferred_name_pattern="my-image-gcp-builder",
    )
    assert psi.get_query_assets() == {
        "owners": ['"self"'],
        "filters": {"name": '"my-image-gcp-builder*"'},
        "most_recent": True,
    }
