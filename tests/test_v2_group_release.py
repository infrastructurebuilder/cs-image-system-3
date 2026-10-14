# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 90: a group's release is decided by the state.

A group marked ``unmanaged: true`` leaves terraform state and nothing is
destroyed. The removal used to be decided at generation, from the identity
read-model's ``managed``; every dry run (and every ``record``) rewrites that
file, so a dry run of a release recorded it as done, the real run emitted no
removal, and its plan was the destroy of the group, its project, its token and
its policies (the walk's F63, live 2026-10-13: the gate refused all eight).

Now the runner's pre-plan step lists the state itself and removes, after a
backup, whatever it still holds of an unmanaged group. No record is read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cs_image_system.base.utils import super_safe_name
from cs_image_system.okta_opa_plugin import okta_opa_tf_group_builder as gbmod
from tests.test_v2_hygiene_five import _addr, _fake_tofu, _group_builder, _Opa, _root
from tests.v2_support import V2Run, command_lines, copy_config

GROUP = "tcmet"
MODULE = f"module.group_{super_safe_name(GROUP)}"


def _released(tmp_path: Path, monkeypatch, record: dict | None = None, unmanaged: bool = True) -> V2Run:
    """The fixture with one group marked unmanaged BEFORE the context loads,
    and, when given, an identity read-model as an earlier run left it."""
    root = copy_config(tmp_path)
    p = root / "groups" / f"group-{GROUP}.yaml"
    data = yaml.safe_load(p.read_text())
    if unmanaged:
        data["groups"][0]["unmanaged"] = True
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    if record is not None:
        (root / "meta-state").mkdir(exist_ok=True)
        (root / "meta-state" / "identity.yaml").write_text(yaml.safe_dump({"groups": {GROUP: record}}))
    return V2Run(tmp_path, monkeypatch, config_root=root)


def _other_managed(gb) -> str:
    return next(super_safe_name(g.name) for g in gb.get_groups_for_builder() if not getattr(g, "unmanaged", False))


def _group_state(label: str) -> list[str]:
    return [f"module.group_{label}.oktapam_group.admin",
            f"module.group_{label}.oktapam_group.user",
            f"module.group_{label}.oktapam_resource_group.rg",
            f"module.group_{label}.oktapam_resource_group_project.rg_login",
            f"module.group_{label}.oktapam_resource_group_server_enrollment_token.login",
            f"module.group_{label}.oktapam_security_policy.admin",
            f"module.group_{label}.oktapam_security_policy.user"]


def test_what_the_state_holds_of_an_unmanaged_group_leaves_it_after_a_backup(tmp_path, monkeypatch, caplog):
    run = _released(tmp_path, monkeypatch)
    try:
        gb = _group_builder(run.ctx)
        other = _other_managed(gb)
        tofu, journal = _fake_tofu(run.config_root, [
            "data.external.group_gids",
            *_group_state(super_safe_name(GROUP)),
            _addr(super_safe_name(GROUP), "admins", "an.admin"),        # the group's own attachment: goes with it
            f"module.group_{other}.oktapam_group.user",                 # a MANAGED group: never touched
            f"{MODULE}x.oktapam_group.user",                            # a name that only begins the same: not it
        ])
        monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", lambda self: _Opa({}))
        cwd = _root(run.config_root)
        with caplog.at_level("INFO"):
            assert gb.prune_stale_attachments(tofu, "r1", cwd) == 0
        assert journal.read_text().splitlines() == [MODULE], "the module, once, and nothing else"
        kept = run.config_root / "_private" / "state-backups" / f"{gb.name}.backup-r1.tfstate"
        assert json.loads(kept.read_text())["serial"] == 7, "the backup precedes the removal"
        said = [r.message for r in caplog.records if "is unmanaged and the state still holds" in r.message]
        assert said and f"group {GROUP!r}" in said[0] and "8 of its resource(s)" in said[0]
        assert "nothing is destroyed" in said[0] and f"state rm {MODULE}" in said[0]
    finally:
        run.restore_cwd()


@pytest.mark.parametrize("record", [
    {"managed": False, "builder": "oktagroups"},      # what a dry run, or a `record`, leaves behind: F63
    {"managed": True, "builder": "oktagroups"},       # the record as it stood before anyone looked
    None,                                             # no record at all
])
def test_no_record_can_spend_a_release(tmp_path, monkeypatch, record):
    """The sequence that failed live: marked unmanaged, a dry run, then the
    real run. Whatever the read-model says, the state decides."""
    run = _released(tmp_path, monkeypatch, record=record)
    try:
        gb = _group_builder(run.ctx)
        assert run.run(["identity"], apply=False).ok          # the dry form; it rewrites the read-model
        model = yaml.safe_load((run.meta_state / "identity.yaml").read_text())
        assert model["groups"][GROUP]["managed"] is False, "a dry run records the group as unmanaged"
        cmds = command_lines((run.generated / "identity" / "run-identity.sh").read_text())
        assert not any("state rm" in c for c in cmds), "generation decides no removal"
        assert any(f"prune-attachments --builder {gb.name}" in c for c in cmds)
        tofu, journal = _fake_tofu(run.config_root, _group_state(super_safe_name(GROUP)))
        monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", lambda self: _Opa({}))
        assert gb.prune_stale_attachments(tofu, "r1", _root(run.config_root)) == 0
        assert journal.read_text().splitlines() == [MODULE]
    finally:
        run.restore_cwd()


def test_a_dry_run_says_which_groups_the_runner_will_look_for(tmp_path, monkeypatch, caplog):
    run = _released(tmp_path, monkeypatch)
    try:
        with caplog.at_level("INFO"):
            assert run.run(["identity"], apply=False).ok
        said = [r.message for r in caplog.records if "are unmanaged; the runner's pre-plan step" in r.message]
        assert said and GROUP in said[0] and "destroys nothing" in said[0]
    finally:
        run.restore_cwd()


def test_an_unmanaged_group_the_state_no_longer_holds_costs_nothing(tmp_path, monkeypatch):
    run = _released(tmp_path, monkeypatch)
    try:
        gb = _group_builder(run.ctx)
        tofu, journal = _fake_tofu(run.config_root, ["data.external.group_gids",
                                                     f"module.group_{_other_managed(gb)}.oktapam_group.user"])
        monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", lambda self: _Opa({}))
        assert gb.prune_stale_attachments(tofu, "r1", _root(run.config_root)) == 0
        assert not journal.exists(), "nothing is removed"
        assert not (run.config_root / "_private" / "state-backups").exists(), "and no backup is taken for nothing"
    finally:
        run.restore_cwd()


def test_a_managed_group_is_never_released(tmp_path, monkeypatch):
    run = _released(tmp_path, monkeypatch, unmanaged=False)
    try:
        gb = _group_builder(run.ctx)
        listed = [a for g in gb.get_groups_for_builder() for a in _group_state(super_safe_name(g.name))]
        tofu, journal = _fake_tofu(run.config_root, listed)
        monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", lambda self: _Opa({}))
        assert gb.prune_stale_attachments(tofu, "r1", _root(run.config_root)) == 0
        assert not journal.exists()
    finally:
        run.restore_cwd()


def _scripted_tofu(tmp_path: Path, listed: list[str], rm_exit: int = 0) -> tuple[str, Path]:
    """A tofu whose pulled state says whether anything was removed yet (serial
    7 before the first `state rm`, 8 after) and whose `state rm` can fail."""
    journal = tmp_path / "state-rm.log"
    script = tmp_path / "tofu-scripted"
    script.write_text("#!/bin/sh\n"
                      "case \"$1 $2\" in\n"
                      "  'state list') cat <<'CSIS_EOF'\n" + "\n".join(listed) + "\nCSIS_EOF\n;;\n"
                      "  'state pull') if [ -f '" + str(journal) + "' ]; "
                      "then printf '%s' '{\"serial\": 8, \"resources\": [{\"type\": \"x\"}]}'; "
                      "else printf '%s' '{\"serial\": 7, \"resources\": [{\"type\": \"x\"}]}'; fi ;;\n"
                      "  'state rm') printf '%s\\n' \"$3\" >> '" + str(journal) + "'; "
                      + ("echo \"Removed $3\"" if rm_exit == 0 else f"echo 'Error: state is locked' >&2; exit {rm_exit}") + " ;;\n"
                      "esac\n")
    script.chmod(0o755)
    return str(script), journal


def test_a_removal_that_fails_stops_the_runner_before_the_plan(tmp_path, monkeypatch, caplog):
    run = _released(tmp_path, monkeypatch)
    try:
        gb = _group_builder(run.ctx)
        tofu, _ = _scripted_tofu(run.config_root, _group_state(super_safe_name(GROUP)), rm_exit=1)
        monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", lambda self: _Opa({}))
        with caplog.at_level("ERROR"):
            assert gb.prune_stale_attachments(tofu, "r1", _root(run.config_root)) == 1
        assert any(f"`state rm {MODULE}` failed; the runner stops here" in r.message for r in caplog.records)
    finally:
        run.restore_cwd()


def test_one_backup_a_run_and_it_is_the_state_before_anything_left(tmp_path, monkeypatch):
    """A release and a pruned attachment in the same run: the backup is the
    state as it stood before the FIRST removal, not after the release."""
    run = _released(tmp_path, monkeypatch)
    try:
        gb = _group_builder(run.ctx)
        other = next(g for g in gb.get_groups_for_builder() if not getattr(g, "unmanaged", False))
        label = super_safe_name(other.name)
        tofu, journal = _scripted_tofu(run.config_root, [
            *_group_state(super_safe_name(GROUP)),
            f"module.group_{label}.oktapam_group.user",
            _addr(label, "members", "gone.member"),          # dropped, OPA lacks it: leaves state too
        ])
        monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", lambda self: _Opa({f"{other.get_name()}_user": []}))
        assert gb.prune_stale_attachments(tofu, "r1", _root(run.config_root)) == 0
        assert journal.read_text().splitlines() == [MODULE, _addr(label, "members", "gone.member")]
        kept = run.config_root / "_private" / "state-backups" / f"{gb.name}.backup-r1.tfstate"
        assert json.loads(kept.read_text())["serial"] == 7
    finally:
        run.restore_cwd()
