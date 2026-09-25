# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
import logging
from dataclasses import field
from .model_config import CSIS_MODEL_CONFIG
from pydantic import Field
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Annotated, TYPE_CHECKING, Any, Mapping, Sequence


# from cs_image_system.base.models.base_image import BaseImage


from ..helpers.field_helpers import fk_field, templated_field
from .root_item import SubRootItem

from ..constants import  DEFAULT, OOPS_DEFAULTS, VCT

if TYPE_CHECKING:
    from .os_builder_model import OsBuilderModel
    from .runtime import RuntimeBuilderModel
from .base_image import BaseImage
log = logging.getLogger(__name__)


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OSBuilderBaseImageBuilderSubconfig(SubRootItem):
    image_builder: str = fk_field(target = VCT.IMAGE_BUILDER_MODEL,
                                  default = DEFAULT,
                             metadata={
                                "description": "The image-builder this config uses",
                                "required": True,
                                    })
    name: str | None = None
    type_: Annotated[str, Field(alias="type")] = templated_field(replace_value="{{ identified_model.name }}", 
                                default = DEFAULT,
                                metadata={
                                "description": "parent model",
                                "required": True,
                                })
    description: str = " {{ image_builder.name }} runtime configuration for {{ this.name }}"
#     output_image_name: str  = "{{ os.output_image_name }}-{{ self.runtime }}". #REMOVED
    image_id: str | None = None
    image_name: str | None = None
    auto_update: bool | None = None # None inherits the OS builder's auto_update
    default_machine_type: str | None = None # Only for image creation
    default_primary_disk_size: int = 100
    tags: Mapping[str, str] = field(default_factory=dict)
    owners: list[str] = field(default_factory=list) # Added to parent owners
    query: Mapping[str, Any] = field(default_factory=dict)
    ssh_username: str  = DEFAULT
    # Per-runtime in-bake tests: when set, REPLACES the os builder's tests
    # for bakes on this runtime (finding 40: the fixture's AWS package test
    # asserted nfs-utils on a GCE bake where the efs prerequisite rightly
    # never ran). None inherits the builder-level tests.
    tests: Mapping[str, Any] | None = None
    _runtime_image: BaseImage | None = field(init=False, default=None)
    # _model_id: str | None = field(init=False, default=None)
    # This needs placed here to override the one in ParentPropertyHoldingProtocol
    _model_id: str | None = fk_field(target = VCT.OS_BUILDER_MODEL,
                                     init=False, 
                                     default=None,
                                     metadata={
                                        "description": "Associatd OS Builder",
                                        "required": True,})
    
    def _runtime_model(self) -> RuntimeBuilderModel | None:
        """The runtime this entry bakes on: its IMAGE BUILDER's runtime (stage
        63 item 22). The lookup used to key the runtime namespace by the
        image builder's own name and never found one, so the runtime's
        ``default_owners`` never reached a query."""
        ib: Any = self._reg.get_instance_by_name_or_alias(VCT.IMAGE_BUILDER_MODEL, self.image_builder)
        if ib is None:
            return None
        try:
            runtime = ib.get_runtime_provider()
        except ValueError:                      # an image builder still on `default`
            return None
        return self._reg.get_instance_by_name_or_alias(VCT.RUNTIME_BUILDER_MODEL, runtime)

    def get_owners(self) -> Sequence[str]:
        _rt: RuntimeBuilderModel | None = self._runtime_model()
        _owners: list[str] = []
        _parent = self.identified_model
        if _parent:
            _owners.extend(_parent.get_owners() or [])
        if _rt:
            _owners.extend(_rt.get_default_owners() or [])
        _owners.extend(self.owners)
        seen: set[str] = set()
        return [x for x in _owners if not (x in seen or seen.add(x))]
    def get_image_builder(self) -> str:
        return self.image_builder
    def get_type(self) -> str:
        return self.image_builder
    def get_config(self) -> dict[str, Any]:
        return {}
    def get_description(self) -> str | None:
        return self.description
    def get_image_id_for_runtime(self) -> str | None:
        return self.image_id
    def get_image_name(self) -> str | None:
        return self.image_name    
    def get_default_primary_disk_size(self) -> int:
        return self.default_primary_disk_size    
    def get_auto_update(self) -> bool:
        if self.auto_update is not None:
            return self.auto_update
        parent = self.identified_model
        return bool(parent.get_auto_update()) if parent is not None else False    
    def get_default_machine_type(self) -> str | None:
        return self.default_machine_type
    def get_executable(self) -> str | None:
        return None
    def get_is_default(self) -> bool:
        return False
    def get_gitignore(self) -> list[str]:
        return []    
    def get_name(self) -> str:
        assert self.name is not None, f"Runtime configuration {self.image_builder} must have a name."
        return self.name

    @classmethod
    def csis_name(cls) -> str:
        return "os_runtime_config"
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.OS_IMAGE_BUILDER_SUBCONFIG_MODEL

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.name:
            self.name = self.name.strip()
        self.image_builder = self.image_builder.strip()
        if not self.image_builder:
            raise ValueError(f"Runtime configuration type cannot be empty for {self}")
        if self.aliases:
            raise ValueError(f"Aliases are not allowed for runtime configurations, "
                             f"but got {self.aliases} for {self.name}")
    def finalize(self) -> None:
        if self._finalized:
            return
        super().finalize()
        # Ensure the model_id is set to the associated OS builder's name for proper association in the registry
        if self._model_id is None:
            raise ValueError(f"Model ID must be set for OSRuntimeConfigModel {self.name} prior to finalization.")
        # stage 63 item 22: this method used to fill ssh_username from
        # config_username, then from the runtime's default_config_username
        # (looked up by the wrong key), and refuse when neither answered; it
        # had no caller. The bake user is now decided in ONE place,
        # cs_image_system.base.bake_user, in the operator's order (the
        # runtime's own ssh_username sits between those two fields, which a
        # value written here would have overtaken), and the refusal is its.


    @property
    def os(self) -> OsBuilderModel | None:
        return self.identified_model

    # @property
    # def runtime_image(self) -> "Image":
    #     if not self._runtime_image:
    #         raise ValueError(f"No image assigned for runtime configuration {self.name}")
    #     return self._runtime_image

    # @runtime_image.setter
    # def runtime_image(self, image: Image | None) -> None:
    #     self._runtime_image = image
    #     # --- FIX 2: Safeguard the attribute access ---
    #     if image:
    #         self.image_id = image.image_identifier
    def get_ssh_username(self) -> str | None:
        # A declared ssh_username on the runtime entry wins (finding 43: the
        # GCE chain must bake every image as ONE user, or the guest agent's
        # stale-user removal aborts metadata key provisioning). Unset entries
        # return None so consumers keep their own fallback resolution
        # (see builder_base_os.generate_resolved_image).
        return None if self.ssh_username in OOPS_DEFAULTS else self.ssh_username
    def get_runtime_image(self) -> BaseImage | None:
        return self._runtime_image 
    @property
    def identified_model(self) -> OsBuilderModel | None:
        return super().identified_model # type: ignore
    def get_tags(self) -> dict[str, str]:
        mod = self.identified_model
        tags:dict[str, str] = {}
        if mod and mod.get_tags():
            tags.update(mod.get_tags())
        tags.update(self.tags)
        return tags

    def get_query(self) -> Mapping[str, Any]:
        parent = self.identified_model
        q: dict[str, Any] = {}
        if parent and parent.get_query():
            for k, v in parent.get_query().items():
                q[k] = v
        for k,v in self.query.items():
            q[k] = v
        return q

    @property
    def output_image_name(self) -> str:
        return self.display_name
