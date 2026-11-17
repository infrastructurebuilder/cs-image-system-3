# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The check a plugin runs against itself finds every way of reaching past
the surface, and nothing else.

Held on small source trees the test writes, against a surface the test
declares: a listed name passes; an unlisted name, an underscore member
that is no declared hook, the engine, the command line and another plugin
are each found, with the file, the line and the reason; the plugin's own
packages and the plugins it declares as dependencies pass; and a plugin's
tests may also import the test kit.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.base.surface import check, cli

KIT = "cs_image_system.base"


@pytest.fixture(autouse=True)
def surface(monkeypatch: pytest.MonkeyPatch) -> None:
    """A kit that lists one module with two names and one hook, and keeps
    one more underscore member private; the other libraries list nothing."""
    def declared(library: str) -> check.Declared | None:
        if library != KIT:
            return check.Declared(library, "9.9.9", {}, frozenset(), frozenset())
        return check.Declared(KIT, "0.2.0", {f"{KIT}.models.thing": frozenset({"Thing", "make"})},
                              frozenset({"_hook"}), frozenset({"_hook", "_secret"}))
    monkeypatch.setattr(check, "declared", declared)


def _plugin(tmp_path: Path, body: str, name: str = "mine") -> Path:
    src = tmp_path / "src"
    package = src / "cs_image_system" / name
    package.mkdir(parents=True)
    (package / "main.py").write_text(body)
    return src


def _reasons(src: Path, **kwargs) -> list[tuple[str, str]]:
    return [(f.what, f.reason.split(" 0.")[0].split(" 9.")[0]) for f in check.findings(src, **kwargs)]


def test_a_listed_name_and_a_declared_hook_pass(tmp_path: Path):
    src = _plugin(tmp_path, f"from {KIT}.models.thing import Thing, make\n"
                            "from cs_image_system.contract.constants import VCT\n"
                            "from cs_image_system.mine.other import helper\n"
                            "class Mine(Thing):\n    def _hook(self):\n        return self._hook\n")
    assert check.findings(src) == []


def test_an_unlisted_name_is_found_with_its_file_line_and_library(tmp_path: Path):
    src = _plugin(tmp_path, f"import os\nfrom {KIT}.models.thing import Thing, hidden\nfrom {KIT}.internals import x\n")
    found = check.findings(src)
    assert [(f.file, f.line, f.what) for f in found] == [
        ("cs_image_system/mine/main.py", 2, f"from {KIT}.models.thing import hidden"),
        ("cs_image_system/mine/main.py", 3, f"from {KIT}.internals import x")]
    assert all(f.reason == f"{check.NOT_LISTED} {KIT} 0.2.0" for f in found)


def test_an_underscore_member_that_is_no_hook_is_private(tmp_path: Path):
    src = _plugin(tmp_path, f"from {KIT}.models.thing import Thing\n"
                            "class Mine(Thing):\n"
                            "    def _secret(self):\n        return getattr(self, '_secret')\n"
                            "    def _my_own(self):\n        return self._my_own\n")
    assert _reasons(src) == [("_secret", f"{check.PRIVATE} {KIT}")] * 2


@pytest.mark.parametrize("line, reason", [
    ("from cs_image_system.engine.loader import discover_plugins", check.ENGINE),
    ("import cs_image_system.system.cli", check.ENGINE),
    ("from cs_image_system.someone_else.models import Theirs", check.ANOTHER),
])
def test_the_engine_the_command_line_and_another_plugin_are_found(tmp_path: Path, line: str, reason: str):
    assert [r for _, r in _reasons(_plugin(tmp_path, line + "\n"))] == [reason]


def test_a_plugin_named_as_family_may_be_imported(tmp_path: Path):
    src = _plugin(tmp_path, "from cs_image_system.someone_else.models import Theirs\n")
    assert check.findings(src, family=["cs_image_system.someone_else"]) == []


def test_tests_may_import_the_test_kit_and_reach_into_what_they_test(tmp_path: Path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_it.py").write_text("from cs_image_system.system import testing as kit\n"
                                      "from cs_image_system.system.testing import double\n"
                                      "from cs_image_system.mine.testing import stub\n"
                                      f"from {KIT}.models.thing import Thing\n"
                                      "def test_it():\n    assert Thing()._secret\n")
    assert check.findings(tests, own=["cs_image_system.mine"], family=[], tests=True) == []
    (tests / "test_bad.py").write_text("from cs_image_system.engine.loader import discover_plugins\n"
                                       f"from {KIT}.models.thing import hidden\n")
    assert sorted(r for _, r in _reasons(tests, own=["cs_image_system.mine"], family=[], tests=True)) == [
        check.ENGINE, f"{check.NOT_LISTED} {KIT}"]


def test_the_command_prints_each_finding_and_exits_1_or_says_it_keeps_and_exits_0(tmp_path: Path, capsys):
    good = _plugin(tmp_path / "a", f"from {KIT}.models.thing import Thing\n")
    assert cli.main(["check", str(good)]) == 0
    bad = _plugin(tmp_path / "b", "from cs_image_system.engine import loader\n")
    assert cli.main(["check", str(bad)]) == 1
    out = capsys.readouterr().out
    assert "cs_image_system/mine/main.py:1: from cs_image_system.engine import loader" in out
