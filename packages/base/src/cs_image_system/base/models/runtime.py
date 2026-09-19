# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from collections.abc import Mapping
import logging
from typing import Any


from cs_image_system.base.helpers.field_helpers import fk_field
log = logging.getLogger(__name__)
from ..constants import OOPS_DEFAULTS, VCT
from .builder_model import BuilderModel
from ..constants import DEFAULT
from dataclasses import field
from .credentials import CredentialsBase
from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class RuntimeSubnetModel:
    name: str
    subnet_id: str
    is_default: bool = False
    public: bool = False
    cidr: str | None = None
    # stage 52: the zone this subnet is in. Declared, never inferred -- it is
    # what lets a zone mismatch be refused at validate instead of discovered
    # as a volume replacement at apply.
    availability_zone: str | None = None
    config: dict[str, Any] = field(default_factory=dict)

    def get_name(self) -> str:
        return self.name
    def get_subnet_id(self) -> str:
        return self.subnet_id
    def get_availability_zone(self) -> str | None:
        return self.availability_zone
    def get_is_default(self) -> bool:
        return self.is_default
    def get_public(self) -> bool:
        return self.public
    def get_cidr(self) -> str | None:
        return self.cidr
    def get_config(self) -> Mapping[str, Any]:
        return self.config

    def __post_init__(self):
        # super().__post_init__() # Has no object parent
        if not self.name:
            self.name = self.subnet_id

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class RuntimeAvailabilityZoneModel:
    """ We're using Amazon's terminology of AZs here, but it's really just a named location
    for the runtime provider. """
    name: str
    is_default: bool = False
@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class RuntimeNetworkingModel:
    """Networking configuration data object."""
    name: str = DEFAULT
    network: str = DEFAULT
    subnets: list[RuntimeSubnetModel] = field(default_factory=list)
    availability_zones: list[RuntimeAvailabilityZoneModel] = field(default_factory=list)


    def __post_init__(self):
        # super().__post_init__() # Has no object parent
        if not self.network:
            raise ValueError("RuntimeNetworkingModel must have a network specified.")
        if not self.name or self.name in OOPS_DEFAULTS:
            self.name = self.network
        if not self.subnets:
            raise ValueError(f"RuntimeNetworkingModel for network {self.network} "
                      " has no subnets defined. ")
        else:
            dsub = None
            for subnet in self.subnets:
                if subnet.get_is_default():
                    log.info(f"Subnet {subnet.get_name()} is set as the default subnet for network {self.network}.")
                    dsub = subnet
                    break
        if not dsub:
            raise ValueError(f"No default subnet defined for network {self.network}.")
    
    @property
    def default_subnet(self) -> RuntimeSubnetModel:
        """Get the default subnet from the list of subnets."""
        for subnet in self.subnets:
            if subnet.get_is_default():
                return subnet
        raise ValueError(f"No default subnet defined for network {self.network}.")  

    @property
    def default_subnet_id(self) -> str:
        """Get the default subnet ID from the list of subnets."""
        return self.default_subnet.get_subnet_id()
    
    @property
    def default_availability_zone(self) -> str | None:
        """Get the default availability zone from the list of availability zones."""
        for az in self.availability_zones:
            if az.is_default:
                return az.name
        return None

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class RuntimeBuilderModel(BuilderModel):
    """Runtime provider configuration data object."""
    default_machine_type: str # reqired field
    # stage 22.1: this was `init=False`, so cattrs never structured it and the
    # YAML value (`default_image_builder: pckr-ebs-ans`) never reached any
    # runtime -- every one of them silently held DEFAULT. Both cloud plugins
    # read it through get_default_image_builder(), so AWS and GCE were equally
    # affected. It is an ordinary init field now.
    default_image_builder: str = fk_field(target = VCT.IMAGE_BUILDER_MODEL,
                                          default=DEFAULT,
                                          metadata={
                                              "description": "The default image builder",
                                              "required": True,
                                          })
    default_owners: list[str] | None = None 
    # stage 17: a declared object, not an opaque mapping. Each provider
    # narrows this to its own subclass, so an unknown key inside
    # `credentials:` is a validation error rather than a silent drop.
    credentials: CredentialsBase = field(default_factory=CredentialsBase)
    default_config_username: str | None = None
    # Declared ephemerality (stage 10.4): nothing baked on this runtime survives a
    # successful run -- the closing `retention` lifecycle disposes every image
    # here regardless of per-image retention. Declared storages are NEVER
    # touched (stage 10.15). retention_keep is the runtime-level default for
    # images that declare no retention of their own (None = keep everything).
    ephemeral: bool = False
    retention_keep: int | None = None
    # Runtime-level defaults for the ephemeral failure policy (stage 11.3).
    on_failure: str | None = None
    teardown_after: str | None = None
    
    def __post_init__(self) -> None:        
        if not self.default_machine_type:
            raise ValueError(f"Runtime builder {self.name} must have a default machine type specified.")
        return super().__post_init__()
    
    def get_default_image_builder(self) -> str:
        return self.default_image_builder
    def get_default_machine_type(self) -> str:
        return self.default_machine_type
    def get_default_owners(self) -> list[str] | None:
        return self.default_owners
    def get_credentials(self) -> dict[str, str]:
        return self.credentials.as_dict()
    def get_default_config_username(self) -> str | None:
        return self.default_config_username
    def update_networking(self) -> None:
        return # No-op by default
    
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.RUNTIME_BUILDER_MODEL




