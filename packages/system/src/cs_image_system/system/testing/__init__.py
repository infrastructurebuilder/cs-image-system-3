# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The test kit: what a plugin's tests use to drive a whole run over a
fixture of their own, with nothing outside the process touched.

It names no provider and imports none. A provider ships the stub function
that stands in for its own calls to the outside world, in its own package,
and a test hands it in.

The kit needs ``pytest`` only for the ``monkeypatch`` a test passes to it;
install it with the ``testing`` extra of this distribution.
"""
from .golden import IGNORED_FILES, assert_matches, differences, emitted, write
from .neighbours import broken_neighbour
from .run import (
    FIXED_CHECKED_AT,
    FIXED_NOW,
    FIXED_RUN_ID,
    FIXED_TIMESTAMP,
    IDENTITY_FILE,
    Run,
    Stub,
    cli_context,
    command_lines,
    copy_fixture,
    drive_lifecycles,
    encrypted,
    load_context,
    module_path,
    modules_beside,
    modules_inside,
    os_type_for_family,
    passing_session,
    plain,
    run_mod_tests,
    stub_core,
    tree,
    validation_errors,
)

__all__ = [
    "FIXED_CHECKED_AT",
    "FIXED_NOW",
    "FIXED_RUN_ID",
    "FIXED_TIMESTAMP",
    "IDENTITY_FILE",
    "IGNORED_FILES",
    "Run",
    "Stub",
    "assert_matches",
    "broken_neighbour",
    "cli_context",
    "command_lines",
    "copy_fixture",
    "differences",
    "drive_lifecycles",
    "emitted",
    "encrypted",
    "load_context",
    "module_path",
    "modules_beside",
    "modules_inside",
    "os_type_for_family",
    "passing_session",
    "plain",
    "run_mod_tests",
    "stub_core",
    "tree",
    "validation_errors",
    "write",
]
