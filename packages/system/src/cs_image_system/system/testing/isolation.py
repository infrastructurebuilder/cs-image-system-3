# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The test kit's isolation between tests: every test finds the root logger
as the session started it.

The command line configures logging for the whole process when a command
starts (``setup_rich_logging``: the root logger's level and a handler of its
own), which is right for a process that runs one command and wrong for a
test session that runs hundreds in one process: a test that invoked a
command left the root logger at INFO for every test after it, and a test
that read INFO records without asking for them then passed in a full suite
and failed when run by itself.

:func:`root_logger_restored` is the body of a fixture. A suite applies it
to every one of its tests by making it one in its ``conftest.py``::

    import pytest
    from cs_image_system.system.testing import isolation

    root_logger_restored = pytest.fixture(autouse=True)(isolation.root_logger_restored)

After each test the root logger's level is put back to what it was when the
session started, and every handler the test left on it is removed (the
test runner's own capture handlers are its own to manage and are left
alone). A test that needs INFO records asks for them (``caplog.set_level``,
``caplog.at_level``) and gets them for its own length.

This module imports nothing but the standard library: the command line's
package does not depend on a test runner, so the conftest that uses the
restore is where ``pytest`` is named.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator

_ROOT = logging.getLogger()
#: the root logger's level when this module was first imported: at the start
#: of the session, by the suite's ``conftest.py``, before any test ran
_SESSION_LEVEL = _ROOT.level


def root_logger_restored() -> Iterator[None]:
    """A fixture's body: put the root logger back after the test, its level
    to the session's, and off it every handler the test left there."""
    before = list(_ROOT.handlers)
    yield
    _ROOT.setLevel(_SESSION_LEVEL)
    for handler in list(_ROOT.handlers):
        if handler not in before and not type(handler).__module__.startswith("_pytest"):
            _ROOT.removeHandler(handler)
