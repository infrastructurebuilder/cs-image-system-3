# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Surfaces the system no longer offers, pinned absent.

`--only-providers` is not an option and the run context carries no `force`;
`sleep_before_finalization` defaults to one second; the RHEL builder has no
unreachable update hooks of its own; the registry has no `get_builder`.

history: bundle VI item 2.
"""
from __future__ import annotations

from pathlib import Path

from tests.harness import V2Run


def test_only_providers_is_gone_and_the_context_has_no_force(tmp_path: Path, monkeypatch):
    from typer.testing import CliRunner
    from cs_image_system.system import cli as climod
    from cs_image_system.base.models.ia_config import IAConfig
    result = CliRunner().invoke(climod.app, ["--root-dir", str(tmp_path), "--only-providers", "aws", "validate"])
    assert result.exit_code != 0 and "--only-providers" in result.output, result.output
    run = V2Run(tmp_path / "run", monkeypatch)
    try:
        assert not hasattr(run.ctx, "force") and not hasattr(run.ctx, "only_providers")
    finally:
        run.restore_cwd()
    assert IAConfig.__dataclass_fields__["sleep_before_finalization"].default == 1     # the model's default (it said 10)


def test_rhels_unreachable_update_hooks_are_gone():
    from cs_image_system.default_os_plugin.rhel_type import RhelOsBuilderModel
    from cs_image_system.base.models.os_builder_model import OsBuilderModel
    assert "commands_to_update" not in RhelOsBuilderModel.__dict__
    assert "get_command_to_update" not in RhelOsBuilderModel.__dict__
    assert OsBuilderModel.get_command_to_update(OsBuilderModel.__new__(OsBuilderModel)) == [], \
        "the base's update is the one path for a family without a package-manager policy"


def test_registry_get_builder_is_gone():
    from cs_image_system.base.registry import Registry
    assert not hasattr(Registry, "get_builder")
