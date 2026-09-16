# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the module-call shape emitted for okta groups (tfmodules/okta_opa_module)."""
from types import SimpleNamespace

from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder


def _stub_builder(*, account_discovery=True, gateway_selector=None):
    from cs_image_system.hashicorp_utils.collector import TerraformCollector
    TerraformCollector().reset()
    TerraformCollector().configure_provider("oktagroups", "oktapam", {"oktapam_team": "t"})
    stub = SimpleNamespace(
        name="oktagroups",
        # The builder consumes effective_gateway_selector (model value with
        # config fallback); the stub bypasses the property with a plain attr.
        model=SimpleNamespace(account_discovery=account_discovery,
                              effective_gateway_selector=gateway_selector),
    )
    stub._group_module_call = OktaTfGroupBuilder._group_module_call.__get__(stub)
    return stub


_ROOT = SimpleNamespace(name="basic", admins={"avery.alpha"},
                        include_root_group_in_admins=True)


def test_regular_group_delegates_to_own_admin_and_merges_root_admins():
    b = _stub_builder(gateway_selector="environment=staging")
    # Root's admin (avery.alpha) is NOT in this group's own admins — the
    # emitted list must be the union (PLAN.md local-migration Q2).
    group = SimpleNamespace(name="coops", members={"casey.charlie"},
                            admins={"casey.charlie"},
                            include_root_group_in_admins=True)
    hcl = "\n".join(b._group_module_call(group, _ROOT, "../../../../tfmodules/okta_opa_module"))
    assert 'module "group_coops" {' in hcl
    assert 'source                    = "../../../../tfmodules/okta_opa_module"' in hcl
    assert 'group_id                  = "coops"' in hcl
    assert 'providers                 = { oktapam = oktapam.oktagroups }' in hcl
    assert 'members                   = ["casey.charlie"]' in hcl
    assert 'admins                    = ["avery.alpha", "casey.charlie"]' in hcl
    # Q1: every rg delegates to its OWN admin group via the module fallback.
    assert "delegated_admin_group_ids = []" in hcl
    assert "module.group_basic.admin_group_id" not in hcl
    assert 'gateway_selector          = "environment=staging"' in hcl
    # account_discovery defaults to True on the model; stub mirrors that
    assert "account_discovery         = true" in hcl


def test_include_root_group_in_admins_false_keeps_own_admins():
    b = _stub_builder()
    group = SimpleNamespace(name="coops", members=set(),
                            admins={"casey.charlie"},
                            include_root_group_in_admins=False)
    hcl = "\n".join(b._group_module_call(group, _ROOT, "X"))
    assert 'admins                    = ["casey.charlie"]' in hcl
    assert "avery.alpha" not in hcl


def test_root_group_gets_no_delegates_and_merge_is_noop():
    b = _stub_builder(account_discovery=False)
    group = SimpleNamespace(name="basic", members=set(), admins={"avery.alpha"},
                            include_root_group_in_admins=True)
    hcl = "\n".join(b._group_module_call(group, _ROOT, "X"))
    assert "delegated_admin_group_ids = []" in hcl
    assert 'admins                    = ["avery.alpha"]' in hcl
    assert "account_discovery         = false" in hcl
    assert "gateway_selector" not in hcl


def _bare_model(gateway_selector):
    from cs_image_system.okta_opa_plugin.okta_tf_models import OktaGroupBuilderModel
    model = object.__new__(OktaGroupBuilderModel)  # skip required ctor fields
    model.gateway_selector = gateway_selector
    return model


def test_effective_gateway_selector_falls_back_to_config(monkeypatch):
    import cs_image_system.base.global_context as gc
    monkeypatch.setattr(gc, "GlobalTypeContext",
                        lambda: SimpleNamespace(config={"okta_gateway_selector": "environment=staging"}))
    assert _bare_model(None).effective_gateway_selector == "environment=staging"
    # An explicit model value always wins over config.
    assert _bare_model("environment=prod").effective_gateway_selector == "environment=prod"


def test_effective_gateway_selector_none_when_config_unset(monkeypatch):
    import cs_image_system.base.global_context as gc
    monkeypatch.setattr(gc, "GlobalTypeContext",
                        lambda: SimpleNamespace(config={}))
    assert _bare_model(None).effective_gateway_selector is None


def test_model_account_discovery_defaults_true():
    """Pins the OktaGroupBuilderModel field default (changed 2026-07-10)."""
    import dataclasses
    from cs_image_system.okta_opa_plugin.okta_tf_models import OktaGroupBuilderModel
    fields = {f.name: f for f in dataclasses.fields(OktaGroupBuilderModel)}
    assert fields["account_discovery"].default is True
