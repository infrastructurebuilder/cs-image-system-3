# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A test that configures logging for the process does not configure it for
the tests after it.

The command line sets the root logger's level and installs its own handler
when a command starts. The repository's root ``conftest.py`` puts both back
after every test. The two tests here run in file order: the first does
what a command does, the second finds no trace of it. Without the restore
the second fails, and so, by itself, would any test that read INFO records
it never asked for.
"""
from __future__ import annotations

import logging

from rich.logging import RichHandler

from cs_image_system.system.cli import setup_rich_logging

#: the root logger's level as the first test found it
_FOUND: dict[str, int] = {}


def test_a_command_configures_the_root_logger_for_its_own_process():
    root = logging.getLogger()
    _FOUND["level"] = root.level
    setup_rich_logging()
    assert root.level == logging.INFO
    assert any(isinstance(h, RichHandler) for h in root.handlers)


def test_the_test_after_it_finds_the_root_logger_as_it_was():
    root = logging.getLogger()
    assert root.level == _FOUND.get("level", logging.WARNING)
    assert not any(isinstance(h, RichHandler) for h in root.handlers)
