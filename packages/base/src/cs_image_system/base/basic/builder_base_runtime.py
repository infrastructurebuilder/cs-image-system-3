# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from cs_image_system.contract.image import ImageQuery
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from .builder_base import BuilderBase
from cs_image_system.contract.runtime import RuntimeBuilderProtocol
from cs_image_system.contract.session import LoadFailureReport, SessionStatus
from cs_image_system.contract.constants import VCT
from ..models.image import Image, ImageImageBuilderSubconfig
from ..models.provider_specific_image import (
    GenericProviderSpecificImage,
    ProviderSpecificImage,
    PSISourceKind,
)
from ..models.runtime import RuntimeBuilderModel
from cs_image_system.contract.runtime import LAUNCH_DELIVERY_BOOT
from ..image_sources import packaged_entries_of
from ..network_facts import coverage_problems, facts_of
if TYPE_CHECKING:
    from .builder_base_image import ImageBuilderBase
    from .builder_base_instance import InstanceBuilderBase
    from ..models.base_image import BaseImage, BaseImageImageBuilderSubconfig

log = logging.getLogger(__name__)


R = TypeVar("R", bound=RuntimeBuilderModel)


class RuntimeBuilderBase(BuilderBase[R], RuntimeBuilderProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._image_builders: list[ImageBuilderBase] = []
        self._instance_builders: list[InstanceBuilderBase] = []

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.RUNTIME_BUILDER


    def query_provider_image(self, os_builder) -> tuple[str, str, Any] | None:
        # Preserved from the removed protocol declaration: concrete runtime
        # builders (the cloud plugins) override this with real cloud queries.
        return None

    def query_provider_image_by_id(self, os_builder, image_id: str) -> tuple[str, str, Any] | None:
        """The vendor image an OS builder entry PINS by id (stage 63: the
        entry's ``image_id``; the vendor query is skipped). Same shape as
        ``query_provider_image``; None when the provider does not know it."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot look a vendor image up by id")

    def query_images(self, series: list[str]) -> list[dict[str, Any]]:
        """Reality check (EXPLORE state query): every image in this
        runtime that carries the system's lineage tags, ``[{image_id, name,
        state, created, tags}]``, read-only. ``series`` hints which series
        the caller knows about; a runtime may return more. Optional."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot query images")

    def verify_instance(self, instance_name: str, expected_build: str | None = None,
                        expect_mounts: int = 0, timeout: int = 600,
                        mount_points: list[str] | None = None) -> dict[str, Any]:
        """Verify a launched instance without an operator session (TODO
        §10.2): ``{"ok": bool, "checks": [{"name", "ok", "detail"}],
        "evidence": [lines]}``. A cloud runtime reads the serial console (startup
        scripts finished, no failure line, data disks mounted) and the
        booted image; a runtime without a verification path raises
        NotImplementedError (ephemeral instances refuse there).
        ``mount_points`` names the declared mounts (hygiene XII item 22):
        a runtime that can read the startup script's own line per mount
        passes the check only when each one reports itself mounted;
        ``expect_mounts`` is the count, for a runtime that can only count."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot verify instances")

    def ssh_proxy_command(self, instance_name: str) -> list[str] | None:
        """An ssh ``ProxyCommand`` (argv, ``%p`` for the port) that reaches a
        launched instance through this runtime's session mechanism -- no
        public address, no inbound rule (stage 75 step 6: one cloud's
        session-manager ssh document, the path packer already bakes through;
        another's identity-aware tunnel). None when the runtime has none."""
        return None

    def run_session_command(self, instance_name: str, script: str, timeout: int = 300) -> tuple[int, str]:
        """Run a shell script ON a launched instance through this runtime's
        session mechanism (stage 10.14: the unmount before a detach) and
        return ``(exit status, output)``: tunnelled ssh on one cloud, the
        session manager's run-script document on another. A runtime without
        one raises NotImplementedError."""
        raise NotImplementedError(f"{self.__class__.__name__} has no session mechanism to run commands")

    def inventory(self) -> dict[str, Any]:
        """Everything that exists on this runtime that the system could have
        created (stage 11.5): ``{"instances": [...], "images": [...],
        "disks": [...], "buckets": [...]}`` -- read-only; and, when the
        runtime can read labels, ``"owners": {kind: {name: csis_config}}``
        for every thing that carries a configuration's id (stage 93), so the
        emptiness check leaves another configuration's things alone. A
        runtime without an inventory raises NotImplementedError (`empty
        --runtime` refuses)."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot list its inventory")

    def instance_tags(self, instance_name: str) -> dict[str, str] | None:
        """The tags or labels the named machine carries, None when none
        stands (stage 93: what `lineage relabel` reads before it adds the
        configuration's id). A runtime that cannot read them raises."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot read a machine's tags")

    def retag_instance(self, instance_name: str, tags: dict[str, str]) -> bool:
        """Add ``tags`` to the named machine in place (stage 93); False when
        no such machine stands. A runtime that cannot retag raises."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot retag a machine")

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

    # ------------------------------------------------- the image query (stage 106)
    def supported_query_keys(self) -> frozenset[str]:
        """The keys of the system's image-query vocabulary this runtime can
        translate (``contract.image.QUERY_KEYS``); ``validate`` refuses an
        entry that uses any other on this runtime. Empty: none."""
        return frozenset()

    def translate_image_query(self, query: ImageQuery) -> Any:
        """The system's query in this runtime's own words: whatever its
        query path and its packer data source consume. A runtime that
        cannot query vendor images raises."""
        raise NotImplementedError(f"{self.__class__.__name__} cannot translate an image query")

    # ------------------------------------------------- packer source hooks
    # (the second-cloud exploration, increment 1: the packer builder is provider-neutral;
    # the runtime plugin owns everything that names its packer plugin.)
    def packer_source_type(self) -> str:
        """The packer source/builder type this runtime bakes with
        (the type its packer plugin registers; each cloud plugin names its own)."""
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
        (one cloud's ``<region>:<image id>`` -> the image id; another's is the
        image name itself)."""
        return artifact_id.split(":")[-1] if artifact_id else artifact_id

    def packer_post_processor_blocks(self, image: Any, *, runtime: str, source_type: str, subconfig: Any,
                                     final_name: str) -> list[str]:
        """HCL lines for the post-processor blocks this runtime's packer
        plugin wants in the build block for ``image``, before the manifest
        (stage 103: the container runtime tags its committed image with the
        build's final name and the series' floating tag). Default: none --
        the clouds name their artifact in the source block itself."""
        return []

    def bake_ansible_vars(self, image: Any) -> dict[str, str]:
        """Ansible variables the ansible provisioner passes as
        ``--extra-vars`` for a bake of ``image`` on this runtime (stage 103:
        the container runtime's container-type ``ansible_connection`` and the
        build container's name as ``ansible_host``, the way packer's ansible
        provisioner documents for its container builder). Default: none; the
        clouds bake over SSH through packer's own adapter."""
        return {}

    def tool_environment(self) -> dict[str, str]:
        """Environment variables every tool a bake or an apply on this
        runtime runs needs on top of the caller's (stage 103: the container
        runtime's daemon-address or client-context variable, read by packer's
        container plugin and ansible's container connection alike). Default: none;
        the clouds' tools read the credentials the environment already has."""
        return {}

    def get_default_machine_type(self) -> str:
        return self.model.get_default_machine_type()

    # ------------------------------------------- asked of the class itself
    @classmethod
    def session_status(cls, settings: Mapping[str, Any], executables: Mapping[str, Any]) -> SessionStatus | None:
        """Default: the runtime needs no session the preflight can read."""
        return None

    @classmethod
    def classify_failure(cls, exc: BaseException) -> LoadFailureReport | None:
        """Default: no load-time failure is this runtime's to explain."""
        return None

    @classmethod
    def credential_environment_prefixes(cls) -> tuple[str, ...]:
        """Default: the runtime reads no credentials from the environment."""
        return ()

    @classmethod
    def secret_patterns(cls) -> Mapping[str, str]:
        """Default: the runtime's secrets have no shape the scan can name."""
        return {}

    # ------------------------------------------ the network facts (stage 127)
    # Two OPTIONAL hooks the core reaches through ``getattr`` (the contract's
    # protocol gains nothing): a loaded configuration never reaches a cloud,
    # so what an account answers a runtime's networking declaration with is
    # discovered ONLINE by a real run and by `validate --online` and recorded
    # in meta-state/runtime-facts.yaml, then adopted OFFLINE by every load.
    #: What a runtime plugin's two networking hooks are built from: the
    #: record entry an online check answers, and the problems a recorded
    #: entry leaves against the declaration (both in ``network_facts``; the
    #: kit re-exports them here, the one module a plugin reaches the kit by).
    recorded_network_facts = staticmethod(facts_of)
    network_coverage_problems = staticmethod(coverage_problems)

    def network_facts(self) -> dict[str, Any]:
        """ONLINE: check this runtime's networking declaration against its
        account and answer the FACTS the declaration resolved to -- the
        network a `default` resolved to, the declared subnet and security
        group ids that were checked, when -- small and public-safe (never the
        account's inventory). Default: nothing to record."""
        return {}

    def adopt_network_facts(self, facts: Mapping[str, Any]) -> list[str]:
        """OFFLINE: take the recorded facts (``{}`` when nothing was recorded
        for this runtime) into the model -- a `default` network becomes the
        recorded one -- and answer the problems a validator reports: a
        declaration the record does not cover. Default: nothing to adopt."""
        return []

    #: The package that ships this runtime's part of the image-source catalog
    #: (``<package>/data/image-sources.yml``, stage 125); None for a runtime
    #: that ships none. A plugin names the package; the core reads the file.
    image_source_package: str | None = None

    @classmethod
    def image_source_entries(cls) -> list[Mapping[str, Any]]:
        """The runtime's part of the image-source catalog: the entries of the
        file ``image_source_package`` ships, none when it names no package."""
        return packaged_entries_of(cls.image_source_package) if cls.image_source_package else []

    @classmethod
    def local_test_target(cls) -> Callable[..., Any] | None:
        """Default: the runtime offers no local target for modification tests."""
        return None

    # ---------------------------------------------------------- V2 contract
    def session_mechanism(self) -> str | None:
        """The cloud's session-based debug access (N9: "the first cloud's
        session manager or each cloud's equivalent"), if this runtime is
        configured for it. None =
        no session mechanism; the admin key is then the only debug path."""
        return None

    def session_agent_commands(self, os_family: str | None = None) -> list[str]:
        """Shell commands that bake the session agent into a base image."""
        return []

    def session_verify_commands(self, os_family: str | None = None) -> list[str]:
        """Shell assertions proving the session agent is baked."""
        return []

    def launch_delivery(self) -> str:
        """How an instance's launch script reaches a machine on this runtime
        (stage 103 branch 2): ``boot`` (the default: the platform runs it at
        first boot -- a cloud's user data or startup script) or ``session``
        (the system runs it through ``run_session_command`` after the apply,
        exactly as it runs the accounts script; a container has no first
        boot). The script itself is the same on both."""
        return LAUNCH_DELIVERY_BOOT

    def bake_settle_commands(self, os_family: str | None = None) -> list[str]:
        """Shell commands emitted in the FIRST provisioner of every bake on
        this runtime, before any package work (stage 86): wait, bounded,
        for whatever this cloud does to a NEW machine on its own -- fleet
        management that updates agents, scans for patches or takes
        inventory uses the package database the bake is about to use. The
        commands must end on their own; a bound reached is said and the
        bake goes on. Default: none."""
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
        the cloud (read-only) -- the boot disk's source image on one cloud,
        the machine's image id on another. Used to bind an instance's pin from reality when its
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
        each cloud's own state field and spelling -- mapped onto the vocabulary
        in ``power_state`` so no caller reads a cloud's spelling (stage 57).

        ``None`` means THIS RUNTIME CANNOT ANSWER, which is never the same as
        ``STOPPED``: an instance the operator switched off is in the state
        they chose, while None is the absence of knowledge. Conflating the
        two is the bug this hook exists to end -- ``query_instance_boot_image``
        answers None for a stopped machine and for an unreachable cloud
        alike, because the probe behind it filters on ``running``."""
        return None

    def can_query_instance_identity(self) -> bool:
        """Whether this runtime implements query_instance_identity (stage
        58). Same gate shape as the power-state pair."""
        return False

    def query_instance_identity(self, instance_name: str) -> dict[str, str] | None:
        """The provider's own names for the machine: ``{"instance_id",
        "provider_hostname"}`` -- one cloud's instance id and private DNS name
        (an address-derived ``ip-…`` name), another's numeric id and
        ``<name>.c.<project>.internal``. None when this runtime cannot answer
        or the machine is not there; no claim is made either way. Read from
        the provider, never inferred, and never recorded in the launch
        parameters (they are what the machine booted with, and these are
        discovered afterwards)."""
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

    def default_bake_user(self, family: str) -> str | None:
        """The last step of the bake-user order (stage 63 item 22, see
        ``cs_image_system.base.bake_user``): the user a build VM of this OS
        family is reached as on this runtime when nothing names one. None =
        this runtime cannot say, and the resolver refuses."""
        return None

    def label_key_problem(self, key: str) -> str | None:
        """Why a declared tag key cannot become a label on this runtime, or
        None (stage 63). Default: any key is fine (the first cloud's tags take anything)."""
        return None

    def image_name_problem(self, name: str) -> str | None:
        """Why a build's full name (``<prefix>-<timestamp>``) cannot be an
        image name on this runtime, or None (stage 105). Default: any name
        is fine. The runtime that shortens or rewrites names reports what
        it would make of one through ``image_name_as_made`` instead."""
        return None

    def image_name_as_made(self, name: str) -> str:
        """What this runtime makes of a build name (stage 105): the name
        itself by default; one cloud lowercases, replaces what it cannot keep and
        shortens. ``validate`` compares images' prefixes AS MADE, so two
        names that collapse to one here are refused before a bake."""
        return name

    def one_bake_user_per_chain(self) -> bool:
        """Whether every image of a chain must bake as the SAME user on this
        runtime (one cloud, finding 43: its guest agent removes a stale other-name
        user at boot and, when that fails, aborts metadata key setup). When
        True, ``validate`` refuses a chain whose images resolve differently."""
        return False

    def bake_ssh_username(self, image=None) -> str | None:
        """The ssh user packer's build VM is reached as on this runtime, for
        provisioners that must name it explicitly (the ansible provisioner
        otherwise defaults to the operator's LOCAL login — finding 48).
        None = provisioners keep their own default (the first cloud's path, unchanged).
        A runtime that returns a user returns the RESOLVED one for ``image``
        (stage 63 item 23), the same the packer source bakes as."""
        return None

    def release_commands(self, build_id: str, tags: dict[str, str]):
        """Executables that mark a built artifact as released in the cloud
        (e.g. tag the image). Default: none."""
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
        psi = self.provider_specific_image_class().resolved(
            source_name=source_name,
            source_kind=source_kind,
            runtime=self.get_name(),
            identifier=identifier,
            owner=owner,
            raw_query_result=raw_query_result,
            architecture=architecture,
        )
        self._run_context().reg.register_built_instance(psi)
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
        psi = self.provider_specific_image_class().deferred(
            source_name=image.get_name(),
            source_kind=source_kind,
            runtime=self.get_name(),
            deferred_name_pattern=subconfig.get_image_output_name(),
            architecture=(architecture if architecture is not None
                          else getattr(image, "architecture", None)),
        )
        self._run_context().reg.register_built_instance(psi)
        log.debug(f"Registered deferred provider-specific image {psi.get_name()} "
                  f"with pattern {psi.deferred_name_pattern}")
        return psi
