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
