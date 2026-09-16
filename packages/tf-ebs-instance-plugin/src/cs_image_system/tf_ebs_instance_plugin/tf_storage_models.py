# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.constants import DEFAULT, VCT
from cs_image_system.base.helpers.field_helpers import fk_field
from cs_image_system.base.models.module_variables import ModuleVariables
from cs_image_system.base.models.storage_builder import StorageBuilderModel
from cs_image_system.hashicorp_utils.hashicorp_models import TFTofuPluginModel


TF_AWS: str = "tf-aws"
TF_AWS_EBS = TF_AWS + "-ebs"
TF_AWS_EFS = TF_AWS + "-efs"
TF_AWS_S3 = TF_AWS + "-s3"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuStorageBuilderModel(StorageBuilderModel):
    """OpenTofu IaC storage builder configuration data object."""
    type = TF_AWS
    executable: str | None = "tofu"
    required_plugins: list[TFTofuPluginModel] = field(default_factory=list)
    state_configuration: str = fk_field(target=VCT.STATE_BACKEND_MODEL,
                                        default=DEFAULT, metadata={
        "description": "State backend used for this builder's terraform workspace",
    })
    # stage 26: declared inputs to the module call; each provider narrows the type
    variables: ModuleVariables = field(default_factory=ModuleVariables)


    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS
@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class EbsVariables(ModuleVariables):
    """tfmodules/aws_storage_ebs: the tunables not derived from the storage
    item (name, placement and the restore snapshot are computed)."""
    volume_type: str | None = None
    encrypted: bool | None = None


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class EfsVariables(ModuleVariables):
    """tfmodules/aws_storage_efs: access points, lifecycle transitions and
    public_read come from the storage item."""
    performance_mode: str | None = None
    encrypted: bool | None = None


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class S3Variables(ModuleVariables):
    """tfmodules/aws_storage_s3: bucket name, prefixes, lifecycle rules and
    public_read come from the storage item."""
    force_destroy: bool | None = None


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuEbsStorageBuilderModel(TofuStorageBuilderModel):
    """OpenTofu IaC builder configuration data object for EBS."""
    type = TF_AWS_EBS
    size: int = 100          # GB (a field since stage 26; was an untyped class attribute)
    variables: EbsVariables = field(default_factory=EbsVariables)

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_EBS

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuEfsStorageBuilderModel(TofuStorageBuilderModel):
    """OpenTofu IaC builder configuration data object for EFS."""
    type = TF_AWS_EFS
    variables: EfsVariables = field(default_factory=EfsVariables)
    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_EFS


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuS3StorageBuilderModel(TofuStorageBuilderModel):
    """OpenTofu IaC builder configuration data object for S3."""
    bucket_name: str
    type = TF_AWS_S3
    variables: S3Variables = field(default_factory=S3Variables)
    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_S3
    
    def get_bucket_name(self) -> str:
        return self.bucket_name

