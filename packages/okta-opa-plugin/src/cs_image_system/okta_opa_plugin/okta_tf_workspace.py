# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Terraform-workspace wiring shared by the okta-tf group and user builder models.

Both builders own a standalone terraform root keyed by their name (the
collector "workspace"): provider requirements, credential-backed variables,
and the state-backend binding are identical machinery, so they live here once.

Credential model per provider:

- ``oktapam`` (group root): key/secret arrive as ``TF_VAR_<team>_key`` /
  ``TF_VAR_<team>_secret`` environment variables and are wired through
  declared (sensitive) terraform variables. Missing values abort finalize.
- ``okta`` (user root): OAuth 2.0 client-credentials with a private-key JWT.
  The provider reads ``OKTA_API_CLIENT_ID`` / ``OKTA_API_SCOPES`` /
  ``OKTA_API_PRIVATE_KEY`` / ``OKTA_API_PRIVATE_KEY_ID`` (or ``OKTA_API_TOKEN``
  for SSWS) directly from the environment, so nothing secret enters HCL and no
  terraform variables are declared. Missing credentials only warn -- the
  builder then skips ``plan`` (see ``okta_credentials_present``). See the
  credentials runbook in PLAN.md.
"""
from __future__ import annotations

import logging
import os
from dataclasses import field
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Any, Mapping

from cs_image_system.base import utils
from cs_image_system.base.constants import DEFAULT, OOPS_DEFAULTS, VCT
from cs_image_system.base.encryption import EncryptedStr
from cs_image_system.base.helpers.field_helpers import fk_field, templated_field
from cs_image_system.hashicorp_utils.collector import (
    ConfiguredTerraformProvider,
    TerraformCollector,
    TerraformVariable,
)
from cs_image_system.hashicorp_utils.blocks import Raw
from cs_image_system.hashicorp_utils.hashicorp import QString

log = logging.getLogger(__name__)

OKTAPAM_PROVIDER = "oktapam"
OKTA_PROVIDER = "okta"

# Environment variables the okta/okta provider reads natively (any one of the
# credential-bearing ones marks the credentials as present).
OKTA_CREDENTIAL_ENV_VARS = ("OKTA_API_PRIVATE_KEY", "OKTA_API_TOKEN", "OKTA_ACCESS_TOKEN")


def okta_credentials_present(env: Mapping[str, str] | None = None) -> bool:
    """True when the okta/okta provider can authenticate from the environment."""
    lookup: Mapping[str, str] = os.environ if env is None else env
    return any(lookup.get(v) for v in OKTA_CREDENTIAL_ENV_VARS)


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class OktaTfWorkspaceModelMixin:
    """Provider/variable/backend declarations for an okta-tf terraform root."""

    # NOTE: self._finalized and self.name come from BuilderModel/NameTyped and
    # are read via getattr below -- annotating them here (even TYPE_CHECKING
    # guarded) would make pyright's dataclass transform treat them as required
    # constructor fields.

    org: str
    team: str
    key: EncryptedStr = DEFAULT  # oktapam; becomes "var.<team>_key" at finalize; may be ENC[age:...] (stage 33)
    secret: EncryptedStr = DEFAULT  # oktapam; becomes "var.<team>_secret" at finalize
    api_host: str = templated_field(replace_value='https://{{ this.org }}.pam.okta.com',
                                    default=DEFAULT, metadata={
                    "description": ("The Okta API host for this builder. "
                        "This should be in the format of https://{yourOktaDomain}.pam.okta.com"),
                    "required": True,
                    })
    okta_base_url: str = "okta.com"  # okta/okta provider base_url ("oktapreview.com" for preview orgs)
    # okta_user.status applied to enabled users; STAGED so a first apply does
    # not activate (and email) real people. Disabled users map to SUSPENDED.
    default_user_status: str = "STAGED"
    required_providers: list[ConfiguredTerraformProvider] = field(default_factory=list)
    state_configuration: str = fk_field(target=VCT.STATE_BACKEND_MODEL, default=DEFAULT, metadata={
        "description": "The backend this config uses",
        "required": True,
    })

    # ------------------------------------------------------------------
    # Provider bookkeeping
    # ------------------------------------------------------------------
    def _team_var(self) -> str:
        return utils.super_safe_name(self.team)

    def provider_names(self) -> set[str]:
        """Names of the declared providers, tolerant of un-structured entries."""
        names: set[str] = set()
        for p in self.required_providers:
            name = p.get("name") if isinstance(p, dict) else getattr(p, "name", None)
            if name:
                names.add(str(name))
        return names

    def provider_variables(self, provider: ConfiguredTerraformProvider) -> list[TerraformVariable]:
        """Terraform variables a provider's configuration depends on.

        oktapam wires its credentials through variables; okta reads OKTA_API_*
        from the environment and declares none.
        """
        team = self._team_var()
        if provider.name == OKTAPAM_PROVIDER:
            return [
                TerraformVariable(
                    name=f"{team}_key", type="string", sensitive=True,
                    description=f"Key for {self.team}, auto-generated by "
                                f"{self.__class__.__name__}"),
                TerraformVariable(
                    name=f"{team}_secret", type="string", sensitive=True,
                    description=f"Secret for {self.team}, auto-generated by "
                                f"{self.__class__.__name__}"),
            ]
        return []

    def transform_provider(
        self, provider: ConfiguredTerraformProvider, ctx: Any = None
    ) -> ConfiguredTerraformProvider:
        """Provider config for the generated ``provider`` block.

        Starts from the YAML-declared ``config:`` and fills in defaults only
        for keys the YAML omits, so any provider argument (client_id, scopes,
        private_key_id, ...) is expressible in config without code changes.
        """
        if provider.name == OKTAPAM_PROVIDER:
            tcfg: dict[str, Any] = {
                "oktapam_key": self.key,
                "oktapam_secret": self.secret,
                "oktapam_api_host": self.api_host,
                "oktapam_team": self.team,
            }
            for k, v in tcfg.items():
                # stage 34: a declared-encrypted credential is emitted as the
                # reference to its ciphertext, never quoted into HCL
                if ctx:
                    v = TerraformCollector().sensitive_ref(str(ctx), k, v)
                newv = v if (isinstance(v, Raw) or v.startswith("var.")) else QString(v, quoted=True)
                tcfg[k] = newv
        elif provider.name == OKTA_PROVIDER:
            tcfg = dict(provider.config or {})
            tcfg.setdefault("org_name", self.org)
            tcfg.setdefault("base_url", self.okta_base_url)
            # Credentials intentionally absent: OKTA_API_* env vars.
        else:
            log.warning(f"No transform for provider {provider.name!r} on "
                        f"{self.__class__.__name__}; passing its config through.")
            tcfg = dict(provider.config or {})
        return ConfiguredTerraformProvider(
            name=provider.name,
            source=provider.source,
            version=provider.version,
            config=tcfg,
        )

    def register_hcl_requirements(self, workspace: str) -> None:
        """Declare this builder's terraform needs into the run-scoped collector.

        Providers (with credential-injecting config via transform_provider),
        their credential variables, and the workspace's state backend.
        """
        col = TerraformCollector()
        for provider in self.required_providers:
            col.require_provider(workspace, provider.name,
                                 source=provider.source,
                                 version=provider.version)
            configured = self.transform_provider(provider, workspace)
            col.configure_provider(workspace, provider.name,
                                   dict(configured.config))
            for variable in self.provider_variables(provider):
                col.declare_variable(workspace, variable)
        col.bind_workspace(workspace, self.state_configuration)   # stage 46: own value, else the default (no runtime)

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------
    def _require_tfvar(self, suffix: str, current: str, env: dict[str, str]) -> str:
        """Resolve a DEFAULT credential field to ``var.<team>_<suffix>``,
        asserting the backing ``TF_VAR`` environment variable exists."""
        if current not in OOPS_DEFAULTS:
            return current
        _tu = self._team_var()
        value = env.get(f"TF_VAR_{_tu}_{suffix}")
        assert value is not None, (
            f"Okta builder {getattr(self, 'name', '<unnamed>')} is missing a "
            f"{suffix} value.  "
            f"Expected to find environment variable TF_VAR_{_tu}_{suffix} "
            f"for team {self.team} in org {self.org}"
        )
        return f"var.{_tu}_{suffix}"

    def finalize(self) -> None:
        if getattr(self, "_finalized", False):
            return
        super().finalize()  # type: ignore[misc]
        env = os.environ.copy()
        if self.api_host in OOPS_DEFAULTS:
            self.api_host = f"https://{self.org}.pam.okta.com"
        names = self.provider_names()
        if OKTAPAM_PROVIDER in names:
            self.key = self._require_tfvar("key", self.key, env)
            self.secret = self._require_tfvar("secret", self.secret, env)
        if OKTA_PROVIDER in names and not okta_credentials_present(env):
            log.warning(
                f"Okta builder {getattr(self, 'name', '<unnamed>')}: no "
                f"okta/okta credentials in the environment "
                f"({' / '.join(OKTA_CREDENTIAL_ENV_VARS)}); 'plan' will be "
                f"skipped for this workspace. See the credentials runbook in "
                f"PLAN.md."
            )
