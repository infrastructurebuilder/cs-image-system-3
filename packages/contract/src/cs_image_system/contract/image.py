# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The image kind (stage 30): the builder that bakes base images and
instance images (packer, in the built-in plugin), and the two enums a
provider-specific image carries. The image items themselves (``Image``,
``BaseImage``) are the core's models and ``Any`` here."""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from .constants import DEFAULT
from .core import BuilderProtocol, RuntimeEnabledBuilderModelProtocol
from .lifecycle import ExecutionLifecyclePhase


class PSIState(StrEnum):
    """State of a ProviderSpecificImage."""
    RESOLVED = "resolved"  # A concrete provider identifier is known (e.g. an AMI id)
    DEFERRED = "deferred"  # The image does not exist yet; only a query/name pattern is known


class PSISourceKind(StrEnum):
    """What kind of source a ProviderSpecificImage was generated from."""
    IMAGE = "image"          # A user-declared Image
    OS_BUILDER = "os_builder"  # An OsBuilder vendor-image lookup


def psi_key(source_name: str, runtime: str) -> str:
    """Registry key for a ProviderSpecificImage.

    "::" cannot appear in validated item names, so the key is unambiguous.
    """
    return f"{source_name}::{runtime}"


class ImageBuilderModelProtocol(RuntimeEnabledBuilderModelProtocol, Protocol):
    """An entry under ``image_builders:``."""

    default_machine_type: str

    def get_default_machine_type(self) -> str: ...


class ImageBuilderProtocol(BuilderProtocol, Protocol):
    """An image builder: it collects the images declared on it and files
    each build block's output under a path per phase."""

    def get_block_directory_for_phase(self, phase: ExecutionLifecyclePhase, block: str = DEFAULT) -> Path: ...

    def get_block_path_for_phase(self, phase: ExecutionLifecyclePhase, block: str = DEFAULT,
                                 discriminator: str | None = None, suffix: str | None = None) -> Path: ...

    def add_image(self, image: Any, os_builder: Any = None) -> None: ...

    def build_target_label(self, image: Any) -> str: ...

    def get_images(self, os_builder: bool = False) -> list[Any]: ...
