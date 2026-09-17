# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
from dataclasses import field
from .model_config import CSIS_MODEL_CONFIG
from pydantic import Field
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
import logging
log = logging.getLogger(__name__)
from typing import Annotated, Any
from ..constants import DEFAULT, SELF,  VCT

from ..helpers.field_helpers import fk_field, templated_field
from ..registry import Registry
from .builder_model import NameTyped
from .root_item import RootItem

from ..protocols.name_typed_protocol import SelfInjectedNameProtocol
from ..protocols.parent_property_holding_protocol import ParentPropertyHoldingProtocol
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..basic.builder_base_image import ImageBuilderBase
    from ..basic.builder_base_os import OsBuilderBase

@dataclass(config=CSIS_MODEL_CONFIG)
class BaseImageImageBuilderSubconfig(NameTyped, ParentPropertyHoldingProtocol):
    """Configuration for a specific runtime for an image."""
    # type is (effectively) ignored for this object
    #. self.runtime serves as the 'type' for ImageRuntimeSubconfig
    #. but we must set it to override the parent
    name: str = DEFAULT
    # stage 48.3: a type TAG, not a reference -- it carried the runtime's name under
    # an OS-builder foreign key and resolved only through the fallback
    type_: Annotated[str, Field(alias="type")] = DEFAULT
    runtime: str = fk_field(target=VCT.RUNTIME_BUILDER_MODEL, # FIXME: This should be image builder
                            default = DEFAULT,
                            metadata={
                                "description": "The runtime this config uses",
                                "required": True,
    })
    image_builder: str = fk_field(target=VCT.IMAGE_BUILDER_MODEL,
                                  default=DEFAULT, metadata={
                                      "description": "The image builder this config uses",
                                      "required": True,
                                  })
    ssh_username: str  = DEFAULT
    # Per-runtime in-bake tests: when set, REPLACES the builder-level tests
    # for bakes on this runtime (finding 40). None inherits them.
    tests: dict | None = None
    auto_update: bool = False # apply the OS-provided package update during the base-image build
    image_identifier: str | None = None # A fallback string id
    # Double braces for an f-string inside a template string.  This will be replaced with the default machine type for this runtime from the builder, if it exists, otherwise it will be set to DEFAULT.
    machine_type: str  | None = templated_field(replace_value =f"{{{{ runtime.get_default_machine_type() if runtime  else '{DEFAULT}' }}}}" ,
                                                default = None,
                                                metadata={
                    "description": "The machine type to use for this runtime.",
    })

    _model_id: str | None = fk_field(target = VCT.IMAGE_BUILDER_MODEL,
                                     also_set_on_update= "model_id",
                                     init=False, default=None, metadata={
        "description": "The name of the model this property holding object is associated with",
    })
    tags: dict[str, str] = field(default_factory=dict)

    owners: list[str] = field(default_factory=list)

    _final_name: str  = templated_field(replace_value ="{{ this.get_image_output_name() }}-{{ execution.timestamp }}" ,
                                                default = None,
                                                metadata={
                    "description": "The machine type to use for this runtime.",
    })

    def __post_init__(self):
        self._image: BaseImage|None = None
        if self.runtime == DEFAULT:
            pass
        if self.type_ and self.type_ != DEFAULT:
            log.warning(f"ImageRuntimeSubconfig {self.name} has a 'type' field that is set to {self.type_} "
                        "and will be overridden with the runtime value in finalize.")
        self.type_ = self.runtime # There maybe needs to be a type specified
        self.name = self.runtime if self.name == DEFAULT else self.name
        if not self.tags:
            self.tags = {}
        if not self.owners:
            self.owners = [SELF]

        super().__post_init__()
    def finalize(self) -> None:
        if self._finalized:
            return
        super().finalize()
        if not self.runtime:
            raise ValueError(f"Runtime configuration for image {self.model_id} must have a runtime specified.")
        if self.name is None or self.name == DEFAULT:
            self.name = self.runtime

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.IMAGE_IMAGE_BUILDER_SUBCONFIG_MODEL

    def get_owners(self) -> list[str]:
        return self.owners
    def get_image_output_name(self) -> str:
        # FIXME
        # Use the display name (original case) for the user-facing image name; the
        # normalized .name is still used only to test presence.
        ret = f"{self._image.get_display_name()}-{self.runtime}" if self._image and self._image.name else f"{self.model_id}-{self.runtime}"
        return ret
    def get_final_name(self) -> str:
        return self._final_name
    def get_name(self) -> str:
        return self.runtime
    def get_ssh_username(self) -> str | None:
        return self.ssh_username
    def get_auto_update(self) -> bool:
        return bool(self.auto_update)
    def get_type(self) -> str:
        return self.runtime
    def get_description(self) -> str | None:
        return f"Runtime-specific configuration for runtime {self.runtime} for image {self.model_id}"
    def get_aliases(self) -> set[str]:
        return set()
    def get_classification(self) -> VCT:
        return self.csis_classifier()
    def get_runtime(self) -> str:
        return self.runtime
    def get_image_builder(self) -> str:
        return self.image_builder
    def get_os_builder(self) -> str | None:
        # This works unless you mess with the model
        ret = None
        im = self.get_image()
        ret = im.os if im else None
        return ret
    def get_image(self) -> BaseImage | None:
        return self._image
    def get_machine_type(self) -> str | None:
        return self.machine_type
    def get_tags(self) -> dict[str, str] | None:
        _tags: dict[str, str] = {}
        reg =  Registry()
        image_build:ImageBuilderBase = reg.get_instance_by_name_or_alias(VCT.IMAGE_BUILDER_MODEL, self.image_builder) if self.image_builder else None # type: ignore
        if image_build:
            _tags.update(image_build.get_tags() or {})

        image = self.get_image()
        if image:
            _tags.update(image.get_tags() or {})
        _tags.update(self.tags or {})
        return _tags

@dataclass(config=CSIS_MODEL_CONFIG)
class BaseImage(RootItem,SelfInjectedNameProtocol):
    """An image with its metadata."""
    type_: Annotated[str, Field(alias="type")] = fk_field(target = VCT.IMAGE_BUILDER_MODEL,
                         default=DEFAULT,
                         metadata={
                            "description": "image builder to use for this image",
                            "required": True,
                        })
    os: str | None= fk_field(target = VCT.OS_BUILDER_MODEL,
                             default=DEFAULT,
                             metadata={
                                "description": " OS builder",
                                "required": True,
                            })
    # source image is either SELF, as a base image, some some other Image that eventually is source_image == SELF
    source_image: str| None  = None
    auto_update: bool | None = None
    is_default: bool = False
    # architecture: str = templated_field( replace_value=("{{ builder.get_architecture() if builder "
    #                                                     f"and builder.get_architecture() != {DEFAULT} else 'x86_64' "
    #                                                     "}}"),
    #                                     default=DEFAULT)
    primary_disk_size: str | int = templated_field( replace_value=("{{ builder.get_default_primary_disk_size() "
                                                                   f"if builder and builder.get_default_primary_disk_size() != {DEFAULT} "
                                                                   "else 200 "
                                                                   "}}"),
                                                   default=DEFAULT)
    variables: dict[str, Any] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    runtimes: list[BaseImageImageBuilderSubconfig] = field(default_factory=list)
    description: str | None = None
    # V2 capability declaration (§3F1) and the mandatory admin user (N9/N12),
    # carried over from the OS builder that synthesizes this base image; the
    # declared capabilities are stamped into each build's lineage (N11).
    identity_types: list[str] = field(default_factory=list)
    storage_types: list[str] = field(default_factory=list)
    admin_user: str = "csisadmin"
    admin_public_keys: list[str] | None = None
    tests: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def klazz_yaml_key(cls) -> str:
        """Get the YAML key for this class, which is typically the lowercase class name."""
        return "base_images"

    def capabilities(self) -> dict[str, list[str]]:
        return {"identity_types": sorted(self.identity_types or []),
                "storage_types": sorted(self.storage_types or [])}

    def __post_init__(self):
        super().__post_init__()
        reg = Registry()
        self._is_base = False
        # self._final_name:str = None # type: ignore
        self._dependencies: set[str] = set()
        self._osbuilder: OsBuilderBase = None # type: ignore
        self._image_builder: ImageBuilderBase|None = None
        if not self.runtimes:
            log.info(f"Image {self.name} has no runtimes specified. Setting to default.")
            raise ValueError(f"Image {self.name} must have at least one runtime specified in the "
                             "'runtimes' field. Please specify at least one runtime configuration.")
        self._runtime_map: dict[str, BaseImageImageBuilderSubconfig] = {}
        for r in self.runtimes:
            r.model_id = self.global_id
            self._runtime_map[r.runtime] = r
            r._image = self
        if self.os and self.source_image:
            if self.os == DEFAULT:
                self.os = None
            else:
                err = f"Image {self.name} has both 'os' and 'source_image' specified. Pick one or the other but not both."
                log.error(err)
                raise ValueError(err)
        if self.os:
            log.debug(f"Image {self.name} has OS {self.os} specified")
            self.source_image = None # type: ignore
        elif self.source_image:
            log.debug(f"Image {self.name} has source image {self.source_image} specified, ignoring 'os' if it exists.")
            self.os = None
        else:
            err = f"Image {self.name} must have either 'os' or 'source_image' specified. Please specify one of these fields."
            log.error(err)
            raise ValueError(err)
        if self.description is None:
            if self.os:
                self.description = f"Image {self.name} with OS {self.os}"
            elif self.source_image:
                 self.description = (
                     f"Image {self.name} from source image {self.source_image}"
                 )

        self._image_identifiers_for_runtimes: dict[str, str] = {}
    def finalize(self) -> None:
        if self._finalized:
            return
        super().finalize()
        if self.os:
            log.debug(f"Finalizing image {self.name} with OS {self.os}")
            __osb = self._reg.get_instance_by_name_or_alias( VCT.OS_BUILDER_MODEL, self.os)
            if not __osb:
                log.error(f"OS builder {self.os} specified for image {self.name} not found in registry.")
                raise ValueError(f"OS builder {self.os} specified for image {self.name} not found in registry.")
            self._osbuilder = __osb

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.BASE_IMAGE_MODEL

    def get_classification(self) -> VCT:
        return self.csis_classifier()

    @property
    def image_builder(self) -> ImageBuilderBase|None:
        """Get the image builder for this image."""
        if not self._image_builder:
            if self.source_image:
                log.debug(f"Image {self.name} has source image {self.source_image} specified, using this to determine image builder.")
                reg = Registry()
                inst = reg.get_all_instances_by_classification(VCT.BASE_IMAGE_MODEL)
                if self.source_image in inst:
                    source_image = inst[self.source_image]
                    if source_image.image_builder:
                        log.debug(f"Image {self.name} is using the image builder from its source image {self.source_image}.")
                        self._image_builder = source_image.image_builder
                    else:
                        log.warning(f"Source image {self.source_image} for image {self.name} does not have an image builder assigned. Cannot determine image builder for {self.name}.")
                else:
                    log.warning(f"Source image {self.source_image} for image {self.name} not found in registry. Cannot determine image builder for {self.name}.")

            # if self._osbuilder:
            #     from cs_image_system.base.global_context import GlobalTypeContext
            #     _ctx = GlobalTypeContext() #     ctx =  _ctx.image_builders
            #     ib = ctx.get(self._osbuilder.model.get_image_builder(), None)
            #     if not ib:
            #         log.warning(f"OS builder {self._osbuilder.get_name()} specifies image builder "
            #                     f" for image {self.name} as {self._osbuilder.model.get_image_builder()} "
            #                     "but no such image builder found in context. ")
            #     self._image_builder = ib
            # else:
            #     log.warning(f"No OS builder assigned for image {self.name}, "
            #                      "cannot determine image builder")
        return self._image_builder
    @image_builder.setter
    def image_builder(self, image_builder: ImageBuilderBase) -> None:
        """Set the image builder for this image."""
        if not image_builder:
            raise ValueError("Image builder cannot be None")
        if self._image_builder and self._image_builder != image_builder:
            # EXPLORE GCP: one image may be baked by several image builders
            # (one per runtime). The first stays the primary; the rest are
            # remembered so each builder's block sees the image.
            log.debug(f"Image {self.name} is also built by {image_builder.get_name()} "
                      f"(primary: {self._image_builder.get_name()})")
            self.extra_image_builders.append(image_builder)
            return
        self._image_builder = image_builder

    @property
    def extra_image_builders(self) -> list[ImageBuilderBase]:
        """Image builders beyond the primary that also bake this image."""
        if not hasattr(self, "_extra_image_builders"):
            self._extra_image_builders: list[ImageBuilderBase] = []
        return self._extra_image_builders

    # @property
    # def osbuilder(self) -> OsBuilderBase | None:
    #     """Get the OS builder for this image."""
    #     return self._osbuilder

    # @osbuilder.setter
    # def osbuilder(self, osbuilder: OsBuilderBase) -> None:
    #     """Set the OS builder for this image."""
    #     if not osbuilder:
    #         raise ValueError("OS builder cannot be None")
    #     if self._osbuilder:
    #         raise ValueError("OS builder cannot be changed once set")
    #     self._osbuilder = osbuilder

    @property
    def dependencies(self) -> set[str]:
        """Get the set of image names that this image depends on."""
        deps: set[str] = set()
        deps.update(self._dependencies)
        return deps

    def set_is_base(self) -> None:
        """Set this image as a base image.  This means that it is not generated from an OS builder and should be treated as a "base" image for resolution purposes."""
        self._is_base = True
        return
    @property
    def is_base(self) -> bool:
        """Return true if this image is a base image, meaning it is not generated from an OS builder and should be treated as a "base" image for resolution purposes."""
        return self._is_base
    def add_dependency(self, image_name: str) -> None:
        """Add a dependency on another image by name."""
        self._dependencies.add(image_name)

    def get_provider_specific_resolved_image_identification_string(self, runtime: str) -> str | None:
        """Get the specific image identifier for a given runtime, if one is mapped."""
        return self._runtime_map[runtime].image_identifier if self._runtime_map[runtime] else None
    def get_specific_machine_type_for_runtime(self, runtime: str) -> str | None:
        """Get the specific machine type for a given runtime, if one is mapped."""
        if runtime in self._runtime_map:
            return self._runtime_map[runtime].machine_type
        return None

    def map_specific_machine_type_to_runtime(self, runtime: str, machine_type: str) -> None:
        """Map a specific machine type to a runtime for this image."""
        rti = self._runtime_map.get(runtime, None)
        if rti:
            if rti.machine_type is None:
                log.debug(f"Mapping specific machine type {machine_type} to runtime "
                          f"{runtime} for image {self.name} (overriding default mapping)")
                rti.machine_type = machine_type
            else:
                raise ValueError(
                    f"Runtime {runtime} already has a machine type mapped: "
                    f"{rti.machine_type}. Cannot map to {machine_type}."
                )
        else:
            log.debug(f"Mapping specific machine type {machine_type} to runtime {runtime} for image {self.name}")
            # self._runtime_map[runtime] = ImageRuntimeSubconfig(runtime=runtime,
            #                                                image_identifier=None,
            #                                                machine_type=machine_type)
    def map_specific_image_to_runtime(self, runtime: str, image_identifier: str) -> None:
        """Map a specific image identifier to a runtime for this image."""
        rti = self._runtime_map.get(runtime, None)
        if rti:
            # You can only overd
            if rti.image_identifier is None:
                log.debug(f"Mapping specific image {image_identifier} to runtime {runtime} for image {self.name} (overriding default mapping)")
                rti.image_identifier = image_identifier
            else:
                raise ValueError(
                    f"Runtime {runtime} already has an image identifier mapped: "
                    f"{rti.image_identifier}. Cannot map to {image_identifier}."
                )
        else:
            log.debug(f"Mapping specific image {image_identifier} to runtime {runtime} for image {self.name}")
            # self._runtime_map[runtime] = ImageRuntimeSubconfig(image_identifier=image_identifier,
            #                                                    machine_type=None,
            #                                                runtime=runtime)

    def get_image_runtime_subconfig_for_runtime(self, runtime: str) -> BaseImageImageBuilderSubconfig | None:
        """Get the data for this image specific to a given runtime."""
        return self._runtime_map.get(runtime, None)

    def get_tags(self) -> dict[str, str]:
        _tags = copy.deepcopy(self.tags) if self.tags else {}
        return _tags