# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
import logging
log = logging.getLogger(__name__)
from ..lifecycle import ExecutionLifecyclePhase
from ..global_context import GlobalTypeContext


def predefined_image_generation(
    ctx: GlobalTypeContext, 
    phase: ExecutionLifecyclePhase,
    is_base_image_phase: bool = False
) -> bool:
    """
    Predefined function for image generation lifecycle phase.
    
    A predefined image is one that is produced by the system through the osbuilders.  As any instance must be based on an image, and
    any image needs some sort of source, the osbuilders are responsible for producing the basic images that generates a source for 
    later-read "image" objects.
    
    This is sort of a weird lifecycle phase.  It may or may not produce an actual packer build.  If it does, then the image will be built
    in the phase 000 of the packer build lifecycles, but for constructed images, the source image will always be "get the latest matching 'me'"
    for the source image.  Every image needs to be able to produce a means for querying it for all of its runtimes. 
    
    For base images, this is where that happens.
    For specified/constructed images, this is where the source image is resolved and set on the image object.
    
    """

    for ibb_name, ibb in ctx.image_builders.items():
        rtp = ctx.runtime_builders.get(ibb.model.get_runtime_provider(), None)
        if not rtp:
            log.error(
                f"No runtime provider found for image builder {ibb_name}. "
                "Skipping image generation for this builder."
            )
            return False
        log.debug(
                f"Generating images for builder: {ibb_name} "
                f"with runtime provider: {rtp.get_name()}"
            )

        genfiles = ibb.generate_items_during(phase)
        genfiles.sort_and_write()
        cfe = ibb.get_commands_to_run_during(phase)
        ctx.extend_finalization_phase(phase,cfe.finalize_executables)
        for cmd in cfe.build_executables:
            log.debug(
                    f"Running command for image builder {ibb.get_name()} "
                    f"for runtime provider {rtp.get_name()}: {cmd.binary} "
                    f"{' '.join(cmd.args)}"
                )
            result = cmd.execute()
            if result.returncode != 0:
                log.error(
                    f"Command failed with return code {result.returncode} "
                    f"for image builder {ibb.get_name()} and runtime provider "
                    f"{rtp.get_name()}: {cmd.binary} {' '.join(cmd.args)}"
                )
                return False
    return True
