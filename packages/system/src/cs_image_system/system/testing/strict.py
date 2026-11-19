# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The strict session: a skipped check is a failed check.

A suite that proves a provider on its own enables this plugin
(``-p cs_image_system.system.testing.strict``, or the same in its pytest
``addopts``). At the end of the session the run fails, with one line
saying why, when no test was collected or when any test was skipped: a
test that did not run proves nothing, and a bar that reports success
without it would pass what it never checked.

:func:`verdict` is the rule itself. This repository's isolated runs
(``scripts/isolated-run``) read the same function, so the two cannot
disagree.
"""
from __future__ import annotations

from typing import Any


def verdict(collected: int, skipped: int, failed: int) -> tuple[bool, str]:
    """Whether a run of ``collected`` tests, of which ``skipped`` were
    skipped and ``failed`` failed or errored, passes, and the one line
    that says why."""
    if collected == 0:
        return False, "no test was collected"
    if failed:
        return False, f"{failed} of {collected} failed"
    if skipped:
        return False, f"{skipped} of {collected} were skipped (a skipped test is a test that did not run)"
    return True, f"{collected - skipped - failed} passed, 0 skipped"


class _Strict:
    """Counts the session's skips and failures as the reports arrive, one
    per test, and turns the session's end into the verdict."""

    def __init__(self) -> None:
        self.skipped = 0
        self.failed = 0

    def pytest_runtest_logreport(self, report: Any) -> None:
        if report.skipped and report.when in ("setup", "call"):
            self.skipped += 1
        elif report.failed:
            self.failed += 1

    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        ok, why = verdict(int(session.testscollected), self.skipped, self.failed)
        if ok or self.failed:
            return  # a failing session already fails, for its own reason
        session.exitstatus = 1
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(f"strict: {why}")


def pytest_configure(config: Any) -> None:
    config.pluginmanager.register(_Strict(), "cs-image-system-strict-session")
