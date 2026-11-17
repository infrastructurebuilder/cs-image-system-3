# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The test-double runtime: a runtime type that exists only inside a test
run.

A configuration needs a runtime, and every real runtime belongs to a
provider. A fixture that declares a runtime of the type :data:`DOUBLE`
needs no provider at all: the core's own image builder bakes on it through
Packer's ``null`` source, so a whole stubbed run emits a base image and an
instance image with their modifications. It offers no instance, no storage
and no local stand-in, because only a provider has those.

The double is never an installed entry point, so it never appears among
the ``type:`` words of a real installation. :func:`stub` is a stub function
like a provider's: handed to the test kit's run, it adds the double to the
plugins the loader replays, for the length of the test that owns the
``monkeypatch``.

A fixture that uses it declares an image source for it, since no catalog
ships one::

    image_sources:
      - family: alma-linux
        is: rhel
        sources:
          test-double:
            publisher: ["nobody"]
            name: test-double-base
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.basic.builder_base_container import ContainerBuilderBase
from cs_image_system.base.models.container_builder import ContainerBuilderModel
from cs_image_system.base.models.provider_specific_image import ProviderSpecificImage
from cs_image_system.contract.constants import DEFAULT, VCT
from cs_image_system.contract.core import PluginArtifactProtocol
from cs_image_system.contract.fields import fk_field
from cs_image_system.contract.image import ImageQuery
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.engine import loader

#: the ``type:`` word of the double, and the key of its image-source block
DOUBLE = "test-double"
#: the namespace its registrations carry
NAMESPACE = "testing"
#: the Packer source it bakes with: the builtin that connects to nothing
NULL_SOURCE = "null"
#: what its image query answers, whatever is asked
BASE_IMAGE = "test-double-base"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DoubleRuntimeModel(ContainerBuilderModel):
    """The double's declaration: the container runtime's fields and the
    state backend its roots would use."""
    type = DOUBLE
    state_configuration: str = fk_field(target=VCT.STATE_BACKEND_MODEL,
                                        default=DEFAULT,
                                        metadata={
                                            "description": "The state manager this runtime's roots use",
                                            "required": True,
                                        })

    @classmethod
    def csis_name(cls) -> str:
        return DOUBLE


class DoubleImage(ProviderSpecificImage):
    """An image as the double knows it: a name."""

    @classmethod
    def csis_name(cls) -> str:
        return DOUBLE

    def get_query_assets(self) -> dict[str, Any] | None:
        return {"image": str(self.identifier)} if self.is_resolved() else None


class DoubleRuntimeBuilder(ContainerBuilderBase[DoubleRuntimeModel], PluginArtifactProtocol):
    """The double's builder. Every question a run asks of a runtime is
    answered from inside the process."""

    @classmethod
    def csis_name(cls) -> str:
        return DOUBLE

    @property
    def model(self) -> DoubleRuntimeModel:
        return self._model

    def provider_specific_image_class(self) -> type[ProviderSpecificImage]:
        return DoubleImage

    def supported_query_keys(self) -> frozenset[str]:
        return frozenset({"name", "publisher"})

    def translate_image_query(self, query: ImageQuery) -> dict[str, Any]:
        return {"name": query.name, "publisher": list(query.publisher or [])}

    def query_provider_image(self, os_builder: Any) -> tuple[str, str, Mapping[str, Any]] | None:
        return BASE_IMAGE, "nobody", {}

    def query_images(self, series: list[str]) -> list[dict[str, Any]]:
        return []

    def default_bake_user(self, family: str) -> str | None:
        return "root"

    def packer_source_type(self) -> str:
        return NULL_SOURCE

    def packer_source_blocks(self, image: Any, *, runtime: str, source_type: str, subconfig: Any,
                             self_subconfig: Any, psi: Any, tags: dict[str, str],
                             final_name: str, pinned: str | None) -> list[str]:
        return [f'source "{source_type}" "{image.get_name()}" {{', '  communicator = "none"', "}"]


class DoubleMetadata(AbstractPluginMetadata):
    """What the double registers: its model and its builder."""

    def __init__(self) -> None:
        super().__init__("1", "3.13", {DOUBLE: [DoubleRuntimeModel, DoubleRuntimeBuilder]},
                         {DoubleRuntimeModel: DoubleRuntimeBuilder}, _namespace=NAMESPACE)


def stub(monkeypatch: Any) -> None:
    """Add the double to the plugins every registry is loaded with, for the
    length of the test that owns ``monkeypatch``."""
    discovered = loader._discovered_plugins

    def with_the_double() -> tuple[loader.DiscoveredPlugin, ...]:
        return (*discovered(), loader.DiscoveredPlugin("runtime", DOUBLE, None, DoubleMetadata))

    monkeypatch.setattr(loader, "_discovered_plugins", with_the_double)
