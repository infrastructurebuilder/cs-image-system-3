# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Identity leaves the core: the commands, the user fields and the
container-runtime verdict that belong to an identity plugin reach the
system through the contract -- a command mount, an injected item model, a
group-builder hook -- and exist exactly when the plugin is installed.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
import typer
from harness import copy_config, load_context, stub_environment
from test_container_runtime import IMAGE, RUNTIME, _stub_daemon, docker_overlay, dummy_group
from typer.testing import CliRunner

from cs_image_system.contract.commands import CommandMount

runner = CliRunner()


# ------------------------------------------------------------ the mount record

def test_a_mount_is_a_sub_app_or_a_command_never_both():
    sub = typer.Typer()
    assert CommandMount(name="x", app=sub).is_app
    assert not CommandMount(name="y", path=("verify",), callback=lambda: None).is_app
    with pytest.raises(ValueError, match="exactly one of app and callback"):
        CommandMount(name="x")
    with pytest.raises(ValueError, match="exactly one of app and callback"):
        CommandMount(name="x", app=sub, callback=lambda: None)
    with pytest.raises(ValueError, match="path must be empty"):
        CommandMount(name="x", app=sub, path=("verify",))
    with pytest.raises(ValueError, match="deferred_load is a sub-app's setting"):
        CommandMount(name="x", path=("verify",), callback=lambda: None, deferred_load=True)
    with pytest.raises(ValueError, match="needs a name"):
        CommandMount(name=" ", app=sub)


# ------------------------------------------------------------ the mounting

def _root() -> tuple[typer.Typer, typer.Typer]:
    root = typer.Typer()
    verify = typer.Typer(help="verify things")
    root.add_typer(verify, name="verify")

    @verify.command(name="instance")
    def _instance() -> None:
        typer.echo("instance verified")
    return root, verify


def test_the_cli_mounts_a_stub_plugins_sub_app_and_a_command_under_verify(monkeypatch):
    from cs_image_system.system import cli
    root, _ = _root()
    stub = typer.Typer(help="a stub plugin's sub-app")

    @stub.command(name="hello")
    def _hello() -> None:
        typer.echo("hello from the stub")

    def _login(name: str = typer.Argument("nobody")) -> None:
        """Log in as a stub."""
        typer.echo(f"stub login {name}")

    mounts = [CommandMount(name="stub", app=stub, deferred_load=True),
              CommandMount(name="login", path=("verify",), callback=_login)]
    monkeypatch.setattr(cli, "entry_points",
                        lambda group: [SimpleNamespace(name="stub_plugin", load=lambda: (lambda: mounts))])
    assert cli.plugin_command_mounts() == mounts, "the monkeypatched entry-point list is what gets read"
    assert cli.mount_plugin_commands(root) == ["stub", "verify/login"]
    assert runner.invoke(root, ["stub", "hello"]).output.strip() == "hello from the stub"
    assert runner.invoke(root, ["verify", "login", "pat"]).output.strip() == "stub login pat"
    assert runner.invoke(root, ["verify", "instance"]).output.strip() == "instance verified"
    assert "stub" in cli.deferred_load_commands()
    # a second owner of a name is a packaging error, not a silent replacement
    with pytest.raises(ValueError, match="already mounted"):
        cli.mount_plugin_commands(root, [CommandMount(name="instance", path=("verify",), callback=_login)])
    with pytest.raises(ValueError, match="already mounted"):
        cli.mount_plugin_commands(root, [CommandMount(name="verify", app=typer.Typer())])
    with pytest.raises(ValueError, match="no sub-app 'nope'"):
        cli.mount_plugin_commands(root, [CommandMount(name="x", path=("nope",), callback=_login)])


def test_a_shared_callback_mounts_once_and_two_different_callbacks_refuse():
    """The shared-command rule: two stub plugins mounting the SAME callback
    (or the same sub-app object) are one command; a different one under a
    taken name is refused."""
    from cs_image_system.system import cli
    root, verify = _root()

    def _shared() -> None:
        typer.echo("shared")

    def _other() -> None:
        typer.echo("other")
    shared_app = typer.Typer(help="shared sub-app")
    pair = [CommandMount(name="login", path=("verify",), callback=_shared),
            CommandMount(name="tools", app=shared_app),
            CommandMount(name="login", path=("verify",), callback=_shared),     # the second plugin, same object
            CommandMount(name="tools", app=shared_app)]
    assert cli.mount_plugin_commands(root, pair) == ["verify/login", "tools"]
    assert [c.name for c in verify.registered_commands].count("login") == 1
    assert [g.name for g in root.registered_groups].count("tools") == 1
    assert runner.invoke(root, ["verify", "login"]).output.strip() == "shared"
    with pytest.raises(ValueError, match="already mounted"):
        cli.mount_plugin_commands(root, [CommandMount(name="login", path=("verify",), callback=_other)])
    with pytest.raises(ValueError, match="already mounted"):
        cli.mount_plugin_commands(root, [CommandMount(name="tools", app=typer.Typer())])


def _entry(name: str, mounts_fn) -> SimpleNamespace:
    return SimpleNamespace(name=name, load=lambda: mounts_fn)


def test_which_commands_each_identity_plugin_brings_through_its_entry_point(monkeypatch):
    """The same rule over the posix plugin and a stub identity plugin that
    brings a sub-app of its own beside the shared `verify login`."""
    from cs_image_system.engine.commands.login_proof import verify_login_command
    from cs_image_system.posix_identity_plugin.cli import command_mounts as posix_mounts
    from cs_image_system.system import cli
    stub_app = typer.Typer(help="a stub identity plugin's own commands")

    @stub_app.command(name="status")
    def _status() -> None:
        typer.echo("stub status")

    def stub_mounts() -> list[CommandMount]:
        return [CommandMount(name="stubtool", app=stub_app),
                CommandMount(name="login", path=("verify",), callback=verify_login_command)]
    # no identity plugin: neither command
    root, verify = _root()
    monkeypatch.setattr(cli, "entry_points", lambda group: [])
    assert cli.mount_plugin_commands(root) == []
    assert "login" not in {c.name for c in verify.registered_commands}
    result = runner.invoke(root, ["verify", "login"])
    assert result.exit_code != 0 and "No such command" in result.output
    # the posix plugin alone: `verify login`, nothing else
    root, verify = _root()
    monkeypatch.setattr(cli, "entry_points", lambda group: [_entry("posix_identity_plugin", posix_mounts)])
    assert cli.mount_plugin_commands(root) == ["verify/login"]
    assert "stubtool" not in {g.name for g in root.registered_groups}
    assert [c.callback for c in verify.registered_commands if c.name == "login"] == [verify_login_command]
    # the stub alone: its own sub-app and the shared command
    root, verify = _root()
    monkeypatch.setattr(cli, "entry_points", lambda group: [_entry("stub_identity_plugin", stub_mounts)])
    assert cli.mount_plugin_commands(root) == ["stubtool", "verify/login"]
    assert runner.invoke(root, ["stubtool", "status"]).output.strip() == "stub status"
    # both installed: one `verify login`, the core's callback
    root, verify = _root()
    monkeypatch.setattr(cli, "entry_points", lambda group: [_entry("posix_identity_plugin", posix_mounts),
                                                             _entry("stub_identity_plugin", stub_mounts)])
    assert cli.mount_plugin_commands(root) == ["verify/login", "stubtool"]
    logins = [c for c in verify.registered_commands if c.name == "login"]
    assert len(logins) == 1 and logins[0].callback is verify_login_command


# ------------------------------------------------------------ the user model


# ------------------------------------------------------- the container runtime

def test_an_identity_plugin_that_says_nothing_about_containers_objects_and_posix_does_not():
    from cs_image_system.base.basic.builder_base_group import GroupBuilderBase
    from cs_image_system.dummy_plugin.dummy_builders import DummyGroupBuilder
    from cs_image_system.posix_identity_plugin.posix_builders import PosixGroupBuilder
    assert PosixGroupBuilder.container_runtime_objection(cast(Any, None)) is None
    dummy = DummyGroupBuilder.container_runtime_objection(cast(Any, DummyGroupBuilder.__new__(DummyGroupBuilder)))
    assert dummy and "'dummy'" in dummy, "a plugin that has not said it works in a container is not assumed to"

    class _Other(GroupBuilderBase):
        @classmethod
        def identity_type(cls) -> str:
            return "other"
    default = GroupBuilderBase.container_runtime_objection(cast(Any, _Other.__new__(_Other)))
    assert default and "'other'" in default


def test_validate_refuses_an_objecting_group_and_accepts_a_posix_group_on_a_container_runtime(tmp_path, monkeypatch):
    from cs_image_system.engine.commands.validate import check_container_runtimes
    stub_environment(monkeypatch)
    _stub_daemon(monkeypatch)
    root = copy_config(tmp_path)
    docker_overlay(root, group=dummy_group(root))               # the template builder objects by default
    ctx = load_context(root)
    errors = [str(e) for e in check_container_runtimes(ctx)]
    assert len(errors) == 1 and IMAGE in errors[0] and RUNTIME in errors[0] and "(dummy)" in errors[0], errors
    assert errors[0].endswith(ctx.group_builders["dummy-groups"].container_runtime_objection() or "?"), \
        "the sentence ends with the builder's own objection"
    root = copy_config(tmp_path, "posix-tree")
    docker_overlay(root)                                      # pxgroup, a posix group
    assert check_container_runtimes(load_context(root)) == []


# --------------------------------------------------------- the core's words

def test_the_core_reads_the_accounts_report_and_the_alias_verdict_by_the_contracts_words():
    """The core's half: the accounts report and the alias verdict are read by
    the contract's constants, and the alias script is a builder's, not the core's."""
    import inspect

    from cs_image_system.contract.group import ACCOUNTS_IN_PLACE, ACCOUNTS_REPORT_PREFIX, ALIASES_CHANGED
    from cs_image_system.engine import accounts_reconcile, provider_aliases
    assert ACCOUNTS_IN_PLACE.startswith(ACCOUNTS_REPORT_PREFIX) and ALIASES_CHANGED
    assert "ACCOUNTS_IN_PLACE" in inspect.getsource(accounts_reconcile)
    assert "ALIASES_CHANGED" in inspect.getsource(provider_aliases)
    assert "alias_registration_script" in inspect.getsource(provider_aliases)
    assert not hasattr(provider_aliases, "alt_names_script") and not hasattr(provider_aliases, "SFTD_YAML")
