# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The strict session: a test run that collected nothing, or skipped
anything, fails, as an isolated run's verdict does.

Each case runs pytest in a subprocess over a few generated tests, with the
plugin enabled, and reads only the exit status.
"""
from __future__ import annotations

import pytest

from cs_image_system.system.testing.strict import verdict

pytest_plugins = ["pytester"]

STRICT = ("-p", "cs_image_system.system.testing.strict", "-p", "no:cacheprovider")


def test_a_session_that_collects_nothing_fails(pytester: pytest.Pytester):
    pytester.makepyfile(test_nothing="")
    assert pytester.runpytest_subprocess(*STRICT).ret == 1


def test_a_session_that_skips_a_test_fails(pytester: pytest.Pytester):
    pytester.makepyfile(test_one="import pytest\n"
                                  "def test_runs(): pass\n"
                                  "def test_skips(): pytest.skip('absent')\n")
    assert pytester.runpytest_subprocess(*STRICT).ret == 1


def test_a_session_that_passes_everything_passes(pytester: pytest.Pytester):
    pytester.makepyfile(test_one="def test_a(): pass\ndef test_b(): pass\n")
    assert pytester.runpytest_subprocess(*STRICT).ret == 0


def test_a_failing_session_fails_as_it_would_without_the_plugin(pytester: pytest.Pytester):
    pytester.makepyfile(test_one="def test_a(): assert False\n")
    assert pytester.runpytest_subprocess(*STRICT).ret == pytester.runpytest_subprocess("-p", "no:cacheprovider").ret


@pytest.mark.parametrize("collected, skipped, failed, ok", [
    (0, 0, 0, False), (3, 1, 0, False), (3, 0, 1, False), (3, 0, 0, True),
])
def test_the_verdict_passes_only_a_run_that_ran_everything(collected, skipped, failed, ok):
    assert verdict(collected, skipped, failed)[0] is ok
