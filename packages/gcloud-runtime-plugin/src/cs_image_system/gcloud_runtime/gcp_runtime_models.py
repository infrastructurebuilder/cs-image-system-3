# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Any

import logging

from cs_image_system.gcloud_runtime import gcp_utils
from cs_image_system.base.helpers.field_helpers import fk_field
log = logging.getLogger(__name__)


from cs_image_system.base.constants import DEFAULT, OOPS_DEFAULTS, VCT
from cs_image_system.base.models.cloud_builder import CloudBuilderModel, CloudNetworkingConfig


GCP: str = "gcloud"

@dataclass(config=CSIS_MODEL_CONFIG)
class GCPCloudNetworkingModel(CloudNetworkingConfig):
    """GCP-specific networking configuration data object."""
    # Network tags select which firewall rules apply to an instance -- the
    # closest GCP analog to AWS security group ids.
    network_tags: list[str] = field(default_factory=list)

    _model_id: str | None = fk_field(target=VCT.RUNTIME_BUILDER_MODEL,
                                     init=False,
                                     default=None, metadata={
                "description": "The name of the runtime model this object is associated with",
            })

    def __post_init__(self) -> None:
        super().__post_init__()
        self.name = self.name.strip()
        if not self.name:
            raise ValueError(f"Networking configuration name cannot be empty for {self}.")

    def get_name(self) -> str:
        return self.name
    def get_subnet_id(self) -> str:
        if not self.default_subnet_id:
            raise ValueError(f"Subnet ID is required for GCP networking configuration {self.name} but is not set.")
        return self.default_subnet_id
    def get_network_tags(self) -> list[str]:
        return self.network_tags


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class GCPCloudBuilderModel(CloudBuilderModel):
    """GCP cloud provider configuration data object."""
    type = GCP
    # stage 63 item 14: the cfg/executables.yml entry every gcloud call on
    # this runtime runs through (the session command, the inventory, the
    # storage lookups and the generated archive/wipe scripts), as the tofu
    # builders name theirs. `validate` refuses a name that is not declared.
    executable: str | None = "gcloud"
    project_id: str | None = None
    zone: str | None = None
    # Service account ATTACHED to build VMs and instances (config, never a
    # code literal). Without it packer attaches the project's default
    # compute SA, which a least-privilege runner cannot actAs (found live).
    service_account_email: str | None = None
    # Bake disk size in GB for every image baked on this runtime (finding
    # 51): a GCE instance's boot disk is exactly its image's disk, and the
    # OS-builder-level default (200 GB, a RHEL vendor minimum carried
    # forward) cost ~$8/month per instance. None = the image's own value.
    default_disk_size: int | None = None
    # Bake build VMs as preemptible (spot) instances: 60-90 % off bake minutes;
    # a preempted bake simply re-runs (GCP-READINESS §6).
    bake_preemptible: bool = False
    state_configuration: str = fk_field(target=VCT.STATE_BACKEND_MODEL,
                                        default = DEFAULT,
                                        metadata={
                                            "description": "The state manager this config uses",
                                            "required": True,
                                        })
    ssh_username: str = DEFAULT # Currently override when needed. (How do we get this?  From the image?)
    # Debug session mechanism (V2 §3F1 parity): only "iap" is supported.
    session_mechanism: str | None = None
    networking: GCPCloudNetworkingModel | None = None # type: ignore #Overrides parent
    network_map: dict[str, dict[str, list[dict]]] | None = field(init=False, default=None)
    default_network: str | None = field(init=False, default=None)
    all_firewall_rules: dict[str, dict] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()

    def finalize(self):
        if self._finalized:
            return
        super().finalize()
        self.update_networking()

    @classmethod
    def csis_name(cls) -> str:
        return GCP

    def self_to_gcp_client_config(self) -> dict[str, Any]:
        """Convert the builder model to a configuration dictionary for GCP client libraries."""
        config: dict[str, Any] = {}
        if self.credentials:
            config["credentials"] = self.get_credentials()
        if self.project_id:
            config["project"] = self.project_id
        if self.region:
            config["region"] = self.region
        if self.zone:
            config["zone"] = self.zone
        return config

    def update_networking(self) -> None:
        """ Get the network map, default network and firewall rules for the GCP project and validate the networking configuration. """
        session_config = self.self_to_gcp_client_config()
        if not session_config:
            raise ValueError("Session configuration cannot be None or empty")
        if not gcp_utils.resolve_project(session_config):
            log.warning(f"No usable GCP project could be resolved for cloud builder {self.get_display_name()} (no `project_id` declared on the runtime). Skipping network validation; image resolution and build execution will not work until valid GCP credentials are configured.")
            return

        network_map, default_network, allfw = gcp_utils.get_network_map_and_default_network(session_config)
        self.network_map = network_map
        self.default_network = default_network
        self.all_firewall_rules = allfw

        if not self.networking:
            log.warning(f"No networking configuration provided for GCP cloud builder {self.get_display_name()}. This is required for image resolution and build execution. Please provide a networking configuration.")
            return
        if self.networking.network in OOPS_DEFAULTS:
            if not default_network:
                errstr = f"No network specified in networking configuration for GCP cloud builder {self.name}, and no 'default' network found in GCP project. A network is required for image resolution and build execution. Please specify a network in the networking configuration or ensure a default network exists in the GCP project."
                log.error(errstr)
                raise ValueError(errstr)
            self.networking.network = default_network
        if self.networking.network not in self.network_map:
            errstr = f"Network {self.networking.network} specified in networking configuration for GCP cloud builder {self.name} not found in GCP project."
            log.error(errstr)
            raise ValueError(errstr)
        # Validate configured subnets against the project's subnetworks (match
        # by name, full self_link, or projects/... path suffix).
        known_subnets: set[str] = set()
        for sn in self.network_map[self.networking.network]["subnets"]:
            known_subnets.add(str(sn.get("subnet_id")))
            self_link = str(sn.get("self_link", ""))
            if self_link:
                known_subnets.add(self_link)
                known_subnets.add(self_link.split("//compute.googleapis.com/")[-1])
                # the canonical path form terraform uses (found live: the
                # real API's self_link host is www.googleapis.com/compute/v1,
                # so the split above never yields projects/...)
                if "/compute/v1/" in self_link:
                    known_subnets.add(self_link.split("/compute/v1/", 1)[-1])
        for subnet in self.networking.subnets:
            sid = subnet.get_subnet_id()
            if sid not in known_subnets:
                errstr = f"Subnetwork {sid} specified in networking configuration for GCP cloud builder {self.name} not found in network {self.networking.network}."
                log.error(errstr)
                raise ValueError(errstr)
        # Firewall rules apply via network tags; warn on tags no rule targets.
        all_target_tags: set[str] = set()
        for fw in self.all_firewall_rules.values():
            all_target_tags.update(fw.get("target_tags", []) or [])
        for tag in self.networking.network_tags:
            if tag not in all_target_tags:
                log.warning(f"Network tag {tag} specified in networking configuration for GCP cloud builder {self.name} is not targeted by any firewall rule in the GCP project.")
