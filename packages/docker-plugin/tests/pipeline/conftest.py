# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The docker family's pipeline tests: what needs a whole run.

The family's suite has two halves. ``unit/`` needs the contract, the SDK
(the kit and the two terraform libraries) and this package, and nothing
else: it is what runs at the LOW end of the SDK range the package declares,
in an environment that holds no command line and no test kit, so nothing
that half needs may live in a conftest above it. ``pipeline/`` (this
directory) drives a whole stubbed run over the family's own fixture
(``../fixture``) through the published test kit, with this package's own
stubs standing in for the daemon, and compares what the run emits with the
family's own golden (``../golden``).

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
from cs_image_system.system.testing import isolation
from cs_image_system.tofu_roots import testing as roots_testing

# every pipeline test finds the root logger as the session started it,
# wherever the suite runs from: its isolated run starts in this package's
# directory and sees no conftest above it
root_logger_restored = pytest.fixture(autouse=True)(isolation.root_logger_restored)

TESTS = Path(__file__).resolve().parents[1]
FIXTURE = TESTS / "fixture"
GOLDEN = TESTS / "golden"
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


@pytest.fixture
def family_stubs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The stubs alone, for a test that loads a tree itself (one it has
    edited, or one that must refuse to load): the core's and this
    package's, installed for the length of the test. The command journal
    is returned."""
    return kit.stub_core(monkeypatch, FIXTURE / kit.IDENTITY_FILE, STUBS)


@pytest.fixture
def family_root(tmp_path: Path) -> Path:
    """A private copy of the family's fixture, for a test to edit before
    it loads it."""
    return kit.copy_fixture(FIXTURE, tmp_path)
