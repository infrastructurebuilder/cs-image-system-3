# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction



from cs_image_system.base.constants import DEFAULT
from cs_image_system.base.models.group_builder import GroupBuilderModel
from cs_image_system.base.models.user_builder import UserBuilderModel

DUMMY: str = "dummy"  
@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DummyGroupBuilderModel(GroupBuilderModel):
    """Dataclass representing an Dummy group configuration.

    Attributes:
        Dummy_group_id: The ID of the Dummy group.
    """

    org: str
    team: str
    key: str = DEFAULT # TODO: Secrets
    secret: str = DEFAULT
    api_host: str = DEFAULT

    @classmethod
    def csis_name(cls) -> str:
        return DUMMY

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DummyUserBuilderModel(UserBuilderModel):
    """Dataclass representing an Dummy user configuration.

    Attributes:
        Dummy_user_id: The ID of the Dummy user.
    """    
    org: str
    team: str    
    type = DUMMY
    
    @classmethod
    def csis_name(cls) -> str:
        return DUMMY