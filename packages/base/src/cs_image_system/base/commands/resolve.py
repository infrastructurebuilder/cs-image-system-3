# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.models.base_image import BaseImage

from ..constants import OOPS_DEFAULTS, VCT
from ..lifecycle import ExecutionLifecyclePhase
from ..global_context import GlobalTypeContext
from ..models.provider_specific_image import PSISourceKind
from ..orchestrator import TemplateResolver

log = logging.getLogger(__name__)


def _create_deferred_psis(ctx: GlobalTypeContext) -> None:
    """Create deferred provider-specific images for user-declared Images.

    These images don't exist yet (a later build produces them), so their
    ProviderSpecificImage carries a name pattern rather than a concrete
    identifier. No cloud calls are made here.
    """
    for img in ctx.images:
        for subconfig in img.runtimes:
            ib = ctx.image_builders.get(subconfig.get_image_builder(), None)
            if ib is None:
                log.warning(f"Image Builder {subconfig.get_image_builder()} for image "
                            f"{img.get_name()} not found while creating deferred "
                            "provider-specific images; skipping")
                continue
            rtb = ctx.runtime_builders.get(ib.model.get_runtime_provider(), None)
            if rtb is None:
                log.warning(f"Runtime Builder {ib.model.get_runtime_provider()} for image "
                            f"{img.get_name()} not found while creating deferred "
                            "provider-specific images; skipping")
                continue
            rtb.create_provider_specific_image_deferred(image=img, subconfig=subconfig)


def predefined_resolve(ctx: GlobalTypeContext, 
                       phase: ExecutionLifecyclePhase,
                       is_base_image_phase: bool = False) -> bool:
    """Resolve

    Perform the required resolution necessary to ensure
    the creation of assets.  This might include things
    like resolving image identifiers, determining which images to build,
    and other resolution tasks.

    """
    # TODO There might be more to do here
    retval: bool = True
    log.info("Starting resolution...")
    added_images: list[BaseImage] = []
    for osb_name, osb in ctx.os_builders.items():
        log.debug(f"Resolving default images for OS builder: {osb_name}")
        # EXPLORE GCP: an OS builder may name several runtimes (AWS and
        # GCE); the vendor image is resolved PER runtime, but exactly one
        # BaseImage is generated and handed to every image builder involved.
        resolutions: dict[str, tuple[str, list[str]]] = {}
        base_builders: list[tuple] = []
        for rt in osb.model.get_runtimes():
            log.debug(f" - Runtime {rt.get_image_builder()} with config {rt}")
            ib = ctx.image_builders.get(rt.get_image_builder(), None)
            if ib is None:
                errstr = (f"Image Builder for OS {osb_name} not found in predefined_resolve: {rt.get_image_builder()}")
                log.error(errstr)
                retval = False
                raise Exception(errstr)
            rtb = ctx.runtime_builders.get(ib.model.get_runtime_provider(), None)
            if not rtb:
                errstr = (f"Runtime Builder for OS {osb_name} not found in predefined_resolve: {ib.model.get_runtime_provider()}")
                log.error(errstr)
                retval = False
                raise Exception(errstr)
            if is_base_image_phase:
                # Base run: query the provider for the vendor image the base
                # image builds FROM, and hand the base image to the image
                # builder so packer builds it.
                x = rtb.query_provider_image(rt)
                if x is None:
                    errstr = (f"No resolved Image identifiers for OS {osb_name} in predefined_resolve")
                    log.error(errstr)
                    retval = False
                    raise Exception(errstr)
                image_id, image_owner, query_result = x
                log.info(f" -> Image for OS {osb_name} "
                         f"for RT {rtb.get_name()} is {image_id} "
                         f"with owner {image_owner} "
                         )
                rtb.create_provider_specific_image_resolved(
                    source_name=osb_name,
                    source_kind=PSISourceKind.OS_BUILDER,
                    identifier=image_id,
                    owner=image_owner,
                    raw_query_result=query_result,
                )
                resolutions[rtb.get_name()] = (image_id, [image_owner])
                base_builders.append((ib, rt, query_result))
                continue
            if True:
                # Execution run: base images are NEVER built here — the base
                # run already produced them. Synthesize the BaseImage for
                # chaining metadata only (no vendor query, never attached to
                # the image builder) and register a deferred PSI whose name
                # pattern locates the base run's most recent built artifact.
                # Under the V2 meta-workflow the base-image lifecycle may have
                # synthesized (and built) this very BaseImage moments ago in
                # the same process: reuse it rather than register a duplicate.
                existing = ctx.reg.get_instance_by_name_or_alias(VCT.BASE_IMAGE_MODEL, osb_name)
                try:
                    i = existing if isinstance(existing, BaseImage) else osb.generate_resolved_image(
                        phase=phase,
                        image_id=None,
                        owners=[],
                        query_result={},
                        resolved=False)
                    if i is None:
                        log.debug(
                            f"OS builder {osb_name} did not generate an image for runtime {rt.get_image_builder()} during "
                            f"{phase.value} phase."
                        )
                        continue # Loop
                    i.set_is_base()
                    added_images.append(i)
                except Exception as e:
                    log.error(f"Failed to generate base image metadata for OS builder {osb_name} and runtime {rt.get_image_builder()}: {e}")
                    raise
                subconfig = i.get_image_runtime_subconfig_for_runtime(rtb.get_name())
                if subconfig is None:
                    errstr = (f"Base image {i.get_name()} has no runtime subconfig for "
                              f"runtime {rtb.get_name()} in predefined_resolve")
                    log.error(errstr)
                    raise Exception(errstr)
                arch = osb.get_architecture()
                rtb.create_provider_specific_image_deferred(
                    image=i,
                    subconfig=subconfig,
                    source_kind=PSISourceKind.OS_BUILDER,
                    architecture=arch if arch not in OOPS_DEFAULTS else None,
                )
                log.info(f" -> Base image {i.get_name()} for RT {rtb.get_name()} deferred "
                         "to the base run's built artifact (name-pattern lookup)")
        if is_base_image_phase and base_builders:
            # ONE BaseImage for the OS builder, every runtime subconfig
            # carrying its own vendor image; handed to each image builder.
            first_rt = base_builders[0][0].model.get_runtime_provider()
            image_id, owners = resolutions[first_rt]
            try:
                i = osb.generate_resolved_image(phase=phase, image_id=image_id, owners=owners,
                                                query_result=base_builders[0][2],
                                                resolutions=resolutions)
            except Exception as e:
                log.error(f"Failed to generate resolved image for OS builder {osb_name}: {e}")
                raise
            if i is None:
                log.debug(f"OS builder {osb_name} did not generate a resolved image during {phase.value}")
                continue
            i.set_is_base()
            for ib, _rt, _q in base_builders:
                log.info(f"OS builder {osb_name} generated image for image builder {ib.get_name()}")
                ib.add_image(i, osb)
            added_images.append(i)
    if not is_base_image_phase:
        _create_deferred_psis(ctx)
    TemplateResolver().resolve_all()

    if not retval:
        log.error("Resolution failed for one or more OS builders.")
    else:
        log.info(f"Resolution complete for {len(ctx.os_builders)} OS builders.")
    return retval
