# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the CLI dry-run contract: on by default, --no-dry-run opts into execution."""
import inspect

from cs_image_system.system.cli import main


def _dry_run_option():
    return inspect.signature(main).parameters["dry_run"].default


def test_dry_run_defaults_to_true():
    assert _dry_run_option().default is True


def test_dry_run_is_toggleable():
    assert "--dry-run/--no-dry-run" in _dry_run_option().param_decls
