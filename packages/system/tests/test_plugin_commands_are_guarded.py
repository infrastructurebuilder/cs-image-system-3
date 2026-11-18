# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A plugin's commands that cannot be used are skipped and named, and the
command line still starts.

The plugins' commands are mounted when the command line is imported, so a
plugin that broke there would take ``--help`` and every command with it.
Held on entry points the test supplies: a commands entry point that fails
is skipped with one error line; two plugins mounting different things
under one name are both skipped and both named; a plugin that takes a
built-in command's name is skipped whole; and in each case the other
plugins' commands are mounted and ``--help`` answers.
"""
from __future__ import annotations

import logging
import types
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from cs_image_system.contract.commands import CommandMount
from cs_image_system.system import cli

runner = CliRunner()


def _root() -> typer.Typer:
    """A command line in miniature: a root with one built-in sub-app and
    one built-in command under it."""
    root, verify = typer.Typer(), typer.Typer()

    @root.callback()
    def _main() -> None:
        """the root"""

    @verify.command(name="instance")
    def _instance() -> None:
        typer.echo("instance verified")
    root.add_typer(verify, name="verify")
    return root


def _says(word: str):
    def command() -> None:
        typer.echo(word)
    return command


def _point(name: str, answer: Any) -> Any:
    def load() -> Any:
        if isinstance(answer, Exception):
            raise answer
        return lambda: answer
    return types.SimpleNamespace(name=name, dist=types.SimpleNamespace(name=f"cs-image-system-{name}-plugin"), load=load)


def _mount(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, *points: Any):
    root = _root()
    monkeypatch.setattr(cli, "entry_points", lambda group: list(points))
    with caplog.at_level(logging.ERROR):
        mounted = cli.mount_plugin_commands(root)
    return root, mounted, [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]


def _help_answers(root: typer.Typer) -> bool:
    return runner.invoke(root, ["--help"]).exit_code == 0


def test_a_commands_entry_point_that_fails_is_skipped_named_and_help_still_answers(monkeypatch, caplog):
    root, mounted, lines = _mount(monkeypatch, caplog, _point("broken", ImportError("gone")),
                                  _point("stranger", ["not a mount"]),
                                  _point("sound", [CommandMount(name="hello", path=("verify",), callback=_says("hello"))]))
    assert mounted == ["verify/hello"] and _help_answers(root)
    assert runner.invoke(root, ["verify", "hello"]).output.strip() == "hello"
    assert len(lines) == 2
    assert "broken (cs-image-system-broken-plugin)" in lines[0] and "gone" in lines[0]
    assert "stranger (cs-image-system-stranger-plugin)" in lines[1]


def test_two_plugins_mounting_different_commands_under_one_name_are_both_skipped_and_named(monkeypatch, caplog):
    pair = [_point("alpha", [CommandMount(name="login", path=("verify",), callback=_says("alpha")),
                             CommandMount(name="alpha-only", path=("verify",), callback=_says("only"))]),
            _point("beta", [CommandMount(name="login", path=("verify",), callback=_says("beta"))])]
    sound = _point("sound", [CommandMount(name="hello", path=("verify",), callback=_says("hello"))])
    for points in (pair, list(reversed(pair))):
        caplog.clear()
        root, mounted, lines = _mount(monkeypatch, caplog, *points, sound)
        assert mounted == ["verify/hello"] and _help_answers(root)          # neither wins; nothing of either mounts
        assert runner.invoke(root, ["verify", "login"]).exit_code != 0
        assert runner.invoke(root, ["verify", "alpha-only"]).exit_code != 0
        assert len(lines) == 1 and "alpha" in lines[0] and "beta" in lines[0] and "command 'verify/login'" in lines[0]


def test_the_same_callback_from_two_plugins_is_one_command(monkeypatch, caplog):
    shared = _says("shared")
    root, mounted, lines = _mount(monkeypatch, caplog,
                                  _point("alpha", [CommandMount(name="login", path=("verify",), callback=shared)]),
                                  _point("beta", [CommandMount(name="login", path=("verify",), callback=shared)]))
    assert mounted == ["verify/login"] and lines == []
    assert runner.invoke(root, ["verify", "login"]).output.strip() == "shared"


def test_a_plugin_that_takes_a_built_in_commands_name_is_skipped_whole(monkeypatch, caplog):
    grabby = _point("grabby", [CommandMount(name="extra", path=("verify",), callback=_says("extra")),
                               CommandMount(name="instance", path=("verify",), callback=_says("mine now"))])
    root, mounted, lines = _mount(monkeypatch, caplog, grabby)
    assert mounted == [] and _help_answers(root)
    assert runner.invoke(root, ["verify", "instance"]).output.strip() == "instance verified"
    assert runner.invoke(root, ["verify", "extra"]).exit_code != 0           # nothing of the plugin was mounted
    assert len(lines) == 1 and "grabby (cs-image-system-grabby-plugin)" in lines[0] and "verify/instance" in lines[0]


def test_a_plugin_may_mount_commands_under_a_sub_app_it_mounts_itself(monkeypatch, caplog):
    tools = typer.Typer()

    @tools.command(name="list")
    def _list() -> None:
        typer.echo("tools listed")
    root, mounted, lines = _mount(monkeypatch, caplog, _point("sound", [CommandMount(name="tools", app=tools)]))
    assert mounted == ["tools"] and lines == []
    assert runner.invoke(root, ["tools", "list"]).output.strip() == "tools listed"


def test_a_command_listed_before_the_sub_app_it_goes_under_skips_the_plugin_and_nothing_raises(monkeypatch, caplog):
    """A plugin's mounts are judged in the order they will be mounted: a
    command under a sub-app the plugin mounts LATER has nowhere to go yet.
    The plugin is skipped whole, in one line, and the command line starts."""
    tools = typer.Typer()
    backwards = _point("backwards", [CommandMount(name="list", path=("tools",), callback=_says("listed")),
                                     CommandMount(name="tools", app=tools)])
    sound = _point("sound", [CommandMount(name="hello", path=("verify",), callback=_says("hello"))])
    root, mounted, lines = _mount(monkeypatch, caplog, backwards, sound)
    assert mounted == ["verify/hello"] and _help_answers(root)
    assert runner.invoke(root, ["tools", "list"]).exit_code != 0             # nothing of the plugin was mounted
    assert len(lines) == 1 and "backwards (cs-image-system-backwards-plugin)" in lines[0] and "tools/list" in lines[0]


def test_a_command_under_a_nested_sub_app_that_does_not_exist_skips_the_plugin(monkeypatch, caplog):
    tools = typer.Typer()
    lost = _point("lost", [CommandMount(name="tools", app=tools),
                           CommandMount(name="deep", path=("tools", "nowhere"), callback=_says("deep"))])
    root, mounted, lines = _mount(monkeypatch, caplog, lost)
    assert mounted == [] and _help_answers(root)
    assert "tools" not in {g.name for g in root.registered_groups}          # not even its sub-app: skipped whole
    assert len(lines) == 1 and "lost (cs-image-system-lost-plugin)" in lines[0]


def test_a_command_under_a_sub_app_the_plugin_mounted_first_is_mounted(monkeypatch, caplog):
    tools = typer.Typer()
    forwards = _point("forwards", [CommandMount(name="tools", app=tools),
                                   CommandMount(name="list", path=("tools",), callback=_says("listed"))])
    root, mounted, lines = _mount(monkeypatch, caplog, forwards)
    assert mounted == ["tools", "tools/list"] and lines == []
    assert runner.invoke(root, ["tools", "list"]).output.strip() == "listed"


def test_a_plugin_mounting_a_kit_command_this_command_line_lacks_is_skipped_and_nothing_raises(monkeypatch, caplog):
    """A plugin built against a later contract may name a kit command this
    command line does not carry. Nothing can be mounted for it: the plugin
    is skipped whole, in one line, and the command line starts."""
    from cs_image_system.contract import commands as contract_commands
    monkeypatch.setattr(contract_commands, "KIT_COMMANDS", (*contract_commands.KIT_COMMANDS, "a-newer-kit-command"))
    newer = _point("newer", [CommandMount(name="extra", path=("verify",), callback=_says("extra")),
                             CommandMount(name="later", path=("verify",), kit_command="a-newer-kit-command")])
    sound = _point("sound", [CommandMount(name="hello", path=("verify",), callback=_says("hello"))])
    root, mounted, lines = _mount(monkeypatch, caplog, newer, sound)
    assert mounted == ["verify/hello"] and _help_answers(root)
    assert runner.invoke(root, ["verify", "extra"]).exit_code != 0             # nothing of the plugin was mounted
    assert len(lines) == 1 and "newer (cs-image-system-newer-plugin)" in lines[0] and "a-newer-kit-command" in lines[0]
