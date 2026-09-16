# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.constants import VCT
from cs_image_system.base.models.builder_model import BuilderModel


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class UserBuilderModel(BuilderModel):
    """
        This dataclass represents a user builder.
        
        Notable here is that the "default" values below for user_email_template and 
        user description WILL have the string '{{ user' replaced witht the string 
        '{{ this' during processing, so that they can be used as templates for the user object.
    """
    
    default_user_email_template: str = "{{ user.name }}" # "this" in this case, applies to the user object
    default_user_description_template: str = "User {{ user.name }} / {{ user.email }}"
    # When true, user.name must equal user.email (casefolded): the name doubles
    # as the identity's login everywhere (e.g. OPA group attachment usernames
    # match the Okta login by construction). Blank names are set from the email;
    # a non-blank mismatch aborts the run.
    email_as_username: bool = True

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.USER_BUILDER_MODEL
    def get_user_email_template(self) -> str:
        return self.default_user_email_template
    def get_user_description_template(self) -> str:
        return self.default_user_description_template
    pass
