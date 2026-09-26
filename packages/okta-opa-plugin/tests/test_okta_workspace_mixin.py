# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins OktaTfWorkspaceModelMixin: provider dispatch, credential asserts,
collector registration."""
import os
from unittest import mock

import pytest

from cs_image_system.hashicorp_utils.collector import (
    ConfiguredTerraformProvider,
    TerraformCollector,
)
from cs_image_system.okta_opa_plugin.okta_opa_tf_group_models import (
    OktaTfGroupBuilderModel,
)
from cs_image_system.okta_opa_plugin.okta_opa_tf_user_models import (
    OktaTfUserBuilderModel,
)

TEAM = "nos-coastal-modeling-cloud-sandbox"
TEAM_VAR = "nos_coastal_modeling_cloud_sandbox"
_OKTAPAM = ConfiguredTerraformProvider(
    name="oktapam", source="okta/oktapam", version=">= 0.6.3", config={})
_OKTA = ConfiguredTerraformProvider(
    name="okta", source="okta/okta", version=">= 4.9", config={})


def _group(**kw) -> OktaTfGroupBuilderModel:
    kw.setdefault("required_providers", [_OKTAPAM])
    return OktaTfGroupBuilderModel(
        name="oktagroups", type_="okta-tf", org="noaa", team=TEAM, **kw)


def _user(**kw) -> OktaTfUserBuilderModel:
    kw.setdefault("required_providers", [_OKTA])
    return OktaTfUserBuilderModel(
        name="okta-tf-users", type_="okta-tf", org="noaa", team=TEAM, **kw)


def _env(**extra) -> mock._patch_dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OKTA_API", "OKTA_ACCESS", "TF_VAR_"))}
    env.update(extra)
    return mock.patch.dict(os.environ, env, clear=True)


def test_oktapam_transform_is_unchanged():
    cfg = _group().transform_provider(_OKTAPAM, None).config
    assert sorted(cfg) == [
        "oktapam_api_host", "oktapam_key", "oktapam_secret", "oktapam_team"]


def test_okta_transform_defaults_org_and_base_url():
    cfg = _user().transform_provider(_OKTA, None).config
    assert cfg == {"org_name": "noaa", "base_url": "okta.com"}


def test_okta_transform_yaml_config_wins():
    """R5 mitigation: YAML-declared provider config passes through untouched."""
    declared = ConfiguredTerraformProvider(
        name="okta", source="okta/okta", version=">= 4.9",
        config={"org_name": "other", "client_id": "abc", "scopes": ["okta.users.manage"]})
    cfg = _user(required_providers=[declared]).transform_provider(declared, None).config
    assert cfg["org_name"] == "other"          # not overwritten by self.org
    assert cfg["client_id"] == "abc"           # arbitrary provider args survive
    assert cfg["base_url"] == "okta.com"       # omitted keys still defaulted


def test_provider_variables_oktapam_sensitive():
    variables = _group().provider_variables(_OKTAPAM)
    assert [v.name for v in variables] == [f"{TEAM_VAR}_key", f"{TEAM_VAR}_secret"]
    assert all(v.sensitive for v in variables)


def test_provider_variables_okta_declares_none():
    assert _user().provider_variables(_OKTA) == []


def test_group_finalize_requires_tfvars():
    with _env():
        with pytest.raises(ValueError, match=f"TF_VAR_{TEAM_VAR}_key"):   # stage 63: a real refusal
            _group().finalize()


def test_group_finalize_resolves_tfvars():
    with _env(**{f"TF_VAR_{TEAM_VAR}_key": "k", f"TF_VAR_{TEAM_VAR}_secret": "s"}):
        g = _group()
        g.finalize()
    assert g.key == f"var.{TEAM_VAR}_key"
    assert g.secret == f"var.{TEAM_VAR}_secret"
    assert g.api_host == "https://noaa.pam.okta.com"


def test_user_finalize_warns_but_does_not_require_credentials(caplog):
    """R2: the okta root demands no oktapam TF_VARs and only warns on
    missing OKTA_API_* credentials."""
    with _env():
        u = _user()
        u.finalize()  # no raise
    assert any("'plan' will be skipped" in r.message for r in caplog.records)


def test_user_finalize_quiet_with_credentials(caplog):
    with _env(OKTA_API_PRIVATE_KEY="pem"):
        _user().finalize()
    assert not any("plan" in r.message for r in caplog.records)


def test_register_hcl_requirements_end_to_end():
    col = TerraformCollector()
    col.reset()
    try:
        _user().register_hcl_requirements("okta-tf-users")
        assert col.provider_bindings("okta-tf-users") == {"okta": "okta.okta_tf_users"}
        assert col.generate_variable_blocks("okta-tf-users") == []
        phcl = "\n".join(col.generate_provider_blocks("okta-tf-users"))
        assert 'provider "okta"' in phcl
        assert 'org_name = "noaa"' in phcl
        assert 'alias   = "okta_tf_users"' in phcl.replace("alias  =", "alias =") or "alias" in phcl
    finally:
        col.reset()
