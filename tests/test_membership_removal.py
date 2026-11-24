# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A membership the YAML dropped is removed by the run.

Found walking the daily driver. A person added to a
group through the YAML could not be taken out of it the same way: the plan
showed the destroy of their attachment, the gate whitelisted no membership
destroy, and the run failed until someone removed them in the OPA console.
The operator: "The system can add users to an oktapam group. It should be
able to remove them from that group, as well."

The identity runner's prune step already lists the state it is bound to and
knows which attachments the declaration dropped. It now names the ones the
plan will destroy in a file beside the plan, and the gate reads that file:
each entry sanctions the one address it spells. Nothing else about the gate
moves -- a group, a policy, a token or a person the YAML still names is as
undestroyable as before.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cs_image_system.engine.commands.gate import gate_plan, sanctioned_addresses
from tests.harness import FixtureRun


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = FixtureRun(tmp_path, monkeypatch)
    try:
        yield r
    finally:
        r.restore_cwd()


def _plan(*destroyed: str, created: tuple[str, ...] = ()) -> dict:
    return {"resource_changes": [{"address": a, "change": {"actions": ["delete"]}} for a in destroyed]
            + [{"address": a, "change": {"actions": ["create"]}} for a in created]}


# ------------------------------------------------------- the prune step sanctions


# ----------------------------------------------------------------- the gate
# The gate, the list reader and `gate-plan --allow-destroy-from` are the
# core's (engine/commands/gate.py), whichever plugin's runner step writes
# the list: the cases below name no plugin. The addresses are data, in the
# shape an identity root's attachment takes.

#: the list's name, as the core's emission ignores it (contract DEFAULT_GITIGNORE_ENTRIES)
REMOVALS = "csis-sanctioned-removals.txt"


def _attachment(label: str, kind: str, user: str) -> str:
    return f'module.group_{label}.oktapam_user_group_attachment.{kind}["{user}"]'


def test_the_gate_lets_a_sanctioned_removal_through_and_only_that():
    held = _attachment("coops", "members", "held.member")
    other = _attachment("coops", "members", "someone.else")
    assert gate_plan(_plan(held), [], allow_exact=[held]) == []
    assert gate_plan(_plan(held, other), [], allow_exact=[held]) == [other], "a person nobody dropped stays undestroyable"
    assert gate_plan(_plan(held), []) == [held], "and without the list the gate is what it was"


@pytest.mark.parametrize("address", [
    "module.group_coops.oktapam_group.user",
    "module.group_coops.oktapam_group.admin",
    "module.group_coops.oktapam_security_policy.user",
    "module.group_coops.oktapam_resource_group_server_enrollment_token.login",
    "module.group_coops",
])
def test_no_list_can_widen_into_a_group_a_policy_or_a_token(address):
    """A file's entry matches the address it spells, never a prefix: sanctioning
    one attachment, or even writing a module's own address into the file,
    covers nothing inside or around it."""
    held = _attachment("coops", "members", "held.member")
    assert gate_plan(_plan(held, address), [], allow_exact=[held]) == [address]
    inside = "module.group_coops.oktapam_group.user"
    assert gate_plan(_plan(inside), [], allow_exact=["module.group_coops"]) == [inside]
    assert gate_plan(_plan(inside), ["module.group_coops"]) == [], "a prefix is --allow-destroy's, by an operation"


def test_a_file_that_is_not_there_sanctions_nothing(tmp_path):
    assert sanctioned_addresses(tmp_path / "absent.txt") == []
    listed = tmp_path / "listed.txt"
    listed.write_text("\n# a comment\n" + _attachment("coops", "admins", "a.b") + "\n\n")
    assert sanctioned_addresses(listed) == [_attachment("coops", "admins", "a.b")]


def test_the_command_reads_the_list_and_says_what_it_let_through(tmp_path):
    import json

    from cs_image_system.system.cli import app
    held = _attachment("coops", "members", "held.member")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(_plan(held, created=("module.group_coops.oktapam_user_group_attachment.members[\"new\"]",))))
    listed = tmp_path / REMOVALS
    runner = CliRunner()
    refused = runner.invoke(app, ["gate-plan", str(plan)])
    assert refused.exit_code == 3 and "DESTROY NOT WHITELISTED" in refused.output
    assert runner.invoke(app, ["gate-plan", str(plan), "--allow-destroy-from", str(listed)]).exit_code == 3, "no file yet"
    listed.write_text(held + "\n")
    passed = runner.invoke(app, ["gate-plan", str(plan), "--allow-destroy-from", str(listed)])
    assert passed.exit_code == 0, passed.output
    assert f"Destroy sanctioned by the declaration: {held}" in passed.output and "Plan passes the apply gate." in passed.output


# ------------------------------------------------------------- the emission
