# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The ``gcs`` state backend type (stage 47.4): a Google Cloud Storage bucket.

OpenTofu's ``gcs`` backend stores a workspace's state as
``<prefix>/<terraform workspace>.tfstate``, the terraform workspace being
``default`` for every root this system emits, so a root's own prefix is the
declared prefix with the root's safe name appended: two roots never share an
object. Credentials are a PATH (``credentials``) or an impersonated service
account, never a value. Declaring the type binds nothing: the standing
decision keeps every live root, the GCE roots included, on the S3 backend.
"""
from __future__ import annotations

from typing import Any, Mapping

from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.constants import VCT
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from cs_image_system.base.models.state_builder import StateBuilderModel
from cs_image_system.base.utils import super_safe_name
from cs_image_system.hashicorp_utils.collector import BackendRegistration, StateLocation, TerraformCollector

GCS_STATE: str = "gcs"
DEFAULT_TERRAFORM_WORKSPACE = "default"


class GcsBackendKind:
    """The gcs type's renderings: the location is ``gcs://<bucket>/<prefix>/
    <root>/default.tfstate``; the backend file and a consumer's data source
    carry ``bucket`` and the root's ``prefix``, plus the credential path and
    the impersonated account when declared (the data source reads with the
    same identity as the producer)."""
    type = GCS_STATE

    @staticmethod
    def root_prefix(settings: Mapping[str, Any], workspace: str) -> str:
        return StateLocation.normalise_key(f"{settings.get('prefix') or ''}/{super_safe_name(workspace)}")

    def location(self, settings: Mapping[str, Any], workspace: str) -> StateLocation:
        return StateLocation(type=self.type, container=str(settings["bucket"]),
                             key=f"{self.root_prefix(settings, workspace)}/{DEFAULT_TERRAFORM_WORKSPACE}.tfstate")

    def _identity(self, settings: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if settings.get("credentials"):
            out["credentials"] = settings["credentials"]
        if settings.get("impersonate_service_account"):
            out["impersonate_service_account"] = settings["impersonate_service_account"]
        return out

    def backend_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]:
        out: dict[str, Any] = {"bucket": settings["bucket"], "prefix": self.root_prefix(settings, workspace)}
        out.update(self._identity(settings))
        for key in ("encryption_key", "kms_encryption_key"):
            if settings.get(key):
                out[key] = settings[key]
        return out

    def remote_state_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]:
        out: dict[str, Any] = {"bucket": settings["bucket"], "prefix": self.root_prefix(settings, workspace)}
        out.update(self._identity(settings))
        return out


GCS_KIND = GcsBackendKind()


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class GcsStateBuilderModel(StateBuilderModel):
    """A ``gcs`` entry under ``state_backends:``."""
    bucket: str
    prefix: str = "statefiles"
    credentials: str | None = None                  # a PATH to a credentials file, never a value
    impersonate_service_account: str | None = None
    encryption_key: str | None = None               # a customer-supplied key, from the environment in practice
    kms_encryption_key: str | None = None           # a Cloud KMS key name
    type = GCS_STATE
    # the executables entry these roots run; None = unspecified (no version
    # check), a declared name is checked like every builder's (stage 63)
    executable: str | None = None

    @classmethod
    def csis_name(cls) -> str:
        return GCS_STATE

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STATE_BACKEND_MODEL

    def __post_init__(self) -> None:
        if not self.bucket or not self.bucket.strip():
            raise ValueError("Terraform state backend 'bucket' cannot be empty for 'gcs' type.")
        self.bucket = self.bucket.strip()
        self.prefix = self.prefix.strip().strip("/")
        super().__post_init__()

    def to_backend_registration(self) -> BackendRegistration:
        return BackendRegistration(
            name=self.name, type=self.type_, kind=GCS_KIND, is_default=self.get_is_default(),
            aliases=tuple(sorted(self.aliases or ())),
            settings={"bucket": self.bucket, "prefix": self.prefix, "credentials": self.credentials,
                      "impersonate_service_account": self.impersonate_service_account,
                      "encryption_key": self.encryption_key, "kms_encryption_key": self.kms_encryption_key})

    def get_state_file_path(self, builder_name: str) -> str:
        return self.to_backend_registration().state_file_path(builder_name)

    def finalize(self) -> None:
        if self._finalized:
            return
        super().finalize()
        TerraformCollector().register_backend(self.to_backend_registration())
