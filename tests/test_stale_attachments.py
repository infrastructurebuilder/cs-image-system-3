# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A membership the declaration dropped leaves tofu state before the plan.

The identity runner prunes the attachments the declaration dropped and OPA
no longer holds, after a state backup; one OPA still holds is left to the
plan; a silent OPA, missing credentials, nothing dropped, a failed backup
or a failed `state list` remove nothing. The runner carries the prune step
between init and plan and previews without refresh; the backup keeps the
pulled state under the private root; a runner step invoked from a root acts
there.

history: bundle V item 3.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs_image_system.contract.names import super_safe_name
from cs_image_system.okta_opa_plugin import okta_opa_tf_group_builder as gbmod
from tests.harness import V2Run


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch)
    try:
        yield r
    finally:
        r.restore_cwd()


def _group_builder(ctx) -> gbmod.OktaTfGroupBuilder:
    return next(b for b in ctx.group_builders.values() if isinstance(b, gbmod.OktaTfGroupBuilder))


class _Opa:
    def __init__(self, answers):
        self.answers = answers
        self.asked: list[str] = []

    def group_users(self, server_group):
        self.asked.append(server_group)
        return self.answers.get(server_group)


def _fake_tofu(tmp_path: Path, listed: list[str], pull: str = '{"serial": 7, "resources": [{"type": "x"}]}') -> tuple[str, Path]:
    """A tofu that answers `state list` and `state pull` from canned text and
    journals every `state rm` address, one per line."""
    journal = tmp_path / "state-rm.log"
    script = tmp_path / "tofu"
    script.write_text("#!/bin/sh\n"
                      "case \"$1 $2\" in\n"
                      "  'state list') cat <<'CSIS_EOF'\n" + "\n".join(listed) + "\nCSIS_EOF\n;;\n"
                      "  'state pull') printf '%s' '" + pull + "' ;;\n"
                      "  'state rm') printf '%s\\n' \"$3\" >> '" + str(journal) + "'; echo \"Removed $3\" ;;\n"
                      "esac\n")
    script.chmod(0o755)
    return str(script), journal


def _root(tmp_path: Path) -> Path:
    cwd = tmp_path / "root"
    (cwd / ".terraform").mkdir(parents=True)
    return cwd


def _addr(label: str, kind: str, user: str) -> str:
    return f'module.group_{label}.oktapam_user_group_attachment.{kind}["{user}"]'


def test_the_runner_prunes_the_attachments_the_declaration_dropped_and_opa_no_longer_holds(run, monkeypatch, caplog):
    ctx = run.ctx
    gb = _group_builder(ctx)
    g = gb.get_groups_for_builder()[0]
    name, label = g.get_name(), super_safe_name(g.name)
    declared_member = sorted(str(m) for m in g.members)[0]
    root_admin = sorted(str(a) for a in ctx.root_group.admins)[0]
    tofu, journal = _fake_tofu(run.config_root, [
        f"module.group_{label}.oktapam_group.user",
        _addr(label, "members", declared_member),          # still declared: kept
        _addr(label, "admins", root_admin),                # the root group's admin, merged in: kept
        _addr(label, "members", "gone.user"),              # dropped, OPA lacks it: removed
        _addr(label, "members", "kept.user"),              # dropped, OPA still holds it: the plan decides
        _addr(label, "admins", "gone.admin"),              # dropped, OPA lacks it: removed
        _addr("nosuchgroup", "members", "x"),              # not this builder's managed group: ignored
    ])
    opa = _Opa({f"{name}_user": ["kept.user", declared_member], f"{name}_admin": [root_admin]})
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", lambda self: opa)
    cwd = _root(run.config_root)
    with caplog.at_level("INFO"):
        assert gb.prune_stale_attachments(tofu, "r1", cwd) == 0
    assert journal.read_text().splitlines() == [_addr(label, "members", "gone.user"), _addr(label, "admins", "gone.admin")]
    assert sorted(opa.asked) == sorted([f"{name}_user", f"{name}_admin"]), "asked once per server group"
    kept = run.config_root / "_private" / "state-backups" / f"{gb.name}.backup-r1.tfstate"
    assert json.loads(kept.read_text())["serial"] == 7, "the backup precedes the first state rm"
    assert any("'kept.user'" in r.message for r in caplog.records), "the one left to the plan is named"
    assert any("'gone.user'" in r.message for r in caplog.records), "the one removed is named"


def test_a_silent_opa_missing_credentials_or_nothing_dropped_remove_nothing(run, monkeypatch, caplog):
    ctx = run.ctx
    gb = _group_builder(ctx)
    g = gb.get_groups_for_builder()[0]
    name, label = g.get_name(), super_safe_name(g.name)
    tofu, journal = _fake_tofu(run.config_root, [_addr(label, "members", "gone.user")])
    cwd = _root(run.config_root)
    # OPA did not answer for the group: the plan decides
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", lambda self: _Opa({}))
    with caplog.at_level("WARNING"):
        assert gb.prune_stale_attachments(tofu, "r1", cwd) == 0
    assert not journal.exists() and any(f"{name}_user" in r.message for r in caplog.records if r.levelno >= 30)
    # no credentials: nothing removed, said once
    caplog.clear()

    def no_creds(self):
        raise ValueError("OPA credentials for team 'x' not found in the environment")
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", no_creds)
    with caplog.at_level("WARNING"):
        assert gb.prune_stale_attachments(tofu, "r2", cwd) == 0
    assert not journal.exists() and len([r for r in caplog.records if r.levelno >= 30]) == 1
    # every attachment in state is declared: OPA is not even asked, no backup is taken
    asked = _Opa({f"{name}_user": []})
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", lambda self: asked)
    two = run.config_root / "two"
    two.mkdir()
    tofu2, journal2 = _fake_tofu(two, [_addr(label, "members", sorted(str(m) for m in g.members)[0])])
    assert gb.prune_stale_attachments(tofu2, "r3", cwd) == 0
    assert asked.asked == [] and not journal2.exists()
    assert not (run.config_root / "_private" / "state-backups").exists()


def test_a_failed_backup_or_state_list_stops_the_runner_before_any_removal(run, monkeypatch, caplog):
    gb = _group_builder(run.ctx)
    g = gb.get_groups_for_builder()[0]
    name, label = g.get_name(), super_safe_name(g.name)
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", lambda self: _Opa({f"{name}_user": []}))
    cwd = _root(run.config_root)
    tofu, journal = _fake_tofu(run.config_root, [_addr(label, "members", "gone.user")], pull="")
    with caplog.at_level("ERROR"):
        assert gb.prune_stale_attachments(tofu, "r1", cwd) == 1
    assert not journal.exists() and any("REFUSED" in r.message for r in caplog.records)
    bad = run.config_root / "tofu-bad"
    bad.write_text("#!/bin/sh\necho 'Backend initialization required' >&2\nexit 1\n")
    bad.chmod(0o755)
    with caplog.at_level("ERROR"):
        assert gb.prune_stale_attachments(str(bad), "r2", cwd) == 1
    assert any("state list" in r.message for r in caplog.records if r.levelno >= 40)


def _lines(execs) -> list[str]:
    return [" ".join([str(e.binary or e.name), *[str(a) for a in (e.args or [])]]) for e in execs]


def test_the_runner_carries_the_prune_step_between_init_and_plan_and_previews_without_refresh(run, monkeypatch):
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    gb = _group_builder(run.ctx)
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_dry_run", lambda self: False)
    execs = gb.get_commands_to_run_after(ExecutionLifecyclePhase.GROUP_GENERATION)
    now = _lines(execs.build_executables)
    preview = [ln for ln in now if " plan" in ln]
    assert preview and all(ln.endswith(" plan -refresh=false") for ln in preview), \
        "the generation-time plan is a preview: it never refreshes the attachment the runner prunes"
    deferred = _lines(execs.finalize_executables)
    init = next(i for i, ln in enumerate(deferred) if " init " in ln)
    prune = next(i for i, ln in enumerate(deferred) if f"prune-attachments --builder {gb.name} --tofu" in ln)
    plan = next(i for i, ln in enumerate(deferred) if " plan -input=false -out=tfplan" in ln)
    assert init < prune < plan, "after the init that binds the root to its state, before the plan the gate reads"
    assert f"--run {run.ctx.run_id}" in deferred[prune] and "--no-dry-run" in deferred[prune]
    assert not any("state-migration backup" in ln for ln in deferred), "the prune step takes its own backup"


def test_the_backup_keeps_the_pulled_state_under_the_private_root_and_refuses_everything_else(tmp_path: Path):
    from types import SimpleNamespace

    from cs_image_system.base.commands.state_migration import backup
    root = tmp_path / "config"
    mirror = root / "_private" / "identity" / "oktagroups" / "group-generation"
    mirror.mkdir(parents=True)
    ctx = SimpleNamespace(working_path=root)
    good = tmp_path / "tofu-good"
    good.write_text('#!/bin/sh\n[ "$1 $2" = "state pull" ] && printf \'{"serial": 7, "resources": [{"type": "x"}]}\'\n')
    good.chmod(0o755)
    # not an initialised root: refused before any pull
    assert backup(ctx, "oktagroups", str(good), "r0", mirror) == 1  # type: ignore[arg-type]
    (mirror / ".terraform").mkdir()
    assert backup(ctx, "oktagroups", str(good), "r1", mirror) == 0  # type: ignore[arg-type]
    kept = root / "_private" / "state-backups" / "oktagroups.backup-r1.tfstate"
    assert json.loads(kept.read_text())["serial"] == 7, "kept under _private/, outside every wiped directory"
    assert not list(mirror.glob("*.tfstate")), "nothing left in the mirror the run re-materialises"
    # the location holds no state, yet a state rm is due: refused
    empty = tmp_path / "tofu-empty"
    empty.write_text("#!/bin/sh\nprintf ''\n")
    empty.chmod(0o755)
    assert backup(ctx, "oktagroups", str(empty), "r2", mirror) == 1  # type: ignore[arg-type]
    assert not (root / "_private" / "state-backups" / "oktagroups.backup-r2.tfstate").exists()
    # the pull failed: refused
    bad = tmp_path / "tofu-bad"
    bad.write_text("#!/bin/sh\necho 'Failed to load state: no such bucket' >&2\nexit 1\n")
    bad.chmod(0o755)
    assert backup(ctx, "oktagroups", str(bad), "r3", mirror) == 1  # type: ignore[arg-type]
    # no configuration root known (the bare harness): beside the root
    assert backup(None, "oktagroups", str(good), "r4", mirror) == 0  # type: ignore[arg-type]
    assert (mirror / "oktagroups.backup-r4.tfstate").is_file()


def test_the_migration_commands_run_from_the_directory_the_runner_entered(tmp_path: Path, monkeypatch):
    """The CLI's callback loads the configuration, which changes directory to
    the root AND replaces the context object; a runner step invoked FROM a
    root (the mirror, or the generated root in-process) must still act
    there. Through the real command line: a direct call of the function
    passed while the live step pulled from the configuration root."""
    from typer.testing import CliRunner

    from cs_image_system.system import cli as climod
    from tests.harness import FIXTURE_CONFIG, stub_environment
    stub_environment(monkeypatch)
    monkeypatch.delenv("CSIS_CONFIG_ROOT", raising=False)
    seen: dict[str, Path] = {}
    monkeypatch.setattr(climod, "backup", lambda gctx, ws, tofu, run, cwd: seen.setdefault("cwd", Path(cwd)) and 0)   # patched where it is read
    started_in = tmp_path / "a-root-the-runner-entered"
    started_in.mkdir()
    monkeypatch.chdir(started_in)
    result = CliRunner().invoke(climod.app, ["--root-dir", str(FIXTURE_CONFIG), "state-migration", "backup",
                                            "--workspace", "ws", "--run", "r1", "--tofu", "/usr/bin/false"])
    assert result.exit_code == 0, result.output[-800:]
    assert seen["cwd"] == started_in, "the step acts where it was started, not in the configuration root"
