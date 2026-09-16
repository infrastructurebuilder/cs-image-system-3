# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.constants import VCT
from cs_image_system.base.models.state_builder import StateBuilderModel
from cs_image_system.hashicorp_utils.hashicorp import AssumeRoleConfig, AssumeRoleWithWebIdentityConfig, StateEndpoints
from cs_image_system.hashicorp_utils.collector import BackendRegistration, TerraformCollector
from cs_image_system.hashicorp_utils.hashicorp_models import TFTofuPluginModel


TF_AWS_S3_STATE: str = "s3"

HASHICORP_S3 = "s3-state"

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuS3StateBuilderModel(StateBuilderModel):
    """OpenTofu IaC state builder configuration data object."""
    bucket: str
    key: str
    type = TF_AWS_S3_STATE
    executable: str | None = "tofu"
    required_plugins: list[TFTofuPluginModel] = field(default_factory=list)
    # type = HASHICORP_S3
    region: str = "us-east-2"
    encrypt: bool = False
    use_lockfile: bool = True
    allowed_account_ids: list[str] = field(default_factory=list)
    forbidden_account_ids: list[str] = field(default_factory=list)
    http_proxy: str | None = None
    https_proxy: str | None = None
    no_proxy: list[str] = field(default_factory=list)
    insecure: bool = False
    max_retries: int = 5
    profile: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    shared_config_file: str | None = None
    shared_credentials_file: str | None = None
    skips_credentials_validation: bool = False
    skip_region_validation: bool = False
    skip_requesting_account_id: bool = False
    skip_metadata_api_check: bool = False
    skip_s3_checksum: bool = False
    use_dualstack_endpoint: bool = False
    use_fips_endpoint: bool = False
    endpoints: StateEndpoints | None = None
    assume_role: AssumeRoleConfig | None = None
    assume_role_with_web_identity: AssumeRoleWithWebIdentityConfig | None = None
    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_S3_STATE
    
    # def __init__(self, *args ,**kwargs: Any) -> None:
    #     super().__init__(*args, **kwargs)


    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STATE_BACKEND_MODEL

    def __post_init__(self) -> None:
        if self.key:
            self.key = self.key.rstrip("/")
            self.key = f"{self.key}/"
        else:
            raise ValueError("Terraform state backend 'key' cannot be empty for 's3' type.")
        super().__post_init__()

    def to_backend_registration(self) -> BackendRegistration:
        return BackendRegistration(
            name=self.name,
            type=self.type_,
            bucket=self.bucket,
            region=self.region,
            key_prefix=self.key,
            encrypt=self.encrypt,
            use_lockfile=self.use_lockfile,
            profile=self.profile,
            is_default=self.get_is_default(),
        )

    def get_state_file_path(self, builder_name: str) -> str:
        return self.to_backend_registration().state_file_path(builder_name)

    def finalize(self) -> None:
        if self._finalized:
            return
        super().finalize()
        # Make this backend available run-wide: consumers (instance/storage/
        # okta workspaces) resolve it from the collector by name or as the
        # default. Model finalize happens at config load, before any
        # generation phase, so every consumer sees the registration.
        TerraformCollector().register_backend(self.to_backend_registration())
