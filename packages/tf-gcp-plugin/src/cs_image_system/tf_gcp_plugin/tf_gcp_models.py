# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""GCP storage and instance builder models (GCP increment 3, PLAN.md).

Same shape as the AWS tofu models: one terraform root per builder, a state
backend by reference (the S3 backend works for GCP roots too), and the
runtime builder supplies project/zone/network.
"""
from dataclasses import field

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from cs_image_system.base.models.module_variables import ModuleVariables
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.constants import VCT  # noqa: F401  (re-exported for symmetry)

from cs_image_system.tf_ebs_instance_plugin.tf_instance_models import TofuInstanceBuilderModel
from cs_image_system.tf_ebs_instance_plugin.tf_storage_models import TofuStorageBuilderModel

TF_GCP: str = "tf-gcp"
TF_GCP_PD = TF_GCP + "-pd"
TF_GCP_FILESTORE = TF_GCP + "-filestore"
TF_GCP_GCS = TF_GCP + "-gcs"
TOFU_GCE: str = "tofu-gce"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuGcpStorageBuilderModel(TofuStorageBuilderModel):
    type = TF_GCP

    @classmethod
    def csis_name(cls) -> str:
        return TF_GCP


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class GcpVariables(ModuleVariables):
    """The GCP modules' tunables not derived from the item or declared as a
    builder field (size, disk_type, tier, capacity_gb, location): builder-wide
    default labels, which the item's labels and the csis_* labels override.
    ``tags`` is the declared name; the builders emit them as ``labels``."""


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuPdStorageBuilderModel(TofuGcpStorageBuilderModel):
    """Persistent disk (EBS equivalent): single-attach, POSIX."""
    type = TF_GCP_PD
    size: int = 100          # GB
    disk_type: str = "pd-balanced"
    variables: GcpVariables = field(default_factory=GcpVariables)

    @classmethod
    def csis_name(cls) -> str:
        return TF_GCP_PD


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuFilestoreStorageBuilderModel(TofuGcpStorageBuilderModel):
    """Filestore (EFS equivalent): many-attach NFS, POSIX. Minimum 1 TiB."""
    type = TF_GCP_FILESTORE
    tier: str = "BASIC_HDD"
    capacity_gb: int = 1024
    variables: GcpVariables = field(default_factory=GcpVariables)

    @classmethod
    def csis_name(cls) -> str:
        return TF_GCP_FILESTORE


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuGcsStorageBuilderModel(TofuGcpStorageBuilderModel):
    """GCS bucket (S3 equivalent): many-attach object store, non-POSIX."""
    type = TF_GCP_GCS
    bucket_name: str
    location: str | None = None
    variables: GcpVariables = field(default_factory=GcpVariables)

    @classmethod
    def csis_name(cls) -> str:
        return TF_GCP_GCS


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuGceInstanceBuilderModel(TofuInstanceBuilderModel):
    type = TOFU_GCE

    @classmethod
    def csis_name(cls) -> str:
        return TOFU_GCE
