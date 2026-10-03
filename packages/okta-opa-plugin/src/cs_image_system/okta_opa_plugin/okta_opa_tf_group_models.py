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
    # stage 75: the posix group builder that creates this builder's groups on
    # the machines of their images. REQUIRED and without a default: a group
    # builder's name, or `none` for no posix configuration. Read as written by
    # the builder's configuration_errors (absent or null is refused; `none` is
    # the opt-out), not as a foreign key, which refuses `none` (stage 76).
    posix: str | None = None
    # stage 75: opt-in -- the login hook also installs each member's declared
    # `public_keys:` as their authorized_keys (a key path beside OPA's certificates)
    posix_ssh_keys: bool = False

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
