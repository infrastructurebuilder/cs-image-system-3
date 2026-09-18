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
    # stage 51: the organisation half of a derived address, so it can be
    # declared encrypted on its own -- `{{ user.name }}@{{ builder.email_domain }}`
    # renders the address in process and, because a derived value inherits its
    # inputs' encryption, carries the ciphertext into every emitted artifact.
    # One marker serves every user, so the emission is stable across a run.
    email_domain: str | None = None
    # When true, user.name must equal user.email (casefolded): the name doubles
    # as the identity's login everywhere (e.g. OPA group attachment usernames
    # match the Okta login by construction). Blank names are set from the email;
    # a non-blank mismatch aborts the run.
    email_as_username: bool = True

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.USER_BUILDER_MODEL
    EMAIL_DOMAIN_PLACEHOLDER = "{{ builder.email_domain }}"

    def get_user_email_template(self) -> str:
        """The address template with :attr:`email_domain` already folded in.

        It is substituted HERE, in Python, rather than left for the renderer:
        `builder` reaches a template only on the pass that resolves the foreign
        key, so a `{{ builder.… }}` inside the template's own VALUE would never
        be rendered. Folding it in keeps the user-level template one pass, and
        the domain's plaintext then carries its ciphertext into the emission
        the way any derived value does (stage 51)."""
        template = self.default_user_email_template
        if self.email_domain and self.EMAIL_DOMAIN_PLACEHOLDER in template:
            return template.replace(self.EMAIL_DOMAIN_PLACEHOLDER, str(self.email_domain))
        return template
    def get_user_description_template(self) -> str:
        return self.default_user_description_template
    def get_email_domain(self) -> str | None:
        return self.email_domain
    pass
