# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction



from cs_image_system.base.models.group_builder import GroupBuilderModel
from cs_image_system.base.models.user_builder import UserBuilderModel

DUMMY: str = "dummy"  
@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DummyGroupBuilderModel(GroupBuilderModel):
    """The template's group builder model: the shape a group plugin's model
    takes, and nothing more.

    Attributes:
        org, team: two required example fields, validated at load and read
            by nothing -- they show a plugin author how a builder declares
            what its provider needs. (Stage 63: the credential-shaped `key`,
            `secret` and `api_host` were removed, so the template never
            suggests putting a credential in the tree.)
    """

    org: str
    team: str

    @classmethod
    def csis_name(cls) -> str:
        return DUMMY

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DummyUserBuilderModel(UserBuilderModel):
    """The template's user builder model; ``org`` and ``team`` as on the
    group model: required example fields, read by nothing."""
    org: str
    team: str
    
    @classmethod
    def csis_name(cls) -> str:
        return DUMMY