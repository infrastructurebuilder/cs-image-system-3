# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

from .builder_base import BuilderBase
from ..constants import VCT
from ..models.image import Image, ImageImageBuilderSubconfig
from ..models.provider_specific_image import (
    GenericProviderSpecificImage,
    ProviderSpecificImage,
    PSISourceKind,
)
from ..models.runtime import RuntimeBuilderModel
if TYPE_CHECKING:
    from .builder_base_image import ImageBuilderBase
    from .builder_base_instance import InstanceBuilderBase
    from ..models.base_image import BaseImage, BaseImageImageBuilderSubconfig

log = logging.getLogger(__name__)


class RuntimeBuilderBase(BuilderBase[TypeVar("T", bound=RuntimeBuilderModel)]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._image_builders: list[ImageBuilderBase] = []
        self._instance_builders: list[InstanceBuilderBase] = []

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.RUNTIME_BUILDER


    def query_provider_image(self, os_builder) -> tuple[str, str, Any] | None:
        # Preserved from the removed protocol declaration: concrete runtime
        # builders (aws, gcloud) override this with real cloud queries.
        return None

    def query_images(self, series: list[str]) -> list[dict[str, Any]]:
        """Reality check (EXPLORE state query): every image in this
        runtime that carries the system's lineage tags, ``[{image_id, name,
        state, created, tags}]``, read-only. ``series`` hints which series
        the caller knows about; a runtime may return more. Optional."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot query images")

    def verify_instance(self, instance_name: str, expected_build: str | None = None,
                        expect_mounts: int = 0, timeout: int = 600) -> dict[str, Any]:
        """Verify a launched instance without an operator session (TODO
        §10.2): ``{"ok": bool, "checks": [{"name", "ok", "detail"}],
        "evidence": [lines]}``. GCE reads the serial console (startup
        scripts finished, no failure line, data disks mounted) and the
        booted image; a runtime without a verification path raises
        NotImplementedError (ephemeral instances refuse there)."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot verify instances")

    def run_session_command(self, instance_name: str, script: str, timeout: int = 300) -> tuple[int, str]:
        """Run a shell script ON a launched instance through this runtime's
        session mechanism (stage 10.14: the unmount before a detach) and
        return ``(exit status, output)``. GCE: IAP-tunnelled ssh; AWS: SSM
        RunShellScript. A runtime without one raises NotImplementedError."""
        raise NotImplementedError(f"{self.__class__.__name__} has no session mechanism to run commands")

    def inventory(self) -> dict[str, list[str]]:
        """Everything that exists on this runtime that the system could have
        created (stage 11.5): ``{"instances": [...], "images": [...],
        "disks": [...], "buckets": [...]}`` -- read-only. A runtime without an
        inventory raises NotImplementedError (`empty --runtime` refuses)."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot list its inventory")

    def dispose_image(self, build_id: str) -> bool:
        """Delete one of OUR OWN recorded images from this runtime (the
        sanctioned disposal, stage 8.4): the cloud artifact named by the
        lineage build id. Returns False when the runtime finds no such
        image (already gone -- the record is still dropped). Raises
        NotImplementedError when this runtime cannot dispose."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot dispose images")

    def retag_image(self, image_id: str, tags: dict[str, str]) -> bool:
        """Update lineage tags on one of OUR OWN built images (zero-drift-
        report): a parent resolved after the bake leaves generation-time
        ``csis_parent``/``csis_fingerprint`` tags stale versus lineage, and
        the fix is to make reality right, not to look away. Returns False
        when this runtime cannot retag (the state query then keeps showing
        the honest ``changed`` line)."""
        import logging
        logging.getLogger(__name__).info(
            f"{self.__class__.__name__} cannot retag {image_id}; tags {sorted(tags)} stay stale")
        return False

    # ------------------------------------------------- packer source hooks
    # (EXPLORE GCP, increment 1: the packer builder is provider-neutral;
    # the runtime plugin owns everything that names its packer plugin.)
    def packer_source_type(self) -> str:
        """The packer source/builder type this runtime bakes with
        (``amazon-ebs``, ``googlecompute``, ...)."""
        raise NotImplementedError(f"{self.__class__.__name__} declares no packer source type")

    def packer_source_blocks(self, image: Any, *, runtime: str, source_type: str, subconfig: Any,
                             self_subconfig: Any, psi: Any, tags: dict[str, str],
                             final_name: str, pinned: str | None) -> list[str]:
        """HCL lines for the ``source "<type>" "<image>"`` block (plus any data
        lookups it needs) that bakes ``image`` on this runtime. ``psi`` is the
        provider-specific image of the bake's source; ``pinned`` the exact
        parent build id when the image is pinned (DESIGN N5); ``tags`` the
        merged image + lineage tags; ``final_name`` the artifact name."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot emit packer sources")

    def build_id_from_artifact(self, artifact_id: str) -> str:
        """The lineage build id carried by a packer manifest ``artifact_id``
        (amazon-ebs: ``<region>:<ami>`` -> ami; googlecompute: the image name)."""
        return artifact_id.split(":")[-1] if artifact_id else artifact_id

    def get_default_machine_type(self) -> str:
        return self.model.get_default_machine_type()

    # ---------------------------------------------------------- V2 contract
    def session_mechanism(self) -> str | None:
        """The cloud's session-based debug access (N9: "AWS SSM or each
        cloud's equivalent"), if this runtime is configured for it. None =
        no session mechanism; the admin key is then the only debug path."""
        return None

    def session_agent_commands(self, os_family: str | None = None) -> list[str]:
        """Shell commands that bake the session agent into a base image."""
        return []

    def session_verify_commands(self, os_family: str | None = None) -> list[str]:
        """Shell assertions proving the session agent is baked."""
        return []

    def bake_finalize_commands(self, os_family: str | None = None) -> list[str]:
        """Shell commands emitted as the LAST provisioner of every bake on
        this runtime (base and instance images alike) — cloud-specific
        image hygiene the baked artifact needs to boot cleanly (finding
        47). Default: none."""
        return []

    def can_query_instance_boot_image(self) -> bool:
        """Whether this runtime implements query_instance_boot_image; the
        state query asks only runtimes that do, so an unsupported cloud
        makes no claim and adds no noise."""
        return False

    def query_instance_boot_image(self, instance_name: str) -> str | None:
        """The build id the named instance actually BOOTED from, read from
        the cloud (read-only) -- e.g. the boot disk's source image on GCE,
        the AMI on AWS. Used to bind an instance's pin from reality when its
        parent was deferred at launch, and by the state query to compare the
        booted image with the pin (finding 49). None = this runtime cannot
        answer; no claim is made."""
        return None

    def can_query_instance_power_state(self) -> bool:
        """Whether this runtime implements query_instance_power_state (stage
        57). Gated like the boot-image query so an unsupported cloud makes no
        claim: callers ask only runtimes that answer."""
        return False

    def query_instance_power_state(self, instance_name: str) -> str | None:
        """Is the named machine powered on, as the PROVIDER reports it --
        EC2's ``State.Name``, GCE's ``status`` -- mapped onto the vocabulary
        in ``power_state`` so no caller reads a cloud's spelling (stage 57).

        ``None`` means THIS RUNTIME CANNOT ANSWER, which is never the same as
        ``STOPPED``: an instance the operator switched off is in the state
        they chose, while None is the absence of knowledge. Conflating the
        two is the bug this hook exists to end -- ``query_instance_boot_image``
        answers None for a stopped machine and for an unreachable cloud
        alike, because the probe behind it filters on ``running``."""
        return None

    def can_set_instance_power_state(self) -> bool:
        """Whether this runtime implements start/stop (stage 57). Separate
        from the query gate: a cloud may well be readable but not driveable
        by these credentials."""
        return False

    def start_instance(self, instance_name: str, timeout: int = 300) -> bool:
        """Start a stopped machine and wait until the PROVIDER reports it
        running. True when it is running at return.

        This is never reconciliation. The only caller is a bounded task that
        needs a running machine (``running_for_task``), and it puts the
        machine back the way it found it."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot start instances")

    def stop_instance(self, instance_name: str, timeout: int = 300) -> bool:
        """Stop a running machine and wait until the provider reports it
        stopped. True when it is stopped at return."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot stop instances")

    def bake_ssh_username(self) -> str | None:
        """The ssh user packer's build VM is reached as on this runtime, for
        provisioners that must name it explicitly (the ansible provisioner
        otherwise defaults to the operator's LOCAL login — finding 48).
        None = the runtime declares no fixed bake user, and provisioners keep
        their own default (the AWS path, unchanged)."""
        return None

    def release_commands(self, build_id: str, tags: dict[str, str]):
        """Executables that mark a built artifact as released in the cloud
        (e.g. tag the AMI). Default: none."""
        return []

    def session_instance_profile(self) -> str | None:
        """Instance-level wiring (e.g. an IAM instance profile) the session
        mechanism needs on launched instances."""
        return None
    def apply_specific_changes(self, image: Image) -> Image:
        """Apply provider-specific changes to the image."""
        return image

    def add_image_builder(self, image: ImageBuilderBase) -> None:
        if image not in self._image_builders:
            self._image_builders.append(image)
    def add_instance_builder(self, instance: InstanceBuilderBase) -> None:
        if instance not in self._instance_builders:
            self._instance_builders.append(instance)

    def provider_specific_image_class(self) -> type[ProviderSpecificImage]:
        """Hook: the ProviderSpecificImage subclass this runtime produces.

        Runtime plugins override this to supply their provider-specific type.
        """
        return GenericProviderSpecificImage

    def create_provider_specific_image_resolved(
        self,
        *,
        source_name: str,
        source_kind: PSISourceKind,
        identifier: str,
        owner: str | None = None,
        raw_query_result: Any | None = None,
        architecture: str | None = None,
    ) -> ProviderSpecificImage:
        """Create and register a resolved ProviderSpecificImage for this runtime."""
        from ..registry import Registry
        psi = self.provider_specific_image_class().resolved(
            source_name=source_name,
            source_kind=source_kind,
            runtime=self.get_name(),
            identifier=identifier,
            owner=owner,
            raw_query_result=raw_query_result,
            architecture=architecture,
        )
        Registry().register_built_instance(psi)
        log.debug(f"Registered resolved provider-specific image {psi.get_name()} -> {identifier}")
        return psi

    def create_provider_specific_image_deferred(
        self,
        *,
        image: Image | BaseImage,
        subconfig: ImageImageBuilderSubconfig | BaseImageImageBuilderSubconfig,
        source_kind: PSISourceKind = PSISourceKind.IMAGE,
        architecture: str | None = None,
    ) -> ProviderSpecificImage:
        """Create and register a deferred ProviderSpecificImage for a not-yet-built image.

        Deferred PSIs locate an artifact a build produces — a later block in
        this run (user Images) or a prior base-image run (BaseImages, which
        carry OS_BUILDER source_kind and must pass architecture explicitly).
        """
        from ..registry import Registry
        psi = self.provider_specific_image_class().deferred(
            source_name=image.get_name(),
            source_kind=source_kind,
            runtime=self.get_name(),
            deferred_name_pattern=subconfig.get_image_output_name(),
            architecture=(architecture if architecture is not None
                          else getattr(image, "architecture", None)),
        )
        Registry().register_built_instance(psi)
        log.debug(f"Registered deferred provider-specific image {psi.get_name()} "
                  f"with pattern {psi.deferred_name_pattern}")
        return psi
