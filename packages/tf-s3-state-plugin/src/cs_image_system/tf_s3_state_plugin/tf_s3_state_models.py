# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field, fields
from typing import Any, Mapping

from pydantic import model_validator
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.constants import VCT
from cs_image_system.base.models.state_builder import StateBuilderModel
from cs_image_system.hashicorp_utils.collector import BackendRegistration, StateLocation, TerraformCollector


TF_AWS_S3_STATE: str = "s3"

HASHICORP_S3 = "s3-state"


class S3BackendKind:
    """The S3 backend type's renderings (stage 47.2): a workspace's state is the
    object ``<key prefix>/<workspace>.tfstate`` in the bucket; the partial
    configuration carries bucket, key, region, encrypt, use_lockfile and the
    profile; a consumer's data source carries bucket, key, region and the
    profile. The collector knows none of these names."""
    type = TF_AWS_S3_STATE

    def location(self, settings: Mapping[str, Any], workspace: str) -> StateLocation:
        return StateLocation.of(self.type, str(settings["bucket"]), settings.get("key_prefix"), workspace)

    def backend_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "bucket": settings["bucket"],
            "key": self.location(settings, workspace).key,
            "region": settings["region"],
            "encrypt": bool(settings.get("encrypt", False)),
            "use_lockfile": bool(settings.get("use_lockfile", True)),
        }
        if settings.get("profile"):
            out["profile"] = settings["profile"]
        out.update(settings.get("extra") or {})     # stage 63: every other declared backend argument
        return out

    def remote_state_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "bucket": settings["bucket"],
            "key": self.location(settings, workspace).key,
            "region": settings["region"],
        }
        if settings.get("profile"):
            out["profile"] = settings["profile"]
        out.update(settings.get("extra") or {})     # a consumer reads the state the same way
        return out


S3_KIND = S3BackendKind()

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class StateEndpoints:
    """The s3 backend's ``endpoints`` object: custom service endpoints."""
    dynamodb: str | None = None
    s3: str | None = None
    sts: str | None = None
    iam: str | None = None
    sso: str | None = None


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class AssumeRoleConfig:
    """The s3 backend's ``assume_role`` object."""
    role_arn: str
    duration: str | None = None
    external_id: str | None = None
    policy: str | None = None
    policy_arns: list[str] = field(default_factory=list)
    session_name: str | None = None
    source_identity: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    transitive_tag_keys: list[str] = field(default_factory=list)


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class AssumeRoleWithWebIdentityConfig:
    """The s3 backend's ``assume_role_with_web_identity`` object."""
    role_arn: str
    duration: str | None = None
    policy: str | None = None
    policy_arns: list[str] = field(default_factory=list)
    session_name: str | None = None
    web_identity_token: str | None = None
    web_identity_token_file: str | None = None


# stage 63 (decided 2026-09-25): every s3-backend argument the model declares
# is emitted when set -- into the backend file and into a consumer's
# terraform_remote_state -- instead of being accepted and read by nothing.
# Model field -> backend argument; a field at its default is not emitted, so a
# tree that declares none of them renders exactly as before.
_PASS_THROUGH: dict[str, str] = {
    "allowed_account_ids": "allowed_account_ids",
    "forbidden_account_ids": "forbidden_account_ids",
    "http_proxy": "http_proxy",
    "https_proxy": "https_proxy",
    "no_proxy": "no_proxy",
    "insecure": "insecure",
    "max_retries": "max_retries",
    "shared_config_file": "shared_config_files",
    "shared_credentials_file": "shared_credentials_files",
    "skip_credentials_validation": "skip_credentials_validation",
    "skip_region_validation": "skip_region_validation",
    "skip_requesting_account_id": "skip_requesting_account_id",
    "skip_metadata_api_check": "skip_metadata_api_check",
    "skip_s3_checksum": "skip_s3_checksum",
    "use_dualstack_endpoint": "use_dualstack_endpoint",
    "use_fips_endpoint": "use_fips_endpoint",
    "endpoints": "endpoints",
    "assume_role": "assume_role",
    "assume_role_with_web_identity": "assume_role_with_web_identity",
}

# keys refused at load, each with what to do instead
_REFUSED: dict[str, str] = {
    "access_key": "credentials never live in the configuration tree; name a `profile` (or use "
                  "`assume_role`) and let the AWS SDK find the keys",
    "secret_key": "credentials never live in the configuration tree; name a `profile` (or use "
                  "`assume_role`) and let the AWS SDK find the keys",
    "skips_credentials_validation": "the backend argument is `skip_credentials_validation` "
                                    "(the old spelling was never read)",
    "required_plugins": "a state backend has no plugins; providers belong to the roots",
}


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuS3StateBuilderModel(StateBuilderModel):
    """An ``s3`` entry under ``state_backends:``: the backend block's
    arguments. bucket/key/region/encrypt/use_lockfile/profile are the core;
    every other field is a terraform s3-backend argument passed through when
    set (stage 63)."""
    bucket: str
    key: str
    type = TF_AWS_S3_STATE
    # the executables entry this backend's roots run; None = unspecified (no
    # version check), a declared name is checked like every builder's
    executable: str | None = None
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
    shared_config_file: str | None = None
    shared_credentials_file: str | None = None
    skip_credentials_validation: bool = False
    skip_region_validation: bool = False
    skip_requesting_account_id: bool = False
    skip_metadata_api_check: bool = False
    skip_s3_checksum: bool = False
    use_dualstack_endpoint: bool = False
    use_fips_endpoint: bool = False
    endpoints: StateEndpoints | None = None
    assume_role: AssumeRoleConfig | None = None
    assume_role_with_web_identity: AssumeRoleWithWebIdentityConfig | None = None

    @model_validator(mode="before")
    @classmethod
    def _refuse_named_keys(cls, data: Any) -> Any:
        keys = data if isinstance(data, dict) else (getattr(data, "kwargs", None) or {})
        for key, why in _REFUSED.items():
            if key in keys:
                raise ValueError(f"state backend {keys.get('name', '<unnamed>')!r}: `{key}` is refused: {why}")
        return data

    def pass_through(self) -> dict[str, Any]:
        """The declared backend arguments beyond the core, as the backend
        wants them: only fields away from their default; the two singular
        file fields become the lists tofu takes; ``no_proxy`` a comma string;
        the nested objects mappings of their set members."""
        defaults = {f.name: f for f in fields(self)}
        out: dict[str, Any] = {}
        for attr, arg in _PASS_THROUGH.items():
            value = getattr(self, attr)
            f = defaults[attr]
            default = f.default_factory() if callable(getattr(f, "default_factory", None)) else f.default  # type: ignore[misc]
            if value is None or value == default:
                continue
            if attr in ("shared_config_file", "shared_credentials_file"):
                value = [value]
            elif attr == "no_proxy":
                value = ",".join(value)
            elif attr in ("endpoints", "assume_role", "assume_role_with_web_identity"):
                value = {k: v for k, v in vars(value).items()
                         if not k.startswith("_") and v not in (None, [], {})}
            out[arg] = value
        return out

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
            settings={
                "bucket": self.bucket,
                "region": self.region,
                "key_prefix": self.key,
                "encrypt": self.encrypt,
                "use_lockfile": self.use_lockfile,
                "profile": self.profile,
                "extra": self.pass_through(),
            },
            aliases=tuple(sorted(self.aliases or ())),
            kind=S3_KIND,
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
