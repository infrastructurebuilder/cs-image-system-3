# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins OktaTfUserRoBuilder's data-source-only terraform root: lookup file
only, no resources, and the credential-gated command list."""
import os
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

import pytest

from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
from cs_image_system.base.models.user import User
from cs_image_system.hashicorp_utils.collector import (
    ConfiguredTerraformProvider,
    TerraformCollector,
)
from cs_image_system.okta_opa_plugin.okta_opa_tf_user_ro_builder import OktaTfUserRoBuilder
from cs_image_system.okta_opa_plugin.okta_opa_tf_user_models import OktaTfUserRoBuilderModel

PHASE = ExecutionLifecyclePhase.USER_GENERATION
ROOT = Path("okta-ro-users/user-generation")


@pytest.fixture
def builder():
    TerraformCollector().reset()
    model = OktaTfUserRoBuilderModel(
        name="okta-ro-users", type_="okta-tf-ro", org="noaa",
        team="nos-coastal-modeling-cloud-sandbox",
        required_providers=[ConfiguredTerraformProvider(
            name="okta", source="okta/okta", version=">= 6.0", config={})],
    )
    b = OktaTfUserRoBuilder(model)
    for name in ("kendall.kilo@example.com", "avery.alpha@example.invalid"):   # added out of order
        first, last = name.split("@")[0].split(".")
        b.add_user_to_builder(User(
            name=name, email=name, first_name=first, last_name=last))
    model.register_hcl_requirements(b.name)
    yield b
    TerraformCollector().reset()


def _by_path(assets) -> dict[Path, str]:
    grouped: dict[Path, list[str]] = {}
    for a in assets:
        grouped.setdefault(a.path, []).append(a.value)
    return {p: "\n".join(v) for p, v in grouped.items()}


def test_scaffolding_inherited_from_managed_builder(builder):
    files = _by_path(builder.generate_items_before(PHASE))
    root = files[ROOT / "okta-ro-users-user-generation.tf"]
    assert "terraform {" in root
    assert 'provider "okta"' in root
    assert 'org_name = "noaa"' in root
    assert "oktapam" not in root


def test_data_lookups_only_no_resources(builder):
    files = _by_path(builder.generate_items_during(PHASE))
    assert set(files) == {ROOT / "okta-ro-users-user-generation-users-data.tf"}
    data_tf = files[ROOT / "okta-ro-users-user-generation-users-data.tf"]
    assert data_tf.count('data "okta_user"') == 2
    assert 'resource "' not in data_tf
    # eager lookups: nothing to depend on in a root that creates nothing
    assert "depends_on" not in data_tf
    assert data_tf.count("provider = okta.okta_ro_users") == 2
    # least privilege (LEDGER.md item 1): no roles/groups fetch, so okta.roles.read
    # can stay revoked
    assert data_tf.count("skip_roles = true") == 2
    assert data_tf.count("skip_groups = true") == 2
    assert data_tf.index("avery_alpha") < data_tf.index("kendall_kilo")   # emitted sorted by name
    assert 'value = "avery.alpha@example.invalid"' in data_tf


def test_commands_gated_on_credentials(builder):
    # the command list depends on the run mode; pin a REAL run explicitly, so a
    # context another test left behind (dry by default) cannot decide it
    builder._get_context = lambda: SimpleNamespace(dry_run=False)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OKTA_API", "OKTA_ACCESS"))}
    with mock.patch.dict(os.environ, env, clear=True):
        with mock.patch.object(builder, "get_executable_copy") as gec:
            gec.side_effect = lambda: mock.MagicMock()
            cfe = builder.get_commands_to_run_after(PHASE)
    assert [c.args for c in cfe.build_executables] == [["fmt"], ["init"], ["validate"]]

    with mock.patch.dict(os.environ, {**env, "OKTA_API_PRIVATE_KEY": "pem"}, clear=True):
        with mock.patch.object(builder, "get_executable_copy") as gec:
            gec.side_effect = lambda: mock.MagicMock()
            cfe = builder.get_commands_to_run_after(PHASE)
    assert [c.args for c in cfe.build_executables][-1] == ["plan"]

    # a DRY run initialises without the backend and never plans at generation
    # time, credentials or not: it must not need the remote state
    builder._get_context = lambda: SimpleNamespace(dry_run=True)
    with mock.patch.dict(os.environ, {**env, "OKTA_API_PRIVATE_KEY": "pem"}, clear=True):
        with mock.patch.object(builder, "get_executable_copy") as gec:
            gec.side_effect = lambda: mock.MagicMock()
            cfe = builder.get_commands_to_run_after(PHASE)
    assert [c.args for c in cfe.build_executables] == [["fmt"], ["init", "-backend=false"], ["validate"]]


def test_no_users_no_output_no_commands():
    TerraformCollector().reset()
    model = OktaTfUserRoBuilderModel(
        name="okta-ro-users", type_="okta-tf-ro", org="noaa", team="t",
        required_providers=[ConfiguredTerraformProvider(
            name="okta", source="okta/okta", version=">= 6.0", config={})])
    b = OktaTfUserRoBuilder(model)
    assert list(b.generate_items_before(PHASE)) == []
    assert list(b.generate_items_during(PHASE)) == []
    assert b.get_commands_to_run_after(PHASE).build_executables == []
    TerraformCollector().reset()


def test_other_phases_are_silent(builder):
    for phase in (ExecutionLifecyclePhase.GROUP_GENERATION,
                  ExecutionLifecyclePhase.IMAGE_GENERATION):
        assert list(builder.generate_items_before(phase)) == []
        assert list(builder.generate_items_during(phase)) == []
        assert builder.get_commands_to_run_after(phase).build_executables == []
