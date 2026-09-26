# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

# from collections.abc import Mapping, Sequence
from __future__ import annotations

import copy
import logging
import pprint

from .. import utils

from .. import registry
from ..orchestrator import Orchestrator, TemplateResolver
log = logging.getLogger(__name__)
from typing import Any, Sequence, TypeVar,Mapping
from ..lifecycle import ExecutionLifecyclePhase
from ..models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
from ..models.base_image import BaseImage
from ..models.os_builder_model import OsBuilderModel
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .builder_base_image import ImageBuilderBase
from ..constants import DEFAULT, OOPS_DEFAULTS, SELF, VCT
from .asset import AssetSet
from .builder_base import BuilderBase
from .builder_base_image import build_target_label_of

OSRTC = TypeVar("OSRTC", bound=OSBuilderBaseImageBuilderSubconfig)
# Deliberate bound exception: this pseudo-builder wraps an os-image-builder
# SUBCONFIG (a SubRootItem), not a BuilderModel; it satisfies the parts of the
# model surface BuilderBase actually touches.
class OsRuntimeConfigBuilderBase(BuilderBase[OSRTC]):  # type: ignore[type-var]
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.OS_IMAGE_BUILDER_SUBCONFIG

TOS = TypeVar("TOS", bound=OsBuilderModel)
class OsBuilderBase(BuilderBase[TOS]):
    # family: str
    # family_version: str
    # output_image_name: str
    # architecture: str
    # image_builder: str
    # # modifications: list[ModItemModelProtocol]
    # runtimes: list[OSRuntimeConfigModelProtocol]
    # config_username: str | None

    def get_family(self) -> str:
        return self.model.get_family()
    def get_family_version(self) -> str:
        return self.model.get_family_version()
    # def get_output_image_name(self) -> str:
    #     return self.model.output_image_name
    def get_architecture(self) -> str:
        return self.model.get_architecture()
    def get_config_username(self) -> str | None:
        return self.model.get_config_username()
    def get_auto_update(self) -> bool:
        return self.model.get_auto_update()
    def get_runtimes(self) -> Sequence[OSBuilderBaseImageBuilderSubconfig]:
        return self.model.get_runtimes()
    def get_owners(self) -> Sequence[str]:
        return self.model.get_owners()
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.OS_BUILDER

    def get_query(self) -> Mapping[str, Any]:
        return self.model.get_query()
    def __post_init__(self):
        """ Still called from reprocess_b even though this isn't a dataclass"""
        super().__post_init__()
        # self.resolved_images_for_runtime: dict[str, Any] = {}
        # self.resolved_query_results_for_runtime: dict[str, dict[str,Any]] = {}
        for rt in self.get_runtimes():
            rt.model_id = self.global_id   # the subconfigs' one parent (stage 48.2)

    # def set_resolved_image_for_runtime(self, runtime: RuntimeBuilderProtocol, image_id: Any, owner: str, query_result: dict[str, Any]) -> None:
    #     self.resolved_images_for_runtime[runtime.get_name()] = image_id
    #     self.resolved_query_results_for_runtime[runtime.get_name()] = query_result

    # def get_resolved_image_for_runtime(self, runtime: str) -> Any | None:
    #     if runtime:
    #         return self.resolved_images_for_runtime.get(runtime, None)
    #     return None
    def generate_resolved_image(self,
                                phase: ExecutionLifecyclePhase,
                                image_id: Any,
                                owners: list[str],
                                query_result: Mapping[str, Any],
                                resolved: bool = True,
                                resolutions: Mapping[str, tuple[Any, list[str]]] | None = None) -> BaseImage | None:
        # resolved=False synthesizes the BaseImage for chaining metadata only
        # (execution runs, where the base run already built the artifact and no
        # vendor-image query is made) — image_identifier stays None.
        from ..global_context import GlobalTypeContext
        ctx = GlobalTypeContext()
        cvt = Orchestrator().get_converter()
        reg = registry.Registry()
        template_resolver = TemplateResolver() # Already has 'addl' fields registered
        rt_list = []
        for os_imgbld_name, os_img_subconfig in self.get_configs_for_image_builders().items():
            log.debug(
                    f"Ensuring Image  OS: {self.get_name()} "
                    f"for Image Builder: {os_imgbld_name}"
                )
            img_bldr: ImageBuilderBase|None = ctx.image_builders.get(os_img_subconfig.get_image_builder(), None)
            if not img_bldr:
                errstr = (f"Image Builder {os_img_subconfig.get_image_builder()} for "
                          f"OS {self.get_name()} and runtime {os_imgbld_name} not found in predefined_resolve: "
                          f"{os_img_subconfig.get_image_builder() if img_bldr else None}")
                log.error(errstr)
                raise Exception(errstr)
            rt_bldr = ctx.runtime_builders.get(img_bldr.model.get_runtime_provider(), None) if img_bldr else None
            if not rt_bldr:
                errstr = (f"Runtime Builder {img_bldr.model.get_runtime_provider()} for "
                          f"OS {self.get_name()} and image builder "
                          f"{os_imgbld_name} not found in predefined_resolve: ")
                log.error(errstr)
                raise Exception(errstr)
            # image_id = self.resolved_images_for_runtime.get(rbb.get_name(), None)
            # query_result = self.resolved_query_results_for_runtime.get(rbb.get_name(), None)
            if query_result is None:
                query_result = {}
            # One BaseImage spans every runtime the OS builder names; each
            # runtime subconfig carries ITS vendor image (EXPLORE GCP: a
            # base image on AWS and GCE at once).
            rt_image_id, rt_owners = image_id, owners
            if resolutions and img_bldr.model.get_runtime_provider() in resolutions:
                rt_image_id, rt_owners = resolutions[img_bldr.model.get_runtime_provider()]
            if rt_image_id is None and resolved:
                raise ValueError(f"No resolved image for runtime {img_bldr.get_name()} in OS builder {self.name}")
            dmt = os_img_subconfig.get_default_machine_type()
            if dmt in OOPS_DEFAULTS:
                dmt = img_bldr.model.get_default_machine_type()
            if dmt in OOPS_DEFAULTS:
                dmt = rt_bldr.get_default_machine_type()
            if dmt in OOPS_DEFAULTS:
                errstr = (f"No default machine type specified for runtime {img_bldr.get_name()} in OS builder {self.name} "
                          f"or its associated image builder {img_bldr.get_name()} or "
                          f"runtime builder {rt_bldr.get_name()}; using {DEFAULT}.")
                log.warning(errstr)
                dmt = DEFAULT
            tags: dict[str,str] = {}
            for k,v in copy.deepcopy(img_bldr.model.get_tags()).items():
                tags[k] = v
            for k,v in os_img_subconfig.get_tags().items():
                if k in tags:
                    log.warning(f"Tag {k} from OS builder {self.get_display_name()} runtime config for runtime {img_bldr.get_display_name()} is overwriting tag with same key from runtime builder {img_bldr.get_display_name()}. Value from OS builder will take precedence.")
                tags[k] = v

            # The runtime for this config is the image builder's own runtime, not the
            # image builder itself. img_bldr was resolved above from
            # os_img_subconfig.get_image_builder().
            image_builder_runtime = img_bldr.model.get_runtime_provider()
            rtcm_map: dict[str, Any] = {
                "runtime": image_builder_runtime,
                "type": DEFAULT,
                "name": os_img_subconfig.get_name(),
                "image_identifier": rt_image_id,
                "auto_update": os_img_subconfig.get_auto_update(),
                # dmt must land on machine_type too: the subconfig's
                # machine_type is a templated field that otherwise fills
                # itself with the RUNTIME default, clobbering the OS-builder
                # declaration (found live: t3.medium bakes stayed t2.micro)
                "machine_type": dmt,
                "tags": tags,
                "owners" : rt_owners,
                # stage 22.2: this dict also carried "source_image",
                # "default_machine_type", "default_primary_disk_size" and
                # "query". None is a field on BaseImageImageBuilderSubconfig,
                # so all four were dropped in silence. "machine_type" DOES
                # land, which is why the dmt comment above still holds; its
                # "default_machine_type" twin never did.
            }
            # stage 63 item 22: the one resolver (entry, config_username, the
            # runtime's ssh_username and default_config_username, the family
            # user); this used to take the entry or a hard-coded AWS vendor
            # map, never the two config_username fields
            from ..bake_user import resolve_for_entry
            ssun = resolve_for_entry(ctx, self, os_img_subconfig, str(image_builder_runtime),
                                     what=f"OS builder {self.get_display_name()}")
            log.debug(f"Bake user for OS builder {self.get_display_name()} on {image_builder_runtime}: {ssun}")
            rtcm_map["ssh_username"] = ssun
            # rtcm = cvt.structure(rtcm_map, OSRuntimeConfigModel)
            # template_resolver.flatten_dataclass(rtcm) # Flatten the dataclass to resolve any templates in the fields
            # rtcm = OSRuntimeConfigModel(
            #     runtime = osrc.get_runtime(),
            #     type = DEFAULT,
            #     name = osrc.get_name(),
            #     image_id = image_id,
            #     auto_update = osrc.get_auto_update(),
            #     default_machine_type = rbb.get_default_machine_type(),
            #     default_primary_disk_size = osrc.get_default_primary_disk_size(),
            #     tags = osrc.get_tags(),
            #     query = osrc.get_query()
            # )
            rt_list.append(rtcm_map)

        log.debug(f"Generating resolved image for {self.__class__.__name__} in phase "
                  f"{phase} with runtime builder {img_bldr.get_name()}.")
        i: BaseImage = None # type: ignore
        # Base images receive no modification elements — at most the OS-provided
        # package-level update (see generate_items_for_os_update). Any mods
        # declared on the OS builder are intentionally NOT carried onto the
        # synthesized BaseImage.
        # stage 22.2: the list itself is gone with the dict key that carried it;
        # the warning stays, because an OS builder declaring modifications is
        # still worth telling the operator about.
        if self.model.get_modifications():
            log.warning(f"OS builder {self.get_display_name()} declares modifications, "
                        "but base images do not receive modifications — ignoring them")
        tags = utils.strip_tags(self.get_tags())
        # self is the OsBuilder
        image_map: dict[str, Any] = {
            "name": self.get_name(),
            # stage 48.3: BaseImage.type is "the image builder to use for this image"
            # (an Image says the same); the OS builder's own type was written here
            # and resolved only through the foreign-key fallback
            "type": img_bldr.get_name(),
            "description": f"Default resolved image for OS builder {self.name} and runtime {img_bldr.get_name()}",
            "aliases": set(), # No aliases for these image
            "config": {},
            "os": "", # str
            "source_image": SELF,
            "auto_update": False,
            "is_default": True,
            "primary_disk_size": DEFAULT,
            "variables": {},
            "tags": tags,
            "runtimes": rt_list,
            # stage 22.2: this dict also carried "machine_type",
            # "architecture", "auto_generate_storage", "modifications"
            # (mods_list) and "default_groups" -- none of which is a BaseImage
            # field, so all five were dropped in silence. "modifications" is
            # the notable one and its answer is already above: base images
            # receive none by design, so mods_list is always empty; passing it
            # only made the resolver look as though it carried them.

            # V2 capability axes + admin user travel with the base image.
            "identity_types": list(self.model.get_identity_types()),
            "storage_types": list(self.model.get_storage_types()),
            "admin_user": self.model.get_admin_user(),
            "admin_public_keys": self.model.get_admin_public_keys(),
            "tests": dict(getattr(self.model, "tests", None) or {}),
        }
        qv = pprint.pformat(image_map)
        log.debug(f"Image map for {self.get_display_name()}:\n{qv}")
        i = cvt.structure(image_map, BaseImage)
        reg.register_built_instance(i) # Register the built image in the global registry for resolution by other builders that depend on it
        for rt in i.runtimes:
            rt.model_id = i.global_id
        template_resolver.flatten_dataclass(i) # Flatten the dataclass to resolve any templates in the fields
        return i

    # def get_runtime_config_query_results(self, runtime: RuntimeBuilderProtocol) -> Mapping[str, Any] | None:
    #     return self.resolved_query_results_for_runtime.get(runtime.get_name(), None)


    def generate_items_for_os_update(self, image, image_builder, phase,
                                     build_path) -> AssetSet:
        """The OS-provided means of updating a base image during its build.

        Base images receive no modification elements -- at most this full
        package-level update, and only when the image's runtime subconfig has
        auto_update set. The default mechanism (shared by all command-driven
        OS types) wraps the model's get_command_to_update() in a packer shell
        provisioner scoped to the image; subclasses provide their own means
        either via that command list (config-driven) or by overriding this
        hook outright (e.g. an ansible-based update).
        """
        items = AssetSet()
        from ..models.update_policy import POLICY_FULL, UpdatePolicy, manifest_commands
        subconfig = image.get_image_runtime_subconfig_for_runtime(
            image_builder.model.get_runtime_provider())
        # Legacy/stub models expose only get_command_to_update(); real OS
        # builder models carry the update policy.
        model = self.model
        policy: UpdatePolicy = (model.effective_update_policy()
                                if isinstance(model, OsBuilderModel) else UpdatePolicy())
        if subconfig is not None and subconfig.get_auto_update() and policy.is_noop:
            policy = UpdatePolicy(policy=POLICY_FULL)   # subconfig-level alias
        if policy.is_noop:
            return items
        commands: list[str] = list(model.commands_for_policy(policy) if isinstance(model, OsBuilderModel)
                                   else model.get_command_to_update())
        if not commands:
            return items
        commands = commands + manifest_commands()
        if not commands:
            return items
        # escape HCL template sequences (packer: $$ / %% render literal ${ %{)
        quoted = ", ".join('"{}"'.format(c.replace('"', '\\"').replace("${", "$${").replace("%{", "%%{"))
                           for c in commands)
        items.add_list(build_path, [
            f"  # OS update for base image {image.get_name()} "
            f"(policy={policy.policy}, packages={list(policy.packages)}, exclude={list(policy.exclude)}, "
            f"pin={dict(policy.pin)}, {self.get_type()})",
            '  provisioner "shell" {',
            f'    only   = ["{build_target_label_of(image_builder, image)}"]',
            f"    inline = [{quoted}]",
            "  }",
        ])
        return items

    def get_runtime_config_query_results(self, runtime) -> Mapping[str, Any] | None:
        # Preserved from the removed protocol declaration (no implementation exists).
        return None

    def get_configs_for_image_builders(self) -> dict[str, OSBuilderBaseImageBuilderSubconfig]:
        """Get the runtime configurations for this OS builder, keyed by runtime type."""
        configs: dict[str, OSBuilderBaseImageBuilderSubconfig] = {}
        for rc in self.model.get_runtimes():
            configs[rc.get_image_builder()] = rc
        return configs
