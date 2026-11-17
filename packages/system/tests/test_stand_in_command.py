# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The modification tests never pass without having run.

``test-mods`` needs a local container, supplied by the installed runtime
that declares itself a stand-in. Held here, over the core's own fixture
(whose one runtime, the test-double, is no stand-in), with the run's
registry answering for the test-double alone so the result is the same
whatever else is installed beside the core: with none installed
the command fails and says the tests did not run; ``--allow-not-run``
records the exclusion and exits 0; a stand-in whose daemon does not answer
is the same; and two stand-ins with none named is refused before anything
is tested.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cs_image_system.base.registry import Registry
from cs_image_system.system import testing as kit
from cs_image_system.system.cli import app
from cs_image_system.system.testing import double

FIXTURE = Path(__file__).resolve().parent / "fixture"


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private copy of the core fixture, with the core's stubs and the
    test-double in place for the commands the test invokes."""
    kit.stub_core(monkeypatch, FIXTURE / kit.IDENTITY_FILE, (double.stub,))
    monkeypatch.setattr(Registry, "runtime_builder_classes",
                        lambda self: {double.DOUBLE: double.DoubleRuntimeBuilder})
    return kit.copy_fixture(FIXTURE, tmp_path)


def _test_mods(root: Path, *args: str):
    result = CliRunner().invoke(app, ["--root-dir", str(root), "test-mods", *args])
    return result.exit_code, result.output


def _offer(monkeypatch: pytest.MonkeyPatch, factory) -> None:
    """Make the test-double declare itself a stand-in with ``factory``."""
    monkeypatch.setattr(double.DoubleRuntimeBuilder, "local_test_target", classmethod(lambda cls: factory))


def test_with_no_stand_in_installed_the_tests_did_not_run_and_the_command_fails(tree: Path):
    rc, out = _test_mods(tree)
    assert rc == 1 and "did not run" in out and "no installed plugin can serve" in out


def test_the_exclusion_is_explicit_and_then_the_command_exits_0(tree: Path):
    rc, out = _test_mods(tree, "--allow-not-run")
    assert rc == 0 and "did not run" in out and "--allow-not-run" in out


def test_a_stand_in_whose_daemon_does_not_answer_did_not_run_either(tree: Path, monkeypatch: pytest.MonkeyPatch):
    _offer(monkeypatch, lambda image, executables=None: None)        # the factory finds no daemon
    rc, out = _test_mods(tree)
    assert rc == 1 and f"stand-in: {double.DOUBLE} (the only one installed)" in out
    assert f"{double.DOUBLE} did not answer" in out and "did not run" in out
    rc, _ = _test_mods(tree, "--allow-not-run")
    assert rc == 0


def test_two_stand_ins_and_none_named_is_refused_before_anything_is_tested(tree: Path, monkeypatch: pytest.MonkeyPatch):
    from cs_image_system.system import cli
    other = type("Other", (), {"csis_name": classmethod(lambda cls: "another"),
                               "local_test_target": classmethod(lambda cls: lambda image, executables=None: None)})
    _offer(monkeypatch, lambda image, executables=None: None)
    monkeypatch.setattr(cli, "stand_in_runtime_type",
                        lambda classes, named=None: cli_choice({**classes, "another": other}, named))
    ran: list[str] = []
    monkeypatch.setattr(cli, "run_mod_tests", lambda *a, **k: ran.append("ran") or [])
    rc, out = _test_mods(tree)
    assert rc == 1 and "name one with --stand-in" in out and "another" in out and double.DOUBLE in out
    assert ran == []
    rc, out = _test_mods(tree, "--stand-in", "another")
    assert rc == 0 and "stand-in: another (named with --stand-in)" in out and ran == ["ran"]


def cli_choice(classes, named):
    from cs_image_system.base.image_sources import stand_in_runtime_type
    return stand_in_runtime_type(classes, named)
