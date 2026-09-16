# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import json
import subprocess
from typing import TypeVar


from cs_image_system.base.basic.abstract_version_checker import AbstractVersionChecker
from cs_image_system.base.basic.builder_base_state import  StateBuilderBase

from .tf_s3_state_models import TF_AWS_S3_STATE,  TofuS3StateBuilderModel

Q = TypeVar("Q", bound=TofuS3StateBuilderModel)

class TofuS3StateBuilder(StateBuilderBase[Q]):
    """OpenTofu IaC provider implementation."""

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_S3_STATE
    
    # def generate_items_before(self, phase: ExecutionLifecyclePhase) -> AssetSet:
    #     return super().generate_items_before(phase)
    
class TofuVersionChecker(AbstractVersionChecker):
    """Version checker for OpenTofu."""

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_S3_STATE

    def get_version_params(self) -> list[str]:
        return ["--version", "-json"]

    def get_extracted_string(self, res: subprocess.CompletedProcess[str]) -> str | None:
        return json.loads(res.stdout.strip()).get("terraform_version", None)
