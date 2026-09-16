# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from abc import abstractmethod
from warnings import deprecated

from .. import utils
from pathlib import Path
from typing import Any, TypeVar

from cs_image_system.base import registry

from typing import TYPE_CHECKING

from ..models.image import Image
from ..models.image_builder_model import ImageBuilderModel
from ..models.base_image import BaseImage
if TYPE_CHECKING:
    from .builder_base_os import OsBuilderBase

from ..constants import DEFAULT, VCT
from ..lifecycle import ExecutionLifecyclePhase

from .builder_base import BuilderBase

TIMAGE = TypeVar("TIMAGE", bound=ImageBuilderModel)
class ImageBuilderBase(BuilderBase[TIMAGE]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Per-instance: class-level lists would be shared by every image
        # builder (and leak images across GlobalTypeContext rebuilds).
        self.local_items: list[Image] = []
        self.local_os_builder_items: list[BaseImage] = []

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.IMAGE_BUILDER

    
    @property
    def model(self) -> ImageBuilderModel:
        return self._model # type: ignore


    def get_block_directory_for_phase(self, phase: ExecutionLifecyclePhase, block: str = DEFAULT) -> Path:
        # PackerEbsImageBuilder makes a separate subdirectory for each block of images
        return self.get_builder_path() /  phase.value / block 

    def get_block_path_for_phase(self, phase: ExecutionLifecyclePhase, block: str = DEFAULT, discriminator: str | None = None, suffix: str | None = None) -> Path:
        name_for_phase = (
            f"{utils.safe_name(self.name)}-{phase.value}"
            f"{f'-{discriminator}' if discriminator else ''}"
            f"{f'-{block}' if block and block != DEFAULT else ''}"
            f"{suffix if suffix else ''}"
        )
        # PackerEbsImageBuilder makes a separate subdirectory for each block of images
        return self.get_block_directory_for_phase(phase, block) / name_for_phase


    def finalize(self) -> None:
        if self._finalized:
            return
        super().finalize()
        reg = registry.Registry()
        rt = self.model.get_runtime_provider()
        if not rt:
            raise ValueError(
                f"Image builder {self.name} does not specify a runtime provider."
            )
        ibrt = reg.get_builder_by_alias_or_name(classification=VCT.RUNTIME_BUILDER, name_or_alias = rt) # type: ignore
        if not ibrt:
            raise ValueError(
                f"Image builder {self.name} has runtime provider "
                f"{rt} which is not configured."
            )
        else:
            ibrt.add_image_builder(self)
        
    def add_image(self, image: Image | BaseImage, os_builder: OsBuilderBase | None = None) -> None:
        """Add an image to this image builder."""
        
        if image is not None:
            image.image_builder = self
            if isinstance(image, BaseImage):                
                self.local_os_builder_items.append(image)
            else:
                self.local_items.append(image)

    def build_target_label(self, image: Image | BaseImage) -> str:
        """The provisioner target naming one image inside this builder's
        build (packer: ``<source type>.<image>``, used in ``only = [..]``).
        Provider-neutral callers (OS update, mod builders, V2 provisioners)
        never spell a source type themselves."""
        raise NotImplementedError(f"{self.__class__.__name__} has no build target labels")

    def get_images(self, os_builder: bool = False) -> list[Image|BaseImage]:
        """Get the images associated with this image builder. A run's
        ``--only`` selection (scoped-runs, finding 23) filters here -- the
        single choke point every bake path flows through -- so sources,
        provisioners, build blocks and bake commands all scope together."""
        imgs = [i for i in (self.local_os_builder_items if os_builder else self.local_items) if i is not None]
        ctx = self._get_context()
        only = getattr(ctx, "only_images", None)
        rt = str(self.model.get_runtime_provider())
        if only is not None:  # an EMPTY selection (`--only none`) bakes nothing
            # entries are `<image>` (any runtime) or `<image>@<runtime>`
            # (that runtime's builders only -- a multi-cloud DAG bakes the
            # same name on several runtimes)
            imgs = [i for i in imgs
                    if i.get_name() in only or f"{i.get_name()}@{rt}" in only]
        # Convergent bakes (stage 9): an image whose series head was built
        # from the same inputs is current and leaves no bake surface at all.
        if hasattr(ctx, "meta_state"):
            from ..lineage import bake_reason
            imgs = [i for i in imgs if bake_reason(ctx, i, rt) is not None]
        return imgs


    @abstractmethod
    @deprecated("This method is deprecated and will be removed in a future version.")
    def ib_generated_path_name(self) -> Path:
        """
        Return the name of the subdirectory under the generation
        path where this image builder's files should be generated.

        This is an aspect of the image builder and the
        runtime provider

        """
        pass




LEGACY_SOURCE_TYPE = "amazon-ebs"


def build_target_label_of(image_builder: Any, image: Any) -> str:
    """``image_builder.build_target_label(image)`` when the builder can say;
    the legacy ``amazon-ebs.<image>`` when there is no builder (plugin unit
    tests pass ``None``) or it has no opinion."""
    label = getattr(image_builder, "build_target_label", None)
    if callable(label):
        try:
            return str(label(image))
        except NotImplementedError:
            pass
    name = getattr(image, "name", None) or image.get_name()
    return f"{LEGACY_SOURCE_TYPE}.{name}"
