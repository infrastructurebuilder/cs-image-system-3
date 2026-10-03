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
