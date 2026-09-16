# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from ..constants import VCT
from .builder_model import BuilderModel


GROUP_BUILDER: str = "GroupBuilder"


BASIC_GROUP_BUILDER: str = "basic"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class GroupBuilderModel(BuilderModel):
    """Dataclass representing a local modification to be applied during image build.

    Attributes:
        name/type/executable:From BuilderModel
        source: Path to a source file or directory on the local filesystem.
    """
    # default_user_email_template: str = "{{ user.name }}"
    # default_user_description_template: str = "User {{ user.name }} / {{ user.email }}"
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.GROUP_BUILDER_MODEL


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class BasicGroupBuilderModel(GroupBuilderModel):
    """Dataclass representing an Ansible playbook modification.

    Attributes:
        playbooks: Playbooks that are prepended to the list of provided playbooks.
    """
