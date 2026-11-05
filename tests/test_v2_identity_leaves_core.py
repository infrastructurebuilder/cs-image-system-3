# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Identity leaves the core: the commands, the user fields and the
container-runtime verdict that belong to an identity plugin reach the
system through the contract -- a command mount, an injected item model, a
group-builder hook -- and exist exactly when the plugin is installed.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import typer
from typer.testing import CliRunner

from cs_image_system.contract.commands import CommandMount
from cs_image_system.contract.constants import VCT

from test_v2_stage_103 import IMAGE, RUNTIME, _stub_daemon, docker_overlay
from v2_support import copy_config, load_context, reset_singletons, stub_environment

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


def test_which_commands_each_identity_plugins_entry_point_brings(monkeypatch):
    from cs_image_system.system import cli
    from cs_image_system.okta_opa_plugin.cli import command_mounts as okta_mounts
    from cs_image_system.posix_identity_plugin.cli import command_mounts as posix_mounts
    # no identity plugin: neither command
    root, verify = _root()
    monkeypatch.setattr(cli, "entry_points", lambda group: [])
    assert cli.mount_plugin_commands(root) == []
    assert "workload" not in {g.name for g in root.registered_groups}
    assert "login" not in {c.name for c in verify.registered_commands}
    result = runner.invoke(root, ["verify", "login"])
    assert result.exit_code != 0 and "No such command" in result.output
    # the posix plugin alone: `verify login` present, `workload` absent
    root, verify = _root()
    monkeypatch.setattr(cli, "entry_points", lambda group: [_entry("posix_identity_plugin", posix_mounts)])
    assert cli.mount_plugin_commands(root) == ["verify/login"]
    assert "workload" not in {g.name for g in root.registered_groups}
    assert "login" in {c.name for c in verify.registered_commands}
    # okta-opa alone: both
    root, verify = _root()
    monkeypatch.setattr(cli, "entry_points", lambda group: [_entry("okta_opa_plugin", okta_mounts)])
    assert cli.mount_plugin_commands(root) == ["workload", "verify/login"]
    assert "workload" in {g.name for g in root.registered_groups}
    assert "login" in {c.name for c in verify.registered_commands}
    # both installed (name order): one `verify login`, the core's callback
    from cs_image_system.base.commands.login_proof import verify_login_command
    root, verify = _root()
    monkeypatch.setattr(cli, "entry_points", lambda group: [_entry("okta_opa_plugin", okta_mounts),
                                                             _entry("posix_identity_plugin", posix_mounts)])
    assert cli.mount_plugin_commands(root) == ["workload", "verify/login"]
    logins = [c for c in verify.registered_commands if c.name == "login"]
    assert len(logins) == 1 and logins[0].callback is verify_login_command


def test_the_installed_cli_carries_the_okta_commands_from_the_real_entry_point(monkeypatch):
    """The console script read the installed entry point at import: the two
    commands answer `--help` without a tree (the root callback reads the
    help request off the process arguments, which the runner sets here)."""
    import sys
    from typer.main import get_command
    from cs_image_system.system.cli import app
    from cs_image_system.base.commands.login_proof import verify_login_command
    assert "workload" in {g.name for g in app.registered_groups}
    assert [c.callback for g in app.registered_groups if g.name == "verify" and g.typer_instance
            for c in g.typer_instance.registered_commands if c.name == "login"] == [verify_login_command]
    root = get_command(app)
    verify = root.commands["verify"]  # type: ignore[attr-defined]
    assert "login" in verify.commands and "workload" in root.commands  # type: ignore[attr-defined]
    for args in (["workload", "--help"], ["verify", "login", "--help"], ["workload", "token", "--help"]):
        monkeypatch.setattr(sys, "argv", ["cs-image-system", *args])
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        assert "Usage: " in result.output


# ------------------------------------------------------------ the user model

def _with_a_profile_field(root: Path) -> None:
    path = root / "groups" / "users.yaml"
    text = path.read_text()
    old = "    last_name: Alpha\n"
    assert old in text
    path.write_text(text.replace(old, old + '    mobile_phone: "+1-555-0100"\n    department: Modeling\n', 1))


def test_a_tree_with_okta_profile_fields_loads_with_the_plugin_and_is_refused_without_it(tmp_path, monkeypatch):
    from cs_image_system.base.global_context import read_config_and_transform
    from cs_image_system.base.models.user import User
    from cs_image_system.base.registry import Registry
    from cs_image_system.okta_opa_plugin.okta_user import OktaUser
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    _with_a_profile_field(root)
    ctx = load_context(root)
    avery = next(u for u in ctx.users if u.first_name == "Avery")
    assert isinstance(avery, OktaUser) and isinstance(avery, User)
    assert avery.mobile_phone == "+1-555-0100" and avery.department == "Modeling"
    assert avery.get_display_name() == avery.name, "the base display name survives the profile field of that name"
    assert avery.get_self_injected_name() == "user", "templates say {{ user.name }} whatever the subclass"
    assert "{{" not in str(avery.email) and str(avery.email).startswith(avery.name)
    others = [u for u in ctx.users if u is not avery]
    assert others and all(isinstance(u, OktaUser) and u.mobile_phone is None for u in others)
    # the plugin's emitter reads the fields from the subclass
    from cs_image_system.okta_opa_plugin.okta_tf_models import OktaTFUser
    hcl = "\n".join(OktaTFUser(avery, provider="okta.x").generate_terraform())
    assert 'mobile_phone = "+1-555-0100"' in hcl and 'department = "Modeling"' in hcl
    # without the plugin's injected model, the core's User is the item model and the keys are unknown
    reset_singletons()
    reg = Registry()
    reg.models[VCT.USER_MODEL].clear()
    reg.defaults_registry.pop(VCT.USER_MODEL, None)
    with pytest.raises(Exception, match="mobile_phone|department|[Ee]xtra"):
        read_config_and_transform(cast(Any, SimpleNamespace(obj={})), root, False, dry_run=True, overlays=[],
                                  undeclare=[])


def test_the_core_user_carries_no_profile_field():
    import dataclasses
    from cs_image_system.base.models.user import User
    from cs_image_system.okta_opa_plugin.okta_user import OKTA_PROFILE_FIELDS
    names = {f.name for f in dataclasses.fields(User)}
    assert not names & set(OKTA_PROFILE_FIELDS), names & set(OKTA_PROFILE_FIELDS)
    assert {"name", "first_name", "last_name", "middle_name", "email", "description", "is_service_account",
            "is_enabled", "managed", "attributes", "uid", "public_keys"} <= names
    assert not hasattr(User, "as_profile")


# ------------------------------------------------------- the container runtime

def test_each_identity_plugin_answers_the_container_runtime_question():
    from cs_image_system.base.basic.builder_base_group import GroupBuilderBase
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    from cs_image_system.posix_identity_plugin.posix_builders import PosixGroupBuilder
    okta = OktaTfGroupBuilder.container_runtime_objection(cast(Any, None))
    assert okta and "sftd" in okta and "container" in okta
    assert PosixGroupBuilder.container_runtime_objection(cast(Any, None)) is None

    class _Other(GroupBuilderBase):
        @classmethod
        def identity_type(cls) -> str:
            return "other"
    default = GroupBuilderBase.container_runtime_objection(cast(Any, _Other.__new__(_Other)))
    assert default and "'other'" in default, "an identity type that has not said it works in a container is not assumed to"


def test_validate_refuses_an_okta_group_and_accepts_a_posix_group_on_a_container_runtime(tmp_path, monkeypatch):
    from cs_image_system.base.commands.validate import check_container_runtimes
    stub_environment(monkeypatch)
    _stub_daemon(monkeypatch)
    root = copy_config(tmp_path)
    docker_overlay(root, group="coops")                       # an okta group
    errors = [str(e) for e in check_container_runtimes(load_context(root))]
    assert len(errors) == 1 and IMAGE in errors[0] and RUNTIME in errors[0] and "(okta)" in errors[0], errors
    assert "sftd" in errors[0], "the sentence ends with the okta builder's own objection"
    root = copy_config(tmp_path, "posix-tree")
    docker_overlay(root)                                      # pxgroup, a posix group
    assert check_container_runtimes(load_context(root)) == []


# --------------------------------------------------------- the core's words

def test_the_core_reads_the_accounts_report_and_the_alias_verdict_by_the_contract():
    import inspect
    from cs_image_system.base import accounts_reconcile, provider_aliases
    from cs_image_system.contract.group import ACCOUNTS_IN_PLACE, ACCOUNTS_REPORT_PREFIX, ALIASES_CHANGED
    from cs_image_system.okta_opa_plugin.server_aliases import alt_names_script
    assert ACCOUNTS_IN_PLACE.startswith(ACCOUNTS_REPORT_PREFIX)
    assert "ACCOUNTS_IN_PLACE" in inspect.getsource(accounts_reconcile)
    assert "ALIASES_CHANGED" in inspect.getsource(provider_aliases)
    assert "alias_registration_script" in inspect.getsource(provider_aliases)
    assert not hasattr(provider_aliases, "alt_names_script") and not hasattr(provider_aliases, "SFTD_YAML")
    assert ALIASES_CHANGED in alt_names_script(["a-b"])


def test_the_state_query_words_for_workload_access_are_the_plugins(tmp_path, monkeypatch):
    from cs_image_system.base import state_query as sq
    from cs_image_system.contract.group import WORKLOAD_CONNECTION_INACTIVE, WORKLOAD_ROLE_ABSENT
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    gb = next(b for b in ctx.group_builders.values() if isinstance(b, OktaTfGroupBuilder))
    expected = {"role": "ci-role", "policy": "g_v1_security_policy_ci", "mirrors": "g_v1_security_policy_user"}
    real = {"role": {"present": False}, "policy": {"present": False}}
    [drift] = sq.workload_drift("g", expected, real, gb)
    assert "CI_SETUP.md section 3.5" in drift.detail and "OPA" in drift.detail
    [plain] = sq.workload_drift("g", expected, real)                     # no builder: the core's words
    assert "OPA" not in plain.detail and "ci-role" in plain.detail
    assert "DRAFT" in gb.workload_access_detail(WORKLOAD_CONNECTION_INACTIVE, expected, real)
    assert "OPA" in gb.workload_access_detail(WORKLOAD_ROLE_ABSENT, expected, real)
