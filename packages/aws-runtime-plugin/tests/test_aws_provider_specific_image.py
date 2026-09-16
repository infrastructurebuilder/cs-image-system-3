# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the AWS provider-specific image query-asset shapes.

The deferred shape is the packer-ebs compatibility contract: it must match the
chained-image `data "amazon-ami"` filter shape the packer plugin emits.
"""
from typing import Any, cast

from cs_image_system.aws_runtime.aws_provider_specific_image import AwsProviderSpecificImage
from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
from cs_image_system.base.models.provider_specific_image import PSISourceKind


def test_csis_name():
    assert AwsProviderSpecificImage.csis_name() == "aws"


def test_cloud_builder_hook():
    assert AwsCloudBuilder.provider_specific_image_class(cast(Any, object())) is AwsProviderSpecificImage


def test_resolved_query_assets_shape():
    psi = AwsProviderSpecificImage.resolved(
        source_name="basic-rhel-9",
        source_kind=PSISourceKind.OS_BUILDER,
        runtime="aws",
        identifier="ami-0123456789abcdef0",
        owner="309956199498",
    )
    assert psi.get_query_assets() == {
        "filters": {"image-id": '"ami-0123456789abcdef0"'},
        "owners": ['"309956199498"'],
    }


def test_resolved_query_assets_without_owner():
    psi = AwsProviderSpecificImage.resolved(
        source_name="basic-rhel-9",
        source_kind=PSISourceKind.OS_BUILDER,
        runtime="aws",
        identifier="ami-0123456789abcdef0",
    )
    assert psi.get_query_assets() == {
        "filters": {"image-id": '"ami-0123456789abcdef0"'},
    }


def test_deferred_query_assets_shape_matches_packer_chained_image_contract():
    psi = AwsProviderSpecificImage.deferred(
        source_name="my-image",
        source_kind=PSISourceKind.IMAGE,
        runtime="aws",
        deferred_name_pattern="my-image-pckr-ebs-ans",
        architecture="arm64",
    )
    assert psi.get_query_assets() == {
        "owners": ['"self"'],
        "filters": {
            "name": '"my-image-pckr-ebs-ans*"',
            "root-device-type": '"ebs"',
            "virtualization-type": '"hvm"',
            "architecture": '"arm64"',
        },
        "most_recent": True,
    }


def test_deferred_query_assets_default_architecture():
    psi = AwsProviderSpecificImage.deferred(
        source_name="my-image",
        source_kind=PSISourceKind.IMAGE,
        runtime="aws",
        deferred_name_pattern="my-image-pckr-ebs-ans",
    )
    assets = psi.get_query_assets()
    assert assets is not None
    assert assets["filters"]["architecture"] == '"x86_64"'
