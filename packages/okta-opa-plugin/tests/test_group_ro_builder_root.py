# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins OktaTfGroupRoBuilder's data-source-only terraform root: okta_group
lookups only (no module calls, no resources), empty-guarded scaffolding, and
the credential-gated command list."""
import os
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

import pytest

from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
from cs_image_system.base.models.group import Group
from cs_image_system.hashicorp_utils.collector import (
    ConfiguredTerraformProvider,
    TerraformCollector,
)
from cs_image_system.okta_opa_plugin.okta_opa_tf_group_ro_builder import OktaTfGroupRoBuilder
from cs_image_system.okta_opa_plugin.okta_opa_tf_group_models import OktaTfGroupRoBuilderModel

PHASE = ExecutionLifecyclePhase.GROUP_GENERATION
ROOT = Path("okta-ro-groups/group-generation")


def _model():
    return OktaTfGroupRoBuilderModel(
        name="okta-ro-groups", type_="okta-tf-ro", org="noaa",
        team="nos-coastal-modeling-cloud-sandbox",
        required_providers=[ConfiguredTerraformProvider(
            name="okta", source="okta/okta", version=">= 6.0", config={})],
    )


@pytest.fixture
def builder():
    TerraformCollector().reset()
    model = _model()
    b = OktaTfGroupRoBuilder(model)
    for name in ("stofs", "coops"):
        b.add_group_to_builder(Group(name=name))
    model.register_hcl_requirements(b.name)
    yield b
    TerraformCollector().reset()


def _by_path(assets) -> dict[Path, str]:
    grouped: dict[Path, list[str]] = {}
    for a in assets:
        grouped.setdefault(a.path, []).append(a.value)
    return {p: "\n".join(v) for p, v in grouped.items()}


def test_scaffolding_uses_okta_provider(builder):
    files = _by_path(builder.generate_items_before(PHASE))
    root = files[ROOT / "okta-ro-groups-group-generation.tf"]
    assert "terraform {" in root
    assert 'provider "okta"' in root
    assert 'org_name = "noaa"' in root
    assert "oktapam" not in root


def test_data_lookups_only_no_modules_or_resources(builder):
    files = _by_path(builder.generate_items_during(PHASE))
    assert set(files) == {ROOT / "okta-ro-groups-group-generation-groups-data.tf"}
    data_tf = files[ROOT / "okta-ro-groups-group-generation-groups-data.tf"]
    assert data_tf.count('data "okta_group"') == 2
    assert 'module "' not in data_tf
    assert 'resource "' not in data_tf
    assert 'name = "stofs"' in data_tf
    assert 'name = "coops"' in data_tf
    assert data_tf.count("provider = okta.okta_ro_groups") == 2
    assert data_tf.index("coops") < data_tf.index("stofs")


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


def test_no_groups_no_output_no_commands():
    """Unlike the managed group builder, the RO root is skipped when empty."""
    TerraformCollector().reset()
    b = OktaTfGroupRoBuilder(_model())
    assert list(b.generate_items_before(PHASE)) == []
    assert list(b.generate_items_during(PHASE)) == []
    assert b.get_commands_to_run_after(PHASE).build_executables == []
    TerraformCollector().reset()


def test_other_phases_are_silent(builder):
    for phase in (ExecutionLifecyclePhase.USER_GENERATION,
                  ExecutionLifecyclePhase.IMAGE_GENERATION):
        assert list(builder.generate_items_before(phase)) == []
        assert list(builder.generate_items_during(phase)) == []
        assert builder.get_commands_to_run_after(phase).build_executables == []
