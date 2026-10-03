# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 75: a POSIX identity plugin, alone and beside Okta.

Step 2, the decoupling: the core's launch renderers and its login proof
name no identity agent. The group builder's enrollment KIND (recorded in the
launch parameters) is rendered by whichever plugin registered it, and a kind
no plugin renders is refused, never skipped; the login proof asks the
group's builder for its checks. OPA's steps moved to the Okta plugin
unchanged to the byte -- the golden is that proof, since every machine's
user-data hash is recorded.
"""
from __future__ import annotations

import inspect
from typing import Any

import pytest
import yaml

from cs_image_system.base import ansible_launch, launch_enrollment, launch_params
from cs_image_system.base.basic.builder_base_group import GroupBuilderBase
from cs_image_system.base.commands import login_proof


def _params(kind: str | None) -> dict:
    return {"hostname": "box-001", "image": "img", "build": "b1", "group": None, "mounts": [],
            "enrollment": ({"enrollment": kind} if kind else {}), "session": None}


@pytest.fixture
def kinds():
    """The registry as it stands, restored afterwards (the Okta plugin's kind
    is registered at import and must survive)."""
    saved = dict(launch_enrollment._KINDS)
    try:
        yield launch_enrollment._KINDS
    finally:
        launch_enrollment._KINDS.clear()
        launch_enrollment._KINDS.update(saved)


# ------------------------------------------------------------- step 2: the seams

def test_the_core_renderers_and_login_proof_name_no_agent():
    for module, words in ((launch_params, ("sftd-token", "/var/lib/sftd", "/etc/sft")),
                          (ansible_launch, ("sftd-token", "/var/lib/sftd", "sftd")),
                          (login_proof, ("run_sft", "subprocess", "OPA_TOKEN\")", "SFT_TEAM"))):
        code = "\n".join(line for line in inspect.getsource(module).splitlines()
                         if not line.lstrip().startswith("#"))
        for word in words:
            assert word not in code, f"{module.__name__} still names {word!r}"


def test_the_okta_builder_brings_the_renderer_of_the_kind_it_issues():
    from cs_image_system.okta_opa_plugin import okta_opa_tf_group_builder as builder
    assert builder.SFTD_TOKEN == "sftd-token" and "sftd-token" in launch_enrollment.registered_kinds()


def test_a_registered_kind_is_rendered_into_both_launch_forms(kinds):
    launch_enrollment.register_enrollment_kind(
        "test-kind",
        script_lines=lambda p: [f"echo enrolling {p['hostname']}"],
        ansible_tasks=lambda p: [{"name": "enroll", "ansible.builtin.command": "true"}])
    script = launch_params.user_data_template(_params("test-kind"))
    assert "echo enrolling box-001" in script
    lines = script.splitlines()
    assert lines.index("echo enrolling box-001") < next(i for i, ln in enumerate(lines) if "launch-applied" in ln), \
        "the enrollment runs before the completion marker"
    play = yaml.safe_load(ansible_launch.launch_playbook(_params("test-kind")))
    assert [t["name"] for t in play[0]["tasks"]][-1] == "enroll"


def test_a_kind_no_plugin_renders_is_refused_not_skipped(kinds):
    with pytest.raises(ValueError, match=r"box-001: launch enrollment 'nosuch' is rendered by no installed"):
        launch_params.user_data_template(_params("nosuch"))
    with pytest.raises(ValueError, match=r"'nosuch'"):
        ansible_launch.launch_playbook(_params("nosuch"))


def test_a_launch_without_an_enrollment_renders_none():
    assert "enrollment" not in launch_params.user_data_template(_params(None)).lower()


def test_a_group_builder_proves_no_login_unless_it_says_so():
    assert GroupBuilderBase.can_prove_login(object.__new__(GroupBuilderBase)) is False   # type: ignore[arg-type]
    with pytest.raises(NotImplementedError, match="cannot prove a login"):
        GroupBuilderBase.login_checks(object.__new__(GroupBuilderBase), "g", "h")         # type: ignore[arg-type]


# ------------------------------------------------- step 3: gids in generated IaC

def test_the_okta_builder_answers_the_gid_reference_the_consumers_used_to_assume():
    from tests.v2_support import FIXTURE_CONFIG, load_context, reset_singletons, stub_environment
    from pytest import MonkeyPatch
    mp = MonkeyPatch()
    stub_environment(mp)
    try:
        ctx = load_context(FIXTURE_CONFIG)
        gb = ctx.group_builders["oktagroups"]
        assert gb.gid_workspace() == "oktagroups"
        assert gb.gid_expression("coops") == 'data.terraform_remote_state.oktagroups.outputs.group_gids["coops"]'
    finally:
        reset_singletons()
        mp.undo()


def test_a_group_builder_without_an_identity_root_supplies_no_gid_by_default():
    gb = object.__new__(GroupBuilderBase)
    assert GroupBuilderBase.gid_workspace(gb) is None and GroupBuilderBase.gid_expression(gb, "g") is None  # type: ignore[arg-type]


def test_a_literal_gid_reaches_the_roots_and_no_identity_state_is_read(tmp_path, monkeypatch):
    """The seam posix uses: a builder whose gids are configuration answers
    with the number and no workspace -- the storage and instance roots then
    carry the number and declare no remote state of an identity root."""
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    from tests.v2_support import V2Run
    monkeypatch.setattr(OktaTfGroupBuilder, "gid_workspace", lambda self: None)
    monkeypatch.setattr(OktaTfGroupBuilder, "gid_expression", lambda self, group: "4242")
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["storage", "instance-image"], apply=False).ok
        texts = {p: p.read_text() for sub in ("storage", "instance-image")
                 for p in (run.generated / sub).rglob("*.tf")}
        joined = "\n".join(texts.values())
        assert "4242" in joined, "the literal gid reached no root"
        assert "outputs.group_gids" not in joined
        assert not [p for p, t in texts.items() if 'data "terraform_remote_state" "oktagroups"' in t]
    finally:
        run.restore_cwd()


# ------------------------------------------------ step 3: the ids, by the operator's rule

def _claims(*rows):
    from cs_image_system.base.posix_ids import Claim
    return [Claim(*row) if len(row) > 4 else Claim(*row) for row in rows]


def test_two_sides_that_supply_different_ids_for_one_name_are_a_configuration_error():
    from cs_image_system.base.posix_ids import Claim, resolve_posix_ids
    r = resolve_posix_ids([Claim("OPA", "group", "coops", 60123, rank=10),
                           Claim("the configuration", "group", "coops", 3000, rank=20)])
    assert r.ids == {} and r.problems == [
        "group coops: OPA supplies id 60123 and the configuration supplies 3000 "
        "-- one name, two ids is a configuration error"]


def test_a_side_with_only_the_name_takes_the_other_sides_id_in_serial_order():
    from cs_image_system.base.posix_ids import Claim, resolve_posix_ids
    r = resolve_posix_ids([Claim("the configuration", "group", "coops", None, rank=20),
                           Claim("OPA", "group", "coops", 60123, rank=10),
                           Claim("the machine", "group", "coops", None, rank=90)])
    assert r.ids == {("group", "coops"): 60123} and r.problems == []


def test_a_name_no_side_supplies_is_refused_unless_a_side_will_supply_it_later():
    from cs_image_system.base.posix_ids import DEFERRED, Claim, resolve_posix_ids
    r = resolve_posix_ids([Claim("the configuration", "group", "lonely", None)])
    assert r.problems == ["group lonely: no side supplies its id (the configuration); declare one (`gid:`)"]
    r = resolve_posix_ids([Claim("OPA", "group", "coops", DEFERRED, rank=10),
                           Claim("the configuration", "group", "coops", None, rank=20)])
    assert r.problems == [] and r.deferred == {("group", "coops")}


def test_two_names_on_one_id_are_refused_within_a_kind_but_a_users_private_group_may_share_its_uid():
    from cs_image_system.base.posix_ids import Claim, resolve_posix_ids
    r = resolve_posix_ids([Claim("cfg", "group", "a", 3001), Claim("cfg", "group", "b", 3001),
                           Claim("cfg", "user", "u", 3001)])
    assert r.problems == ["groups a, b all have id 3001 -- a machine could not tell them apart"]


# ------------------------------------------------ step 3: the plugin in a loaded tree

def _posix_tree(tmp_path, *, gid=3101, uids=(3201, 3202), extra_group=None):
    """A copy of the frozen fixture, whose posix shape (since step 3d: the
    builders, pxgroup and the two personas) is adjusted for one case."""
    from tests.v2_support import copy_config
    root = copy_config(tmp_path)
    gpath = root / "groups" / "group-pxgroup.yaml"
    groups = yaml.safe_load(gpath.read_text())
    groups["groups"][0]["gid"] = gid
    if extra_group:
        groups["groups"].append(extra_group)
    gpath.write_text(yaml.safe_dump(groups, sort_keys=False))
    upath = root / "groups" / "users.yaml"
    text = upath.read_text()
    for name, uid, default in (("taylor_tango", uids[0], 3201), ("unity_uniform", uids[1], 3202)):
        old = f"  - name: {name}\n    type: posix-users\n"
        assert old in text
        head, tail = text.split(old, 1)
        tail = tail.replace(f"    uid: {default}\n", f"    uid: {uid}\n" if uid is not None else "", 1)
        text = head + old + tail
    upath.write_text(text)                  # textual: the other users' markers stay byte-for-byte
    return root


def _posix_errors(root, monkeypatch) -> list[str]:
    from cs_image_system.base.commands.validate import check_posix_ids
    from tests.v2_support import load_context, reset_singletons, stub_environment
    stub_environment(monkeypatch)
    try:
        return [str(e) for e in check_posix_ids(load_context(root))]
    finally:
        reset_singletons()


def test_a_posix_tree_loads_and_its_ids_resolve_cleanly(tmp_path, monkeypatch):
    from tests.v2_support import load_context, reset_singletons, stub_environment
    root = _posix_tree(tmp_path)
    assert _posix_errors(root, monkeypatch) == []
    stub_environment(monkeypatch)
    try:
        ctx = load_context(root)
        gb = ctx.group_builders["posix-local"]
        assert gb.identity_type() == "posix" and gb.gid_policy() == "config-time"
        assert gb.gid_workspace() is None and gb.gid_expression("pxgroup") == "3101"
        group = next(g for g in gb.get_groups_for_builder() if g.get_name() == "pxgroup")
        image: Any = type("I", (), {"get_name": lambda self: "img"})()      # only its name is read
        bake = "\n".join(gb.activation_commands(image, group))
        assert "sudo bash -s <<'CSIS_POSIX_ACCOUNTS'" in bake and "groupadd -g 3101 pxgroup" in bake
        assert gb.activation_verify_commands(image, group)[-1] == "test \"$(getent group pxgroup | cut -d: -f3)\" = '3101'"
        users = {u.get_name(): u.uid for u in ctx.user_builders["posix-users"].get_users_for_builder()}
        assert users == {"taylor_tango": 3201, "unity_uniform": 3202}
    finally:
        reset_singletons()


@pytest.mark.parametrize("change,needle", [
    ({"gid": None}, "group pxgroup: no side supplies its id"),
    ({"uids": (1000, 3202)}, "user taylor_tango: the configuration declares id 1000, below 1024"),
    ({"uids": (3201, 3201)}, "users taylor_tango, unity_uniform all have id 3201"),
    ({"extra_group": {"name": "taylor_tango", "type": "posix-local", "gid": 3300}},
     "group taylor_tango: the configuration supplies id 3300 and the configuration (user-private group) supplies 3201"),
    ({"extra_group": {"name": "Bad.Name", "type": "posix-local", "gid": 3300}}, None),
])
def test_validate_refuses_each_id_problem_by_name(tmp_path, monkeypatch, change, needle):
    root = _posix_tree(tmp_path, **change)
    errors = _posix_errors(root, monkeypatch)
    if needle is None:                       # names are lower-cased on load: `Bad.Name` is `bad.name`, a fine name
        assert errors == []
    else:
        assert any(needle in e for e in errors), errors


def test_a_gid_below_the_floor_is_refused_when_the_group_loads(tmp_path, monkeypatch):
    """The Group model's own rule, older than this stage: the posix check
    uses the same floor for uids."""
    from tests.v2_support import load_context, reset_singletons, stub_environment
    root = _posix_tree(tmp_path, gid=999)
    stub_environment(monkeypatch)
    try:
        with pytest.raises(Exception, match="gid must be at least 1024"):
            load_context(root)
    finally:
        reset_singletons()


def test_a_posix_group_or_user_declaring_attributes_is_refused(tmp_path, monkeypatch):
    """Their ids are `gid:` and `uid:`: provider attributes would drag them
    into the OPA attribute plan, which asks a provider the posix plugin is not."""
    from cs_image_system.base.identity_attributes import validate_identity_items
    from tests.v2_support import load_context, reset_singletons, stub_environment
    root = _posix_tree(tmp_path)
    for rel, key, name in (("groups/group-pxgroup.yaml", "groups", "pxgroup"), ("groups/users.yaml", "users", "unity_uniform")):
        data = yaml.safe_load((root / rel).read_text())
        next(i for i in data[key] if i["name"] == name)["attributes"] = {"unix_gid" if key == "groups" else "unix_uid": 4000}
        (root / rel).write_text(yaml.safe_dump(data, sort_keys=False))
    stub_environment(monkeypatch)
    try:
        errors = validate_identity_items(load_context(root), [])
    finally:
        reset_singletons()
    assert any("group 'pxgroup': a posix group declares its id as `gid:`" in e for e in errors), errors
    assert any("user 'unity_uniform': a posix user declares its id as `uid:`" in e for e in errors), errors


# --------------------------------------------- step 4: accounts on machines

def test_the_posix_group_renders_its_whole_accounts_script(monkeypatch):
    from tests.v2_support import FIXTURE_CONFIG, load_context, reset_singletons, stub_environment
    stub_environment(monkeypatch)
    try:
        gb = load_context(FIXTURE_CONFIG).group_builders["posix-local"]
        script = gb.accounts_script("pxgroup")
        assert script is not None
        for needle in ("useradd -m -u 3201 -g 3201 -s /bin/bash taylor_tango",
                       "useradd -m -u 3202 -g 3202 -s /bin/bash unity_uniform",
                       "groupadd -g 3101 pxgroup", "# members of pxgroup: taylor_tango, unity_uniform",
                       "# authorized keys of taylor_tango: 1", "taylor_tango ALL=(ALL) NOPASSWD:ALL"):
            assert needle in script, needle
        assert "unity_uniform ALL=(ALL)" not in script, "a member who is not an admin gets no sudo"
        monkeypatch.setattr(gb.model, "admin_sudo", False)
        assert "NOPASSWD" not in (gb.accounts_script("pxgroup") or "")
        assert gb.accounts_script("no-such-group") is None
        assert gb.configuration_errors() == []
    finally:
        reset_singletons()


def test_a_posix_group_member_without_a_posix_account_is_refused(tmp_path, monkeypatch):
    from cs_image_system.base.commands.validate import check_group_builders
    from tests.v2_support import load_context, reset_singletons, stub_environment
    root = _posix_tree(tmp_path, extra_group={"name": "pxextra", "type": "posix-local", "gid": 3102,
                                              "members": ["blake.bravo"]})
    stub_environment(monkeypatch)
    try:
        errors = [str(e) for e in check_group_builders(load_context(root))]
    finally:
        reset_singletons()
    assert errors == ["posix group pxextra: blake.bravo has no posix account -- declare it as a user of a "
                      "`type: posix` user builder, with a `uid:`"]


class _Session:
    """The AWS runtime's power state and session command, faked."""

    def __init__(self, monkeypatch, *, state="running", rc=0, out="posix accounts: in place\n"):
        from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
        self.sent: list[tuple[str, str]] = []
        monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_power_state", lambda s: True)
        monkeypatch.setattr(AwsCloudBuilder, "query_instance_power_state", lambda s, n: state)
        monkeypatch.setattr(AwsCloudBuilder, "run_session_command",
                            lambda s, n, script, timeout=300: self.sent.append((n, script)) or (rc, out))


def _posix_instance_run(tmp_path, monkeypatch):
    """A fixture copy whose `test` instance is a machine of imgfile-posix
    (no storages: pxgroup is allowed on none), launched."""
    from tests.v2_support import V2Run, copy_config
    root = copy_config(tmp_path)
    path = root / "instances" / "instances.yaml"
    data = yaml.safe_load(path.read_text())
    inst = next(i for i in data["instances"] if i["name"] == "test")
    inst["image"] = "imgfile-posix"
    inst.pop("storages", None)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    ms = run.ctx.meta_state
    ms.record_launch_params("test", dict(ms.launch_params().get("test") or {"hostname": "test", "group": "pxgroup"})
                            | {"launched": True})
    run.ctx.config["apply_instances"] = True
    return run


def test_a_launched_running_machine_of_a_posix_group_gets_its_accounts(tmp_path, monkeypatch):
    from cs_image_system.base import accounts_reconcile
    from cs_image_system.base.lifecycles import Lifecycle
    session = _Session(monkeypatch)
    run = _posix_instance_run(tmp_path, monkeypatch)
    try:
        accounts_reconcile.reconcile_accounts(run.ctx, Lifecycle.INSTANCE_IMAGE)
        assert [n for n, _ in session.sent] == ["test"]
        sent = session.sent[0][1]
        assert sent.startswith("sudo bash -s <<'CSIS_ACCOUNTS'\n") and sent.rstrip().endswith("CSIS_ACCOUNTS")
        assert "useradd -m -u 3201" in sent and "groupadd -g 3101 pxgroup" in sent
    finally:
        run.restore_cwd()


@pytest.mark.parametrize("why", ["not launched", "applies off", "wrong lifecycle", "stopped"])
def test_no_accounts_are_sent_when_they_should_not_be(tmp_path, monkeypatch, why):
    from cs_image_system.base import accounts_reconcile
    from cs_image_system.base.lifecycles import Lifecycle
    session = _Session(monkeypatch, state="stopped" if why == "stopped" else "running")
    run = _posix_instance_run(tmp_path, monkeypatch)
    try:
        lifecycle = Lifecycle.BASE_IMAGE if why == "wrong lifecycle" else Lifecycle.INSTANCE_IMAGE
        if why == "not launched":
            ms = run.ctx.meta_state
            ms.record_launch_params("test", dict(ms.launch_params()["test"]) | {"launched": False})
        if why == "applies off":
            run.ctx.config["apply_instances"] = False
        accounts_reconcile.reconcile_accounts(run.ctx, lifecycle)
        assert session.sent == []
    finally:
        run.restore_cwd()


def test_a_refused_script_is_logged_as_an_error_and_never_stops_the_run(tmp_path, monkeypatch, caplog):
    import logging
    from cs_image_system.base import accounts_reconcile
    from cs_image_system.base.lifecycles import Lifecycle
    _Session(monkeypatch, rc=1, out="posix accounts: group pxgroup has gid 4000 here; the configuration says 3101\n")
    run = _posix_instance_run(tmp_path, monkeypatch)
    try:
        with caplog.at_level(logging.INFO):
            accounts_reconcile.reconcile_accounts(run.ctx, Lifecycle.INSTANCE_IMAGE)    # returns, raises nothing
        errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("group pxgroup has gid 4000 here; the configuration says 3101" in e for e in errors), errors
        assert any("the accounts script of group pxgroup FAILED (exit 1)" in e for e in errors), errors
    finally:
        run.restore_cwd()


# --------------------------------------------- step 5: beside Okta

def _okta_posix(root, value):
    """Set the fixture's oktagroups `posix:` line: a name, `none`, or None (absent)."""
    path = root / "cfg" / "group-builders.yml"
    text = path.read_text()
    old = "    posix: posix-local\n    # key:"
    assert old in text
    path.write_text(text.replace(old, ("" if value is None else f"    posix: {value}\n") + "    # key:"))


def _okta_findings(root, monkeypatch):
    from cs_image_system.base.commands.validate import check_group_builders
    from tests.v2_support import load_context, reset_singletons, stub_environment
    stub_environment(monkeypatch)
    try:
        ctx = load_context(root)
        gb: Any = ctx.group_builders["oktagroups"]      # the Okta builder: posix_delegate is its own
        return [str(e) for e in check_group_builders(ctx)], gb.configuration_notes(), gb
    finally:
        reset_singletons()


@pytest.mark.parametrize("value,needle", [
    (None, "group builder oktagroups: `posix:` is required -- write `posix: <name>`"),
    ("nosuch", "group builder oktagroups: `posix: nosuch` names no declared group builder"),
    ("okta-groups-ro", "`posix: okta-groups-ro` names a group builder of identity type 'okta'; it must be of type posix"),
])
def test_the_okta_posix_line_is_required_and_must_name_a_posix_builder(tmp_path, monkeypatch, value, needle):
    from tests.v2_support import copy_config
    root = copy_config(tmp_path)
    _okta_posix(root, value)
    errors, _, _ = _okta_findings(root, monkeypatch)
    assert any(needle in e for e in errors), errors


def test_posix_none_is_valid_and_says_what_it_keeps_off_the_machines(tmp_path, monkeypatch):
    from tests.v2_support import copy_config
    root = copy_config(tmp_path)
    _okta_posix(root, "none")
    errors, notes, gb = _okta_findings(root, monkeypatch)
    assert errors == [] and gb.posix_delegate() is None
    assert any(n.startswith("group coops: its builder oktagroups says `posix: none`, so the group does not exist")
               for n in notes), notes


def test_the_read_only_okta_builder_neither_requires_nor_reads_posix(monkeypatch):
    from tests.v2_support import FIXTURE_CONFIG, load_context, reset_singletons, stub_environment
    stub_environment(monkeypatch)
    try:
        ro: Any = load_context(FIXTURE_CONFIG).group_builders["okta-groups-ro"]
        assert ro.configuration_errors() == [] and ro.configuration_notes() == [] and ro.posix_delegate() is None
    finally:
        reset_singletons()


def _bake_lines(root, monkeypatch) -> tuple[str, list[str]]:
    """coops' activation and in-bake checks, rendered inside the loaded tree."""
    from tests.v2_support import load_context, reset_singletons, stub_environment
    stub_environment(monkeypatch)
    try:
        gb = load_context(root).group_builders["oktagroups"]
        image: Any = type("I", (), {"get_name": lambda self: "img"})()
        coops = next(g for g in gb.get_groups_for_builder() if g.get_name() == "coops")
        return "\n".join(gb.activation_commands(image, coops)), gb.activation_verify_commands(image, coops)
    finally:
        reset_singletons()


def test_an_okta_image_bakes_the_login_hook_only_with_a_delegate(tmp_path, monkeypatch):
    from tests.v2_support import copy_config
    bake, checks = _bake_lines(copy_config(tmp_path), monkeypatch)            # the fixture: posix: posix-local
    assert "/usr/local/sbin/csis-group-login" in bake and "pam_exec.so" in bake
    assert "test -x /usr/local/sbin/csis-group-login" in checks
    root = copy_config(tmp_path / "none")
    _okta_posix(root, "none")
    bake, checks = _bake_lines(root, monkeypatch)
    assert "csis-group-login" not in bake and "test -x /usr/local/sbin/csis-group-login" not in checks


class _Opa:
    """OPA's gid lookup, faked at the builder's resolver."""

    def __init__(self, monkeypatch, gids=None, error=None):
        from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
        self.asked: list[list[str]] = []
        gids = {"coops": 180007} if gids is None else gids

        def resolve(groups):
            self.asked.append(list(groups))
            if error:
                raise error
            return {g: gids[g] for g in groups if g in gids}
        monkeypatch.setattr(OktaTfGroupBuilder, "_resolver", lambda s: type("R", (), {"resolve": staticmethod(resolve)})())


def test_the_okta_accounts_script_makes_the_group_with_opas_gid_and_lists_its_people(monkeypatch):
    from tests.v2_support import FIXTURE_CONFIG, load_context, reset_singletons, stub_environment
    opa = _Opa(monkeypatch)
    stub_environment(monkeypatch)
    try:
        ctx = load_context(FIXTURE_CONFIG)
        gb = ctx.group_builders["oktagroups"]
        coops = next(g for g in gb.get_groups_for_builder() if g.get_name() == "coops")
        script = gb.accounts_script("coops") or ""
        assert opa.asked == [["coops"]]
        assert "groupadd -g 180007 coops" in script and "/etc/csis/groups/coops.members" in script
        assert "useradd" not in script and "# the keys of" not in script     # no keys file: not opted in
        people = {str(m) for m in coops.members} | {str(a) for a in coops.admins} | {str(a) for a in ctx.root_group.admins}
        assert all(p in script for p in people), "members, admins and the root group's admins, as OPA has them"
    finally:
        reset_singletons()


def test_an_okta_machine_gets_its_group_after_apply(tmp_path, monkeypatch):
    from cs_image_system.base import accounts_reconcile
    from cs_image_system.base.lifecycles import Lifecycle
    from tests.v2_support import V2Run
    _Opa(monkeypatch)
    session = _Session(monkeypatch)
    run = V2Run(tmp_path, monkeypatch)
    try:
        ms = run.ctx.meta_state
        ms.record_launch_params("test", dict(ms.launch_params().get("test") or {"hostname": "test"}) | {"launched": True})
        run.ctx.config["apply_instances"] = True
        accounts_reconcile.reconcile_accounts(run.ctx, Lifecycle.INSTANCE_IMAGE)
        assert [n for n, _ in session.sent] == ["test"] and "groupadd -g 180007 coops" in session.sent[0][1]
    finally:
        run.restore_cwd()


def test_posix_none_sends_an_okta_machine_nothing(tmp_path, monkeypatch):
    from cs_image_system.base import accounts_reconcile
    from cs_image_system.base.lifecycles import Lifecycle
    from tests.v2_support import V2Run, copy_config
    root = copy_config(tmp_path)
    _okta_posix(root, "none")
    session = _Session(monkeypatch)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        ms = run.ctx.meta_state
        ms.record_launch_params("test", dict(ms.launch_params().get("test") or {"hostname": "test"}) | {"launched": True})
        run.ctx.config["apply_instances"] = True
        accounts_reconcile.reconcile_accounts(run.ctx, Lifecycle.INSTANCE_IMAGE)
        assert session.sent == []
    finally:
        run.restore_cwd()


def test_an_opa_that_cannot_be_asked_is_an_error_not_a_crash(tmp_path, monkeypatch, caplog):
    import logging
    from cs_image_system.base import accounts_reconcile
    from cs_image_system.base.lifecycles import Lifecycle
    from tests.v2_support import V2Run
    _Opa(monkeypatch, error=RuntimeError("HTTP 401 from OPA"))
    session = _Session(monkeypatch)
    run = V2Run(tmp_path, monkeypatch)
    try:
        ms = run.ctx.meta_state
        ms.record_launch_params("test", dict(ms.launch_params().get("test") or {"hostname": "test"}) | {"launched": True})
        run.ctx.config["apply_instances"] = True
        with caplog.at_level(logging.INFO):
            accounts_reconcile.reconcile_accounts(run.ctx, Lifecycle.INSTANCE_IMAGE)
        assert session.sent == []
        assert any("the accounts script of group coops could not be made: HTTP 401 from OPA" in r.getMessage()
                   for r in caplog.records if r.levelno >= logging.ERROR)
    finally:
        run.restore_cwd()
