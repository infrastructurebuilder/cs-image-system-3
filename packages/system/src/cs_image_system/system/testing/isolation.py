# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The test kit's isolation: every test finds the root logger as the
session started it, and a test can assert that what it drives leaves the
process alone.

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

:func:`process_unchanged` is the assertion a plugin's suite makes about
itself: around a load and a run, it fails, naming what changed, if the
process's environment, working directory, ``sys.path`` or root logger are
not as they were, or if the kit's store of opened secrets lost an entry::

    with isolation.process_unchanged():
        ctx = kit.load_context(root)
        kit.drive_lifecycles(ctx, "all")

Two things are the caller's to arrange, because they are the core's own
and deliberate. The load makes the configuration's root the working
directory and the command line puts the invoking one back when the command
ends: a test stands in the root first, as a command run from it does. And
the store of opened secrets is shared by every run in the process by a
recorded decision (what another run opened can only make a run hide one
value more): it may grow, and the assertion holds it only to never losing
an entry.

This module imports no test runner: the command line's package does not
depend on one, so the conftest that uses the restore is where ``pytest``
is named.
"""
from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from cs_image_system.base import encryption

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


def _state() -> dict[str, Any]:
    return {
        "environment": dict(os.environ),
        "working directory": os.getcwd(),
        "sys.path": list(sys.path),
        "root logger level": _ROOT.level,
        "root logger handlers": list(_ROOT.handlers),
        "opened secrets": set(encryption.opened_markers()),
    }


def _names(items: Any) -> str:
    return ", ".join(sorted(str(i) for i in items))


def changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """What differs between two readings of the process, one line each. An
    environment variable is named and its value never shown; an opened
    secret is counted and never shown."""
    out: list[str] = []
    was, now = before["environment"], after["environment"]
    for label, names in (("set", now.keys() - was.keys()), ("removed", was.keys() - now.keys()),
                         ("changed", {k for k in was.keys() & now.keys() if was[k] != now[k]})):
        if names:
            out.append(f"environment: {label} {_names(names)}")
    if before["working directory"] != after["working directory"]:
        out.append(f"working directory: was {before['working directory']}, is {after['working directory']}")
    was_path, now_path = before["sys.path"], after["sys.path"]
    if was_path != now_path:
        added, removed = [p for p in now_path if p not in was_path], [p for p in was_path if p not in now_path]
        out.append("sys.path: " + "; ".join(part for part in (
            f"added {_names(added)}" if added else "", f"removed {_names(removed)}" if removed else "",
            "reordered" if not added and not removed else "") if part))
    if before["root logger level"] != after["root logger level"]:
        out.append(f"root logger: level was {logging.getLevelName(before['root logger level'])}, "
                   f"is {logging.getLevelName(after['root logger level'])}")
    was_handlers, now_handlers = before["root logger handlers"], after["root logger handlers"]
    for label, handlers in (("added", [h for h in now_handlers if h not in was_handlers]),
                            ("removed", [h for h in was_handlers if h not in now_handlers])):
        if handlers:
            out.append(f"root logger: {label} handler(s) {_names(type(h).__name__ for h in handlers)}")
    lost = before["opened secrets"] - after["opened secrets"]
    if lost:
        out.append(f"opened secrets: {len(lost)} of {len(before['opened secrets'])} entries were lost")
    return out


@contextmanager
def process_unchanged() -> Iterator[None]:
    """Fail, naming what changed, if the block leaves the process other
    than it found it: the environment, the working directory, ``sys.path``,
    the root logger's level and handlers; and the kit's store of opened
    secrets, which may gain entries and may not lose one. A block that
    raises is not judged: its own failure is the one reported."""
    before = _state()
    yield
    found = changes(before, _state())
    if found:
        raise AssertionError("the process was changed:\n  " + "\n  ".join(found))
