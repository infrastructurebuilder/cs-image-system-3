# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ProviderSpecificImage model and its registry/runtime wiring."""
from typing import Any

import pytest

from cs_image_system.base import registry as _registry
from cs_image_system.base.constants import VCT
from cs_image_system.base.models.provider_specific_image import (
    GenericProviderSpecificImage,
    ProviderSpecificImage,
    PSISourceKind,
    PSIState,
    psi_key,
)
from cs_image_system.base.protocols.name_typed_protocol import NameTypedProtocol


def make_resolved(**overrides: Any) -> ProviderSpecificImage:
    kwargs: dict[str, Any] = dict(
        source_name="basic-rhel-9",
        source_kind=PSISourceKind.OS_BUILDER,
        runtime="aws-runtime",
        identifier="ami-0123456789abcdef0",
        owner="amazon",
        raw_query_result={"ImageId": "ami-0123456789abcdef0"},
    )
    kwargs.update(overrides)
    return GenericProviderSpecificImage.resolved(**kwargs)


def make_deferred(**overrides: Any) -> ProviderSpecificImage:
    kwargs: dict[str, Any] = dict(
        source_name="my-image",
        source_kind=PSISourceKind.IMAGE,
        runtime="aws-runtime",
        deferred_name_pattern="my-image-pckr-ebs-ans",
        architecture="arm64",
    )
    kwargs.update(overrides)
    return GenericProviderSpecificImage.deferred(**kwargs)


class TestFactoriesAndValidation:
    def test_resolved_factory(self):
        psi = make_resolved()
        assert psi.state == PSIState.RESOLVED
        assert psi.is_resolved()
        assert psi.identifier == "ami-0123456789abcdef0"
        assert psi.owner == "amazon"
        assert psi.source_kind == PSISourceKind.OS_BUILDER

    def test_deferred_factory(self):
        psi = make_deferred()
        assert psi.state == PSIState.DEFERRED
        assert not psi.is_resolved()
        assert psi.identifier is None
        assert psi.deferred_name_pattern == "my-image-pckr-ebs-ans"

    def test_resolved_requires_identifier(self):
        with pytest.raises(ValueError, match="requires an identifier"):
            GenericProviderSpecificImage(
                source_name="x",
                source_kind=PSISourceKind.OS_BUILDER,
                runtime="rt",
                state=PSIState.RESOLVED,
            )

    def test_deferred_requires_name_pattern(self):
        with pytest.raises(ValueError, match="requires a deferred_name_pattern"):
            GenericProviderSpecificImage(
                source_name="x",
                source_kind=PSISourceKind.IMAGE,
                runtime="rt",
                state=PSIState.DEFERRED,
            )

    def test_psi_key(self):
        assert psi_key("img", "rt") == "img::rt"


class TestNameTypedSurface:
    def test_conforms_to_name_typed_protocol(self):
        assert isinstance(make_resolved(), NameTypedProtocol)

    def test_name_and_classification(self):
        psi = make_resolved()
        assert psi.get_name() == psi_key("basic-rhel-9", "aws-runtime")
        assert psi.get_classification() == VCT.PROVIDER_SPECIFIC_IMAGE
        assert psi.get_aliases() == set()
        assert psi.get_is_default() is False
        assert psi.get_name() in psi.global_id


class TestRegistryRoundTrip:
    def test_register_and_lookup(self, clean_registry):
        reg = _registry.Registry()
        psi = make_resolved()
        reg.register_built_instance(psi)
        got = reg.get_instance_by_name_or_alias(
            VCT.PROVIDER_SPECIFIC_IMAGE, psi_key("basic-rhel-9", "aws-runtime")
        )
        assert got is psi

    def test_reregistration_overwrites(self, clean_registry):
        reg = _registry.Registry()
        first = make_resolved()
        second = make_resolved(identifier="ami-fedcba9876543210f")
        reg.register_built_instance(first)
        reg.register_built_instance(second)
        got = reg.get_instance_by_name_or_alias(
            VCT.PROVIDER_SPECIFIC_IMAGE, first.get_name()
        )
        assert got is second


class TestGenericQueryAssets:
    def test_resolved_query_assets(self):
        assets = make_resolved().get_query_assets()
        assert assets == {
            "filters": {"image-id": '"ami-0123456789abcdef0"'},
            "owners": ['"amazon"'],
        }

    def test_deferred_query_assets(self):
        assets = make_deferred().get_query_assets()
        assert assets == {
            "owners": ['"self"'],
            "filters": {"name": '"my-image-pckr-ebs-ans*"'},
            "most_recent": True,
        }


class TestRuntimeBuilderCreation:
    @pytest.fixture
    def stub_rtb(self):
        from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase

        class Stub:
            provider_specific_image_class = RuntimeBuilderBase.provider_specific_image_class
            create_provider_specific_image_resolved = (
                RuntimeBuilderBase.create_provider_specific_image_resolved
            )
            create_provider_specific_image_deferred = (
                RuntimeBuilderBase.create_provider_specific_image_deferred
            )

            def get_name(self):
                return "stub-runtime"

        return Stub()

    def test_create_resolved_registers(self, clean_registry, stub_rtb):
        reg = _registry.Registry()
        psi = stub_rtb.create_provider_specific_image_resolved(
            source_name="some-os",
            source_kind=PSISourceKind.OS_BUILDER,
            identifier="ami-123",
            owner="amazon",
            raw_query_result={"ImageId": "ami-123"},
        )
        assert isinstance(psi, GenericProviderSpecificImage)
        assert psi.runtime == "stub-runtime"
        assert (
            reg.get_instance_by_name_or_alias(
                VCT.PROVIDER_SPECIFIC_IMAGE, psi_key("some-os", "stub-runtime")
            )
            is psi
        )

    def test_create_deferred_registers(self, clean_registry, stub_rtb):
        class StubSubconfig:
            def get_image_output_name(self):
                return "my-image-pckr-ebs-ans"

        class StubImage:
            architecture = "x86_64"

            def get_name(self):
                return "my-image"

        reg = _registry.Registry()
        psi = stub_rtb.create_provider_specific_image_deferred(
            image=StubImage(), subconfig=StubSubconfig()
        )
        assert psi.state == PSIState.DEFERRED
        assert psi.deferred_name_pattern == "my-image-pckr-ebs-ans"
        assert psi.architecture == "x86_64"
        assert (
            reg.get_instance_by_name_or_alias(
                VCT.PROVIDER_SPECIFIC_IMAGE, psi_key("my-image", "stub-runtime")
            )
            is psi
        )
