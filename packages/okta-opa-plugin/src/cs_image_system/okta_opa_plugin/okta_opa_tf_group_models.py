# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from .okta_tf_models import OKTATF, OKTATF_RO, OktaGroupBuilderModel
from .okta_tf_workspace import OktaTfWorkspaceModelMixin


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OktaTfGroupBuilderModel(OktaTfWorkspaceModelMixin, OktaGroupBuilderModel):
    """The okta-tf group builder model: an oktapam terraform root.

    All workspace/credential machinery (register_hcl_requirements,
    transform_provider, finalize) comes from OktaTfWorkspaceModelMixin.
    """
    type = OKTATF

    @classmethod
    def csis_name(cls) -> str:
        return OKTATF


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OktaTfGroupRoBuilderModel(OktaTfGroupBuilderModel):
    """Read-only variant: data-source lookups of existing Okta groups only.

    Instances declare okta/okta in required_providers (not oktapam) -- the
    lookups target the Okta org itself.
    """
    type = OKTATF_RO

    @classmethod
    def csis_name(cls) -> str:
        return OKTATF_RO
