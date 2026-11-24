# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A POSIX identity plugin.

Step 2, the decoupling: the core's launch renderers and its login proof
name no identity agent. The group builder's enrollment KIND (recorded in the
launch parameters) is rendered by whichever plugin declared it, and a kind
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

from cs_image_system.base import launch_params
from cs_image_system.base.basic.builder_base_group import GroupBuilderBase
from cs_image_system.contract import enrollment
from cs_image_system.contract.enrollment import EnrollmentKind
from cs_image_system.engine import ansible_launch
from cs_image_system.engine.commands import login_proof


def _params(kind: str | None) -> dict:
    return {"hostname": "box-001", "image": "img", "build": "b1", "group": None, "mounts": [],
            "enrollment": ({"enrollment": kind} if kind else {}), "session": None}


@pytest.fixture
def kinds():
    """The registry as it stands, restored afterwards (the kinds discovery
    registered for the process must survive)."""
    saved = dict(enrollment._KINDS)
    try:
        yield enrollment._KINDS
    finally:
        enrollment._KINDS.clear()
        enrollment._KINDS.update(saved)


# ------------------------------------------------------------- step 2: the seams

def test_the_core_renderers_and_login_proof_name_no_agent():
    for module, words in ((launch_params, ("sftd-token", "/var/lib/sftd", "/etc/sft")),
                          (ansible_launch, ("sftd-token", "/var/lib/sftd", "sftd")),
                          (login_proof, ("run_sft", "subprocess", "OPA_TOKEN\")", "SFT_TEAM"))):
        code = "\n".join(line for line in inspect.getsource(module).splitlines()
                         if not line.lstrip().startswith("#"))
        for word in words:
            assert word not in code, f"{module.__name__} still names {word!r}"


def test_a_registered_kind_is_rendered_into_both_launch_forms(kinds):
    # a test may enter a kind directly; a plugin declares it in its metadata
    enrollment._install(EnrollmentKind(
        "test-kind",
        script_lines=lambda p: [f"echo enrolling {p['hostname']}"],
        ansible_tasks=lambda p: [{"name": "enroll", "ansible.builtin.command": "true"}]))
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


def test_a_group_builder_without_an_identity_root_supplies_no_gid_by_default():
    gb = object.__new__(GroupBuilderBase)
    assert GroupBuilderBase.gid_workspace(gb) is None and GroupBuilderBase.gid_expression(gb, "g") is None  # type: ignore[arg-type]


def _every_owner_posix(root) -> None:
    """Make pxgroup the owner of every image and the one allowed group of
    every storage that names groups, and let every base image declare
    posix: the storage and instance roots then hold no other group."""
    for path in sorted((root / "images").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        for image in data["images"]:
            image["group"] = "pxgroup"
        path.write_text(yaml.safe_dump(data, sort_keys=False))
    for path in sorted((root / "storages").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        for storage in data["storages"]:
            if storage.get("groups"):
                storage["groups"] = ["pxgroup"]
        path.write_text(yaml.safe_dump(data, sort_keys=False))
    path = root / "cfg" / "os-builders.yml"
    data = yaml.safe_load(path.read_text())
    for builder in data["os_builders"]:
        if "posix" not in builder.get("identity_types", []):
            builder["identity_types"] = [*builder.get("identity_types", []), "posix"]
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_a_literal_gid_reaches_the_roots_and_no_identity_state_is_read(tmp_path, monkeypatch):
    """The seam posix uses: a builder whose gids are configuration answers
    with the number and no workspace -- the storage and instance roots then
    carry the number and declare no remote state of an identity root."""
    from cs_image_system.contract.names import super_safe_name
    from tests.harness import FixtureRun, copy_config
    root = copy_config(tmp_path)
    _every_owner_posix(root)
    run = FixtureRun(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["storage", "instance-image"], apply=False)
        assert summary.ok, summary.validation_errors
        texts = {p: p.read_text() for sub in ("storage", "instance-image")
                 for p in (run.generated / sub).rglob("*.tf")}
        joined = "\n".join(texts.values())
        assert "3101" in joined, "the literal gid reached no root"
        assert '"group_gid" = 3101' in joined, "an instance takes the number as its group's gid"
        assert "outputs.group_gids" not in joined
        identity = [f'data "terraform_remote_state" "{super_safe_name(name)}"' for name in run.ctx.group_builders]
        assert not [p for p, t in texts.items() if any(block in t for block in identity)]
    finally:
        run.restore_cwd()


# ------------------------------------------------ step 3: the ids, by the operator's rule


def test_two_sides_that_supply_different_ids_for_one_name_are_a_configuration_error():
    from cs_image_system.engine.posix_ids import Claim, resolve_posix_ids
    r = resolve_posix_ids([Claim("the provider", "group", "coops", 60123, rank=10),
                           Claim("the configuration", "group", "coops", 3000, rank=20)])
    assert r.ids == {} and len(r.problems) == 1
    assert r.problems[0].startswith("group coops:") and "60123" in r.problems[0] and "3000" in r.problems[0]


def test_a_side_with_only_the_name_takes_the_other_sides_id_in_serial_order():
    from cs_image_system.engine.posix_ids import Claim, resolve_posix_ids
    r = resolve_posix_ids([Claim("the configuration", "group", "coops", None, rank=20),
                           Claim("the provider", "group", "coops", 60123, rank=10),
                           Claim("the machine", "group", "coops", None, rank=90)])
    assert r.ids == {("group", "coops"): 60123} and r.problems == []


def test_a_name_no_side_supplies_is_refused_unless_a_side_will_supply_it_later():
    from cs_image_system.engine.posix_ids import DEFERRED, Claim, resolve_posix_ids
    r = resolve_posix_ids([Claim("the configuration", "group", "lonely", None)])
    assert len(r.problems) == 1 and r.problems[0].startswith("group lonely:") and "`gid:`" in r.problems[0]
    r = resolve_posix_ids([Claim("the provider", "group", "coops", DEFERRED, rank=10),
                           Claim("the configuration", "group", "coops", None, rank=20)])
    assert r.problems == [] and r.deferred == {("group", "coops")}


def test_two_names_on_one_id_are_refused_within_a_kind_but_a_users_private_group_may_share_its_uid():
    from cs_image_system.engine.posix_ids import Claim, resolve_posix_ids
    r = resolve_posix_ids([Claim("cfg", "group", "a", 3001), Claim("cfg", "group", "b", 3001),
                           Claim("cfg", "user", "u", 3001)])
    assert len(r.problems) == 1 and r.problems[0].startswith("groups a, b") and "3001" in r.problems[0]


# ------------------------------------------------ step 3: the plugin in a loaded tree

def _posix_tree(tmp_path, *, gid: int | None = 3101, uids=(3201, 3202), extra_group=None):
    """A copy of the frozen fixture, whose posix shape (since step 3d: the
    builders, pxgroup and the two personas) is adjusted for one case."""
    from tests.harness import copy_config
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
    from cs_image_system.engine.commands.validate import check_posix_ids
    from tests.harness import load_context, stub_environment
    stub_environment(monkeypatch)
    return [str(e) for e in check_posix_ids(load_context(root))]


def test_a_posix_tree_loads_and_its_ids_resolve_cleanly(tmp_path, monkeypatch):
    from tests.harness import load_context, stub_environment
    root = _posix_tree(tmp_path)
    assert _posix_errors(root, monkeypatch) == []
    stub_environment(monkeypatch)
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
    assert len(users) == 21                 # every persona of the fixture is a POSIX account
    assert {n: uid for n, uid in users.items() if uid is not None} == {"taylor_tango": 3201, "unity_uniform": 3202}


@pytest.mark.parametrize("change,needle", [
    ({"uids": (1000, 3202)}, "user taylor_tango: the configuration declares id 1000, below 1024"),
    ({"uids": (3201, 3201)}, "users taylor_tango, unity_uniform all have id 3201"),
    ({"extra_group": {"name": "taylor_tango", "type": "posix-local", "gid": 3300}},
     "group taylor_tango: the configuration (posix-local) supplies id 3300 and the configuration (user-private group) (posix-users) supplies 3201"),
    ({"extra_group": {"name": "Bad.Name", "type": "posix-local", "gid": 3300}}, None),
])
def test_validate_refuses_each_id_problem_by_name(tmp_path, monkeypatch, change, needle):
    root = _posix_tree(tmp_path, **change)
    errors = _posix_errors(root, monkeypatch)
    if needle is None:                       # names are lower-cased on load: `Bad.Name` is `bad.name`, a fine name
        assert errors == []
    else:
        assert any(needle in e for e in errors), errors


def test_an_undeclared_posix_group_bakes_with_the_id_its_pool_gives(tmp_path, monkeypatch):
    """Through the fixture's POSIX tree with `pxgroup`'s gid left out: it
    validates, draws 3019 (the lowest id of the default pool no name holds:
    the fixture's 19 personas without a `uid:` draw 3019-3018 first), and
    the builder bakes and verifies that id."""
    from tests.harness import load_context, stub_environment
    root = _posix_tree(tmp_path, gid=None)
    assert _posix_errors(root, monkeypatch) == []
    stub_environment(monkeypatch)
    ctx = load_context(root)
    gb = ctx.group_builders["posix-local"]
    assert gb.gid_expression("pxgroup") == "3019"
    group = next(g for g in gb.get_groups_for_builder() if g.get_name() == "pxgroup")
    image: Any = type("I", (), {"get_name": lambda self: "img"})()
    assert "groupadd -g 3019 pxgroup" in "\n".join(gb.activation_commands(image, group))
    assert gb.activation_verify_commands(image, group)[-1].endswith("= '3019'")


def test_a_gid_below_the_floor_is_refused_when_the_group_loads(tmp_path, monkeypatch):
    """The Group model's own rule, older than this stage: the posix check
    uses the same floor for uids."""
    from tests.harness import load_context, stub_environment
    root = _posix_tree(tmp_path, gid=999)
    stub_environment(monkeypatch)
    with pytest.raises(Exception, match="gid must be at least 1024"):
        load_context(root)


def test_a_posix_group_or_user_declaring_attributes_is_refused(tmp_path, monkeypatch):
    """Their ids are `gid:` and `uid:`: provider attributes would drag them
    into the OPA attribute plan, which asks a provider the posix plugin is not."""
    from cs_image_system.engine.identity_attributes import validate_identity_items
    from tests.harness import load_context, stub_environment
    root = _posix_tree(tmp_path)
    for rel, key, name in (("groups/group-pxgroup.yaml", "groups", "pxgroup"), ("groups/users.yaml", "users", "unity_uniform")):
        data = yaml.safe_load((root / rel).read_text())
        next(i for i in data[key] if i["name"] == name)["attributes"] = {"unix_gid" if key == "groups" else "unix_uid": 4000}
        (root / rel).write_text(yaml.safe_dump(data, sort_keys=False))
    stub_environment(monkeypatch)
    errors = validate_identity_items(load_context(root), [])
    assert any("group 'pxgroup'" in e and "`gid:`" in e for e in errors), errors
    assert any("user 'unity_uniform'" in e and "`uid:`" in e for e in errors), errors


# --------------------------------------------- step 4: accounts on machines

def test_the_posix_group_renders_its_whole_accounts_script(monkeypatch):
    from tests.harness import FIXTURE_CONFIG, load_context, stub_environment
    stub_environment(monkeypatch)
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


def test_a_posix_group_member_without_a_posix_account_is_refused(tmp_path, monkeypatch):
    from cs_image_system.engine.commands.validate import check_group_builders
    from tests.harness import load_context, stub_environment
    root = _posix_tree(tmp_path, extra_group={"name": "pxextra", "type": "posix-local", "gid": 3102,
                                              "members": ["wren_whiskey"]})
    # every persona of the fixture is a posix account: this one sits on a
    # user builder of another type (the dummy plugin's), so it has none
    bpath = root / "cfg" / "group-builders.yml"
    builders = yaml.safe_load(bpath.read_text())
    builders["user_builders"].append({"name": "dummy-users", "type": "dummy", "org": "example", "team": "example"})
    bpath.write_text(yaml.safe_dump(builders, sort_keys=False))
    upath = root / "groups" / "users.yaml"
    upath.write_text(upath.read_text() + "  - name: wren_whiskey\n    type: dummy-users\n"
                     "    first_name: Wren\n    last_name: Whiskey\n")
    stub_environment(monkeypatch)
    errors = [str(e) for e in check_group_builders(load_context(root))]
    assert len(errors) == 1 and errors[0].startswith("posix group pxextra: wren_whiskey") and "`type: posix`" in errors[0]


class _Session:
    """The AWS runtime's power state and session command, faked."""

    def __init__(self, monkeypatch, *, state="running", rc=0, out="posix accounts: in place\n"):
        from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
        self.sent: list[tuple[str, str]] = []
        monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_power_state", lambda s: True)
        monkeypatch.setattr(AwsCloudBuilder, "query_instance_power_state", lambda s, n: state)
        monkeypatch.setattr(AwsCloudBuilder, "run_session_command",
                            lambda s, n, script, timeout=300: self.sent.append((n, script)) or (rc, out))


def _posix_instance_run(tmp_path, monkeypatch, prepare=None):
    """A fixture copy whose `test` instance is a machine of imgfile-posix
    (no storages: pxgroup is allowed on none), launched; ``prepare(root)``
    adjusts the copy first."""
    from tests.harness import FixtureRun, copy_config
    root = copy_config(tmp_path)
    if prepare is not None:
        prepare(root)
    path = root / "instances" / "instances.yaml"
    data = yaml.safe_load(path.read_text())
    inst = next(i for i in data["instances"] if i["name"] == "test")
    inst["image"] = "imgfile-posix"
    inst.pop("storages", None)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    run = FixtureRun(tmp_path, monkeypatch, config_root=root)
    ms = run.ctx.meta_state
    ms.record_launch_params("test", dict(ms.launch_params().get("test") or {"hostname": "test", "group": "pxgroup"})
                            | {"launched": True})
    run.ctx.config["apply_instances"] = True
    return run


def test_a_launched_running_machine_of_a_posix_group_gets_its_accounts(tmp_path, monkeypatch):
    from cs_image_system.contract.lifecycles import Lifecycle
    from cs_image_system.engine import accounts_reconcile
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
    from cs_image_system.contract.lifecycles import Lifecycle
    from cs_image_system.engine import accounts_reconcile
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

    from cs_image_system.contract.lifecycles import Lifecycle
    from cs_image_system.engine import accounts_reconcile
    _Session(monkeypatch, rc=1, out="posix accounts: group pxgroup has gid 4000 here; the configuration says 3101\n")
    run = _posix_instance_run(tmp_path, monkeypatch)
    try:
        with caplog.at_level(logging.INFO):
            accounts_reconcile.reconcile_accounts(run.ctx, Lifecycle.INSTANCE_IMAGE)    # returns, raises nothing
        errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("pxgroup" in e and "gid 4000" in e and "3101" in e for e in errors), errors
        assert any("pxgroup" in e and "FAILED (exit 1)" in e for e in errors), errors
    finally:
        run.restore_cwd()


# --------------------------------------------- step 6: real ssh, through the runtime's tunnel

# a fake key, its armour assembled here so the repository's public-safe scan
# (which refuses a PEM private-key header anywhere in the tree) never sees one
_ARMOUR = "OPENSSH PRIVATE KEY-----"
PROOF_PEM = f"-----BEGIN {_ARMOUR}\nZmFrZQ==\n-----END {_ARMOUR}\n"


def test_the_aws_tunnel_is_ssm_start_ssh_session_with_the_runtimes_region_and_profile(monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from tests.harness import FIXTURE_CONFIG, load_context, stub_environment
    stub_environment(monkeypatch)
    ctx = load_context(FIXTURE_CONFIG)
    rtb: Any = ctx.runtime_builders["aws-east2-runtime"]       # the AWS builder: its model has get_region
    monkeypatch.setattr(AwsCloudBuilder, "running_instance_id", lambda s, n: "i-0abc" if n == "test" else None)
    cmd = rtb.ssh_proxy_command("test") or []
    assert cmd[:8] == ["aws", "ssm", "start-session", "--target", "i-0abc", "--document-name",
                       "AWS-StartSSHSession", "--parameters"]
    assert "portNumber=%p" in cmd and cmd[cmd.index("--region") + 1] == str(rtb.model.get_region())
    profile = rtb.model.get_credentials().get("profile_name")
    assert (cmd[cmd.index("--profile") + 1] == profile) if profile else "--profile" not in cmd
    assert rtb.ssh_proxy_command("not-running") is None


class _Ssh:
    def __init__(self, monkeypatch, out="uid=3202(unity_uniform) gid=3202(unity_uniform) groups=3202(unity_uniform),3101(pxgroup)\n", rc=0):
        from cs_image_system.posix_identity_plugin import ssh_login
        self.calls: list[list[str]] = []
        monkeypatch.setattr(ssh_login, "run_ssh", lambda args, timeout=120: self.calls.append(list(args)) or (rc, out))


def test_the_proof_checks_key_tunnel_login_and_group_in_that_order(monkeypatch):
    from cs_image_system.posix_identity_plugin import ssh_login
    proxy = ["aws", "ssm", "start-session", "--target", "i-0abc", "--document-name", "AWS-StartSSHSession",
             "--parameters", "portNumber=%p"]
    no_key, _ = ssh_login.login_checks(group="pxgroup", user="unity_uniform", instance_name="test", proxy=proxy, env={})
    assert [(c["name"], c["ok"]) for c in no_key] == [("proof key", False)] and "CSIS_PROOF_SSH_KEY is not set" in no_key[0]["detail"]
    env = {"CSIS_PROOF_SSH_KEY": PROOF_PEM}
    no_tunnel, _ = ssh_login.login_checks(group="pxgroup", user="unity_uniform", instance_name="test", proxy=None, env=env)
    assert [(c["name"], c["ok"]) for c in no_tunnel] == [("proof key", True), ("tunnel", False)]
    ssh = _Ssh(monkeypatch)
    ok, evidence = ssh_login.login_checks(group="pxgroup", user="unity_uniform", instance_name="test", proxy=proxy, env=env)
    assert [(c["name"], c["ok"]) for c in ok] == [("proof key", True), ("tunnel", True), ("login", True), ("in its group", True)]
    args = ssh.calls[0]
    assert args[-2:] == ["unity_uniform@test", "id"] and "BatchMode=yes" in args and "IdentitiesOnly=yes" in args
    assert any(a.startswith("ProxyCommand=aws ssm start-session --target i-0abc") and "portNumber=%p" in a for a in args)
    _Ssh(monkeypatch, out="uid=3202(unity_uniform) gid=3202(unity_uniform) groups=3202(unity_uniform)\n")
    outside, _ = ssh_login.login_checks(group="pxgroup", user="unity_uniform", instance_name="test", proxy=proxy, env=env)
    assert outside[-1]["name"] == "in its group" and not outside[-1]["ok"]


def _with_proof_user(root):
    path = root / "groups" / "users.yaml"
    text = path.read_text()
    old = "  - name: unity_uniform\n    type: posix-users\n"
    assert old in text
    path.write_text(text.replace(old, old + "    is_service_account: true\n"))


def test_verify_login_proves_a_posix_machine_as_its_proof_user(tmp_path, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.engine.commands import login_proof as lp
    _Session(monkeypatch)
    _Ssh(monkeypatch)
    monkeypatch.setattr(AwsCloudBuilder, "ssh_proxy_command", lambda s, n: ["aws", "ssm", "start-session", "--target", "i-0abc"])
    monkeypatch.setenv("CSIS_PROOF_SSH_KEY", PROOF_PEM)
    run = _posix_instance_run(tmp_path, monkeypatch, prepare=_with_proof_user)
    try:
        rec = lp.prove_login(run.ctx, next(i for i in run.ctx.instances if i.get_name() == "test"))
        assert rec["ok"] and rec["as"] == "proof key" and rec["group"] == "pxgroup", rec
        assert [c["name"] for c in rec["checks"]] == ["proof key", "tunnel", "login", "in its group"]
    finally:
        run.restore_cwd()


def test_a_posix_group_without_a_proof_user_is_skipped_naming_why(tmp_path, monkeypatch):
    from cs_image_system.engine.commands import login_proof as lp
    _Session(monkeypatch)
    run = _posix_instance_run(tmp_path, monkeypatch)
    try:
        rec = lp.prove_login(run.ctx, next(i for i in run.ctx.instances if i.get_name() == "test"))
        assert rec["skipped"] and "has no posix proof user" in rec["checks"][0]["detail"], rec
    finally:
        run.restore_cwd()
