# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A test that configures logging for the process does not configure it for
the tests after it, in this suite too.

The two tests run in file order: the first raises the root logger's level
and leaves a handler on it, as a command run in process does; the second
finds no trace of either. The restore is the test kit's
(``cs_image_system.system.testing.isolation``), applied by the conftest
this suite runs under. Without it the second test fails.
"""
from __future__ import annotations

import logging

#: the root logger's level as the first test found it, and the handler it left
_FOUND: dict[str, object] = {}


def test_a_test_may_configure_the_root_logger_for_itself():
    root = logging.getLogger()
    _FOUND["level"] = root.level
    _FOUND["handler"] = handler = logging.NullHandler()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    assert root.level == logging.DEBUG and handler in root.handlers


def test_the_test_after_it_finds_the_root_logger_as_it_was():
    root = logging.getLogger()
    assert root.level == _FOUND.get("level", logging.WARNING)
    assert _FOUND.get("handler") not in root.handlers
