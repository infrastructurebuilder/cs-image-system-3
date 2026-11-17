# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The docker family's own suite.

``unit/`` needs the contract, the kit, the two terraform libraries and this
package, and nothing else. ``pipeline/`` drives a whole stubbed run over the
family's own fixture (``fixture/``) through the published test kit, with
this package's own stubs standing in for the daemon, and compares what the
run emits with the family's own golden (``golden/``).

Nothing here imports another provider or a helper kept outside this
package's directory: the suite passes with only this package, what it
declares, and its test extra installed.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from cs_image_system.docker_runtime import testing as docker_testing
from cs_image_system.system import testing as kit
from cs_image_system.tofu_roots import testing as roots_testing

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
GOLDEN = HERE / "golden"
#: what stands in for the outside world in a stubbed run of the fixture: the
#: daemon (this package's stubs) and the storage roots' read of live state
STUBS = (docker_testing.stub, roots_testing.stub)


@pytest.fixture
def fixture_dir() -> Path:
    """The family's fixture configuration."""
    return FIXTURE


@pytest.fixture
def golden_dir() -> Path:
    """The family's golden: the fixture's pinned emission."""
    return GOLDEN


@pytest.fixture
def family_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., kit.Run]]:
    """A factory for stubbed runs over a private copy of the family's
    fixture; keyword arguments reach ``cs_image_system.system.testing.Run``.
    The working directory is restored when the test ends."""
    made: list[kit.Run] = []

    def make(**kwargs) -> kit.Run:
        run = kit.Run(tmp_path, monkeypatch, fixture=FIXTURE, stubs=STUBS, **kwargs)
        made.append(run)
        return run

    yield make
    for run in made:
        run.restore_cwd()
