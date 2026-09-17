# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from cs_image_system.base.models.credentials import CredentialsBase
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Any

import logging

from cs_image_system.aws_runtime import aws_utils
from cs_image_system.base.helpers.field_helpers import fk_field
log = logging.getLogger(__name__)


from cs_image_system.base.constants import DEFAULT, OOPS_DEFAULTS, VCT
from cs_image_system.base.models.cloud_builder import CloudBuilderModel, CloudNetworkingConfig
from cs_image_system.base.models.group_builder import GroupBuilderModel


AWS: str = "aws"
AWS_CLI: str = "aws-cli"

@dataclass(config=CSIS_MODEL_CONFIG)
class AwsCloudNetworkingModel(CloudNetworkingConfig):
    """AWS-specific networking configuration data object."""
    security_group_ids: list[str] = field(default_factory=list)
    addl_security_groups: list[str]  = field(default_factory=list)
    # Security groups whose members may SSH into launched instances (e.g.
    # the Okta gateway relay). When set, the instance SG's port-22 ingress
    # references ONLY these groups -- no CIDR ranges (policy: never open
    # ingress to the shared networks' address space).
    ssh_ingress_security_group_ids: list[str] = field(default_factory=list)
    
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
            # import uuid
            # id = str(uuid.uuid4())
            # log.warning(f"Networking configuration name is empty or default for {self}."
            #             f"This may cause issues with identification and retrieval of this configuration. "
            #             f"Assigning a random UUID as name: {id}")
            # self.name = id

    def get_name(self) -> str:
        return self.name
    def get_subnet_id(self) -> str:
        if not self.default_subnet_id:
            raise ValueError(f"Subnet ID is required for AWS networking configuration {self.name} but is not set.")
        return self.default_subnet_id
    def get_security_group_ids(self) -> list[str]:
        return self.security_group_ids
    def get_addl_security_groups(self) -> list[str]:
        return self.addl_security_groups

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class AwsCredentials(CredentialsBase):
    """What an AWS runtime may declare. The names are boto3 session kwargs, so
    `self_to_aws_client_config` can pass them straight through.

    Values belong in the environment, not here: `profile_name` names a profile
    and the key fields carry `{{ ENV[...] }}` templates. Stage 17 makes the
    SHAPE checkable -- `profile_nme` is now an error instead of a silent None.
    """
    profile_name: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class AwsCloudBuilderModel(CloudBuilderModel):
    """AWS cloud provider configuration data object."""
    type = AWS
    account_id: str | None = None
    state_configuration: str = fk_field(target=VCT.STATE_BACKEND_MODEL, 
                                        default = DEFAULT, 
                                        metadata={
                                            "description": "The state manager this config uses",
                                            "required": True,
                                        })
    # profile: str | None = None  # This is for connetivity to AWS
    ena_support: bool | None = None
    sriov_support: bool | None = None
    iam_instance_profile: str | None = None
    # V2 debug access (N9): "ssm" bakes the SSM agent into base images and
    # (when session_instance_profile is set) attaches that profile to
    # launched instances so system-level operators can start a session.
    session_mechanism: str | None = None
    session_instance_profile: str | None = None
    ssh_username: str  = DEFAULT # Currently override when needed. (How do we get this?  From the image?)
    networking: AwsCloudNetworkingModel | None = None # type: ignore #Overrides parent
    vpc_map: dict[str, dict[str, list[str]]] | None = field(init=False, default=None)
    default_vpc_id: str | None = field(init=False, default=None)
    all_security_groups: dict[str, dict] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()        

    def finalize(self):
        if self._finalized:
            return
        super().finalize()
        self.update_networking()
    @classmethod
    def csis_name(cls) -> str:
        return AWS

    credentials: AwsCredentials = field(default_factory=AwsCredentials)

    def self_to_aws_client_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {}
        if self.credentials:
            config.update(self.get_credentials())
        # if self.profile:
        #     config["profile_name"] = self.profile
        if self.region:
            config["region_name"] = self.region
        return config
    def update_networking(self) -> None:
        """ Get the VPC map, default VPC and security groups for the AWS account and validate the networking configuration. """
        session_config = self.self_to_aws_client_config()
        if not session_config:
            raise ValueError("Session configuration cannot be None or empty")

        vpc_map, default_vpc_id, allsgs = aws_utils.get_vpc_map_and_default_vpc_id(session_config)
        self.vpc_map = vpc_map
        self.default_vpc_id = default_vpc_id
        self.all_security_groups = allsgs

        
        if not self.networking:
            log.warning(f"No networking configuration provided for AWS cloud builder {self.get_display_name()}. This is required for image resolution and build execution. Please provide a networking configuration.")
            return
        if self.networking.network in OOPS_DEFAULTS:
            if not default_vpc_id:
                errstr = f"No VPC ID specified in networking configuration for AWS cloud builder {self.name}, and no default VPC found in AWS account. A VPC ID is required for image resolution and build execution. Please specify a VPC ID in the networking configuration or ensure a default VPC exists in the AWS account."
                log.error(errstr)
                raise ValueError(errstr)
            self.networking.network = default_vpc_id
        if self.networking.network not in self.vpc_map:
            errstr = f"VPC ID {self.networking.network} specified in networking configuration for AWS cloud builder {self.name} not found in AWS account."
            log.error(errstr)
            raise ValueError(errstr)
        total_sgs = self.networking.security_group_ids + self.networking.addl_security_groups
        for sg in total_sgs:
            if sg not in self.all_security_groups:
                errstr = f"Security group ID {sg} specified in networking configuration for AWS cloud builder {self.name} not found in AWS account."
                log.error(errstr)
                raise ValueError(errstr)
        if len(total_sgs) > 5:
            errstr = f"Total number of security groups specified in networking configuration for AWS cloud builder {self.name} is {len(total_sgs)}, which may exceed limits for certain instance types. Please ensure this is intentional and does not exceed limits for your target instance types."
            log.error(errstr)
            raise ValueError(errstr)
            

        
            


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DummyGroupBuilderModel(GroupBuilderModel):
    """Dataclass representing an Dummy group configuration.

    Attributes:
        Dummy_group_id: The ID of the Dummy group.
    """

    org: str
    team: str
    key: str = DEFAULT # TODO: Secrets
    secret: str = DEFAULT
    api_host: str = DEFAULT

