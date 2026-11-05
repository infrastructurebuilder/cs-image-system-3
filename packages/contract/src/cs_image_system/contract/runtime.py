# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The runtime kind (stage 30): a cloud or container context every other
builder operates in. The model carries the defaults and the credentials;
the builder answers the queries, sessions, bakes, power states and image
disposal the core asks a runtime for, translates the system's image query
into its own words (stage 106), and makes the provider-specific images (the
resolved or deferred reference to an image on this runtime).
Stage 103 adds the container runtime's model protocol beside the cloud's,
and two bake hooks: the post-processor blocks a runtime's packer plugin
wants in the build (the container runtime tags its committed image) and the
ansible variables a bake on it connects with (``ansible_connection``);
its second branch adds ``launch_delivery``: whether the platform runs the
launch script at first boot (a cloud's user data) or the system delivers it
through the session after the apply (a container has no first boot).
Items of other kinds (images, subconfigs, provider-specific images) are
``Any`` here: their protocols are a later stage."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from .core import BuilderModelProtocol, BuilderProtocol
from .image import ImageQuery, PSISourceKind
from .session import SessionStatus

#: How an instance's launch script reaches the machine (stage 103 branch 2):
#: ``boot`` -- the platform runs it at first boot (a cloud's user data or
#: startup script); ``session`` -- the system runs it through the runtime's
#: session after the apply, as it runs the accounts script.
LAUNCH_DELIVERY_BOOT = "boot"
LAUNCH_DELIVERY_SESSION = "session"


class RuntimeBuilderModelProtocol(BuilderModelProtocol, Protocol):
    """An entry under ``runtime_builders:``."""

    default_machine_type: str
    default_image_builder: str
    default_owners: list[str] | None
    credentials: Any
    default_config_username: str | None
    ephemeral: bool
    retention_keep: int | None
    on_failure: str | None
    teardown_after: str | None

    def get_default_image_builder(self) -> str: ...

    def get_default_machine_type(self) -> str: ...

    def get_default_owners(self) -> list[str] | None: ...

    def get_credentials(self) -> dict[str, str]: ...

    def get_default_config_username(self) -> str | None: ...

    def update_networking(self) -> None: ...


class CloudBuilderModelProtocol(RuntimeBuilderModelProtocol, Protocol):
    """A cloud runtime: a region and a networking block (``networking``:
    the network, its subnets and availability zones)."""

    region: str
    networking: Any

    def get_region(self) -> str: ...

    def get_networking(self) -> Any: ...


class ContainerBuilderModelProtocol(RuntimeBuilderModelProtocol, Protocol):
    """A container runtime (stage 103): a durable host running a daemon
    that speaks the container engine's API, reached by a ``host`` URL
    (``unix://``, ``ssh://``, ``tcp://`` with TLS) or a named client ``context``;
    a ``networking`` block that names a network and nothing more (no
    subnets, no zones); and a ``machine_types`` map from a name to the
    limits a container of that type runs under (``cpus``, ``memory``),
    one of which ``default_machine_type`` names."""

    host: str | None
    context: str | None
    networking: Any
    machine_types: Any

    def get_host(self) -> str | None: ...

    def get_context(self) -> str | None: ...

    def get_networking(self) -> Any: ...

    def get_machine_types(self) -> dict[str, Any]: ...


class RuntimeBuilderProtocol(BuilderProtocol, Protocol):
    """A runtime's builder. Every hook has a default in the core's
    ``RuntimeBuilderBase`` (most answer "cannot" or nothing); a plugin
    overrides what its cloud can do."""

    # --- images: the vendor query and the inventory
    def query_provider_image(self, os_builder: Any) -> tuple[str, str, Any] | None: ...

    def query_provider_image_by_id(self, os_builder: Any, image_id: str) -> tuple[str, str, Any] | None: ...

    def query_images(self, series: list[str]) -> list[dict[str, Any]]: ...

    def inventory(self) -> dict[str, Any]: ...

    def dispose_image(self, build_id: str) -> bool: ...

    def retag_image(self, image_id: str, tags: dict[str, str]) -> bool: ...

    def release_commands(self, build_id: str, tags: dict[str, str]) -> Any: ...

    # --- instances: tags, identity, boot image, power state
    def instance_tags(self, instance_name: str) -> dict[str, str] | None: ...

    def retag_instance(self, instance_name: str, tags: dict[str, str]) -> bool: ...

    def can_query_instance_boot_image(self) -> bool: ...

    def query_instance_boot_image(self, instance_name: str) -> str | None: ...

    def can_query_instance_identity(self) -> bool: ...

    def query_instance_identity(self, instance_name: str) -> dict[str, str] | None: ...

    def can_query_instance_power_state(self) -> bool: ...

    def query_instance_power_state(self, instance_name: str) -> str | None: ...

    def can_set_instance_power_state(self) -> bool: ...

    def start_instance(self, instance_name: str, timeout: int = 300) -> bool: ...

    def stop_instance(self, instance_name: str, timeout: int = 300) -> bool: ...

    # --- sessions and verification
    def verify_instance(self, instance_name: str, expected_build: str | None = None, expect_mounts: int = 0,
                        timeout: int = 600, mount_points: list[str] | None = None) -> dict[str, Any]: ...

    def ssh_proxy_command(self, instance_name: str) -> list[str] | None: ...

    def run_session_command(self, instance_name: str, script: str, timeout: int = 300) -> tuple[int, str]: ...

    def session_mechanism(self) -> str | None: ...

    def session_agent_commands(self, os_family: str | None = None) -> list[str]: ...

    def session_verify_commands(self, os_family: str | None = None) -> list[str]: ...

    def session_instance_profile(self) -> str | None: ...

    def launch_delivery(self) -> str: ...

    # --- bakes
    def bake_settle_commands(self, os_family: str | None = None) -> list[str]: ...

    def bake_finalize_commands(self, os_family: str | None = None) -> list[str]: ...

    def default_bake_user(self, family: str) -> str | None: ...

    def one_bake_user_per_chain(self) -> bool: ...

    def bake_ssh_username(self, image: Any = None) -> str | None: ...

    def label_key_problem(self, key: str) -> str | None: ...

    # --- the names of builds (stage 105)
    def image_name_problem(self, name: str) -> str | None: ...

    def image_name_as_made(self, name: str) -> str: ...

    # --- the image query (stage 106): the system's vocabulary, translated here
    def supported_query_keys(self) -> frozenset[str]: ...

    def translate_image_query(self, query: ImageQuery) -> Any: ...

    # --- packer and the provider-specific image
    def packer_source_type(self) -> str: ...

    def packer_source_blocks(self, image: Any, *, runtime: str, source_type: str, subconfig: Any, self_subconfig: Any,
                             psi: Any, tags: dict[str, str], final_name: str, pinned: str | None) -> list[str]: ...

    def build_id_from_artifact(self, artifact_id: str) -> str: ...

    # --- stage 103: what else a runtime's packer plugin needs in the build block
    def packer_post_processor_blocks(self, image: Any, *, runtime: str, source_type: str, subconfig: Any,
                                     final_name: str) -> list[str]: ...

    def bake_ansible_vars(self, image: Any) -> dict[str, str]: ...

    def tool_environment(self) -> dict[str, str]: ...

    def get_default_machine_type(self) -> str: ...

    def apply_specific_changes(self, image: Any) -> Any: ...

    def provider_specific_image_class(self) -> type[Any]: ...

    def create_provider_specific_image_resolved(self, *, source_name: str, source_kind: PSISourceKind, identifier: str,
                                                owner: str | None = None, raw_query_result: Any | None = None,
                                                architecture: str | None = None) -> Any: ...

    def create_provider_specific_image_deferred(self, *, image: Any, subconfig: Any,
                                                source_kind: PSISourceKind = PSISourceKind.IMAGE,
                                                architecture: str | None = None) -> Any: ...

    # --- what the core asks of the runtime's CLASS, before or without a tree
    @classmethod
    def session_status(cls, settings: Mapping[str, Any], executables: Mapping[str, Any]) -> SessionStatus | None:
        """The session a runtime declared by ``settings`` (the entry's keys
        as written, or the model's fields) will use: read from the
        credential caches, never a credential value; ``executables`` the
        tree's executables by name (a daemon probe reads its binary from
        them). ``None`` when the runtime needs no session."""
        ...

    @classmethod
    def credential_environment_prefixes(cls) -> tuple[str, ...]:
        """The prefixes of the environment variables this runtime reads
        credentials from (the preflight reports one that is set and
        empty, by name, never by value). Empty for a runtime that reads
        none."""
        ...

    @classmethod
    def secret_patterns(cls) -> Mapping[str, str]:
        """The shapes of this runtime's secrets that must never reach a
        public repository, as named regular expressions over text (an
        access key id's prefix and length, a service-account key id); the
        public-safety scan adds them to its own rules. Empty for a runtime
        whose secrets have no recognisable shape."""
        ...

    @classmethod
    def image_source_entries(cls) -> list[Mapping[str, Any]]:
        """The runtime's part of the release-owned image-source catalog:
        entries in the catalog's shape (``family``, ``sources`` keyed by
        this runtime's type, ``description``, ``is``, ``versions``), read
        from the plugin's package data. Empty for a runtime that ships
        none."""
        ...

    @classmethod
    def local_test_target(cls) -> Callable[..., Any] | None:
        """A factory for the local target the modification tests run on
        (``factory(image, executables) -> LocalTarget``), or ``None`` for a
        runtime that offers none. The catalog block the tests read is the
        one keyed by this runtime's type."""
        ...

    # --- wiring: the builders that operate in this runtime
    def add_image_builder(self, image: Any) -> None: ...

    def add_instance_builder(self, instance: Any) -> None: ...
