# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.constants import VCT

from .okta_tf_models import OKTATF, OKTATF_RO, OktaUserBuilderModel
from .okta_tf_workspace import OktaTfWorkspaceModelMixin


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OktaTfUserBuilderModel(OktaTfWorkspaceModelMixin, OktaUserBuilderModel):
    """The okta-tf user builder model: an okta/okta terraform root."""
    type = OKTATF

    @classmethod
    def csis_name(cls) -> str:
        return OKTATF

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.USER_BUILDER_MODEL


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OktaTfUserRoBuilderModel(OktaTfUserBuilderModel):
    """Read-only variant: data-source lookups of existing Okta users only."""
    type = OKTATF_RO

    @classmethod
    def csis_name(cls) -> str:
        return OKTATF_RO
