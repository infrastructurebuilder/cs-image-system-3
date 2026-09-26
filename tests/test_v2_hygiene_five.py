# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 61: hygiene bundle V.

61.1 a group the identity provider could not be ASKED about (a lapsed key
pair, no network) is reported unavailable, never as a missing group; a 404
is still a real absence and hard drift. 61.3 a membership the declaration
dropped and OPA no longer holds leaves tofu state before the plan, after a
state backup; one OPA still holds is left to the plan; a silent OPA and a
dry run remove nothing. 61.4 an unreleased pin is allowed while the series
head is under its own proof (pending replacement, launched, verified) and
refused the moment the proof fails or the pin is not the head; the
`cloud-upgrade` recipe runs the sequence with the rule left on. (61.2 closed
as overtaken: a sentence in OPERATIONS.) 61.5 the instance root's
`instances.auto.tfvars` is written by the instance-image lifecycle alone,
never under generated/release/ or generated/retention/.
"""
from __future__ import annotations

import json
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from cs_image_system.base import state_query as sq
from cs_image_system.base.read_models import identity_read_model
from cs_image_system.base.utils import super_safe_name
from cs_image_system.okta_opa_plugin import okta_opa_tf_group_builder as gbmod
from cs_image_system.okta_opa_plugin.opa_gids import GID_ATTRIBUTE
from tests.v2_support import REPO, V2Run

# captured at import, before the harness's stub replaces it on the class
_REAL_QUERY_STATE = gbmod.OktaTfGroupBuilder.query_state


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch)
    try:
        yield r
    finally:
        r.restore_cwd()


def _group_builder(ctx) -> gbmod.OktaTfGroupBuilder:
    return next(b for b in ctx.group_builders.values() if isinstance(b, gbmod.OktaTfGroupBuilder))


def _http(code: int, reason: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://opa.invalid", code, reason, Message(), None)


# ------------------------------------------------------- 61.1 unavailable, not missing

def test_a_group_the_provider_could_not_be_asked_about_is_unavailable_not_missing(run):
    ctx = run.ctx
    ctx.meta_state.write_identity_read_model(identity_read_model(ctx))
    names = sorted(ctx.meta_state.identity_read_model()["groups"])
    groups = {names[0]: {"present": False, "error": "HTTP 401 Unauthorized"},
              names[1]: {"present": False}}
    report = sq.StateReport(run=ctx.run_id)
    by_name = {d.name: d for d in sq.group_drift(ctx, groups, report)}
    assert names[0] not in by_name, "an errored record is not drift of any kind"
    assert f"groups/{names[0]}: HTTP 401 Unauthorized" in report.unavailable
    assert by_name[names[1]].drift == sq.DRIFT_MISSING and by_name[names[1]].hard, "a plain absence is still hard"
    # the query routes it the same way, and the strict query still refuses (unavailable is not `stale`)
    assert names[0] not in {d.name for d in sq.group_drift(ctx, groups)}


def test_the_builder_tells_a_404_from_a_call_that_failed(run, monkeypatch):
    gb = _group_builder(run.ctx)
    names = [g.get_name() for g in gb.get_groups_for_builder()]
    assert len(names) >= 3
    monkeypatch.setattr(gbmod, "credentials_from_env", lambda team: ("k", "s"))
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "can_manage_workload_access", lambda self: False)
    monkeypatch.setattr(gbmod.OpaGidResolver, "group_users", lambda self, g: None)
    monkeypatch.setattr(gbmod.OpaGidResolver, "project_enrollment_tokens", lambda self, g: None)

    def attributes(self, server_group):
        if server_group == f"{names[0]}{gbmod.USER_GROUP_SUFFIX}":
            raise _http(404, "Not Found")
        if server_group == f"{names[1]}{gbmod.USER_GROUP_SUFFIX}":
            raise _http(401, "Unauthorized")
        if server_group == f"{names[2]}{gbmod.USER_GROUP_SUFFIX}":
            raise OSError("Connection refused")
        return {GID_ATTRIBUTE: 180000, gbmod.GROUP_NAME_ATTRIBUTE: server_group}
    monkeypatch.setattr(gbmod.OpaGidResolver, "group_attributes", attributes)
    # the harness stubs query_state on the class (every group present, gid 1); this test is about the real one
    recs = _REAL_QUERY_STATE(gb)
    assert recs[names[0]] == {"present": False}, "OPA answered: the group is not there"
    assert recs[names[1]] == {"present": False, "error": "HTTP 401 Unauthorized"}
    assert recs[names[2]]["present"] is False and "Connection refused" in recs[names[2]]["error"]
    for other in names[3:]:
        assert recs[other]["present"] is True and "error" not in recs[other]


# ------------------------------------------- 61.3 stale attachments leave state first

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
    assert any("'kept.user'" in r.message and "OPA still holds it" in r.message for r in caplog.records)
    assert any("'gone.user'" in r.message and "leaves tofu state before the plan" in r.message for r in caplog.records)


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
    assert not journal.exists() and any("did not answer" in r.message and f"{name}_user" in r.message for r in caplog.records)
    # no credentials: nothing removed, said once
    caplog.clear()

    def no_creds(self):
        raise ValueError("OPA credentials for team 'x' not found in the environment")
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "_resolver", no_creds)
    with caplog.at_level("WARNING"):
        assert gb.prune_stale_attachments(tofu, "r2", cwd) == 0
    assert not journal.exists() and any("cannot be asked" in r.message for r in caplog.records)
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
    assert any("`state list` failed" in r.message for r in caplog.records)


def _lines(execs) -> list[str]:
    return [" ".join([str(e.binary or e.name), *[str(a) for a in (e.args or [])]]) for e in execs]


def test_the_runner_carries_the_prune_step_between_init_and_plan_and_previews_without_refresh(run, monkeypatch):
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
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
    passed while the live step pulled from the configuration root
    (2026-09-23 10:15)."""
    from typer.testing import CliRunner
    from cs_image_system.base.commands import state_migration as sm
    from cs_image_system.system import cli as climod
    from tests.v2_support import FIXTURE_CONFIG, reset_singletons, stub_environment
    reset_singletons()                      # the CLI loads the fixture into the singletons itself
    stub_environment(monkeypatch)
    monkeypatch.delenv("CSIS_CONFIG_ROOT", raising=False)
    seen: dict[str, Path] = {}
    monkeypatch.setattr(sm, "backup", lambda gctx, ws, tofu, run, cwd: seen.setdefault("cwd", Path(cwd)) and 0)
    started_in = tmp_path / "a-root-the-runner-entered"
    started_in.mkdir()
    monkeypatch.chdir(started_in)
    result = CliRunner().invoke(climod.app, ["--root-dir", str(FIXTURE_CONFIG), "state-migration", "backup",
                                            "--workspace", "ws", "--run", "r1", "--tofu", "/usr/bin/false"])
    assert result.exit_code == 0, result.output[-800:]
    assert seen["cwd"] == started_in, "the step acts where it was started, not in the configuration root"
    reset_singletons()                      # leave the singletons as the next test's harness expects


# --------------------------------------------- 61.4 the release grace and the recipe

def _build(ms, build_id: str, series: str, runtime: str, in_bake: bool = True) -> None:
    ms.add_build({"build_id": build_id, "series": series, "runtime": runtime, "run": "r0", "parent": "p",
                  "input_fingerprint": "f", "name": build_id, "mods": [], "chain": [],
                  "capabilities": {"identity_types": [], "storage_types": []},
                  "tests": {"in_bake": in_bake, "assertions": 1} if in_bake else {}})


def test_the_series_head_under_its_own_proof_is_allowed_and_refused_when_the_proof_fails(run, caplog):
    from cs_image_system.base.release import release, release_grace, validate_released_pins
    ctx = run.ctx
    ms = ctx.meta_state
    inst = next(i for i in ctx.instances if i.get_name() == "test2")
    image, runtime = str(inst.image), str(inst.runtime)
    ctx.config["require_released_builds"] = True
    _build(ms, "ami-old", image, runtime)
    ms.record_image_test("ami-old", {"ok": True, "run": "r0", "instance": "gce-test", "runtime": runtime, "checks": []})
    release(ctx, image, "ami-old")
    ms.bind_instance("test2", "ami-old", ctx.run_id)
    assert validate_released_pins(ctx, []) == [], "a released pin needs no grace"

    # the second build: the pin moves (pending replacement) -- the run that replaces is allowed
    _build(ms, "ami-new", image, runtime)
    ms.move_pin("instance", "test2", "ami-new", ctx.run_id)
    allowed, missing = release_grace(ctx, inst, "ami-new")
    assert allowed and "pending replacement onto series head ami-new" in allowed and missing == ""
    with caplog.at_level("WARNING"):
        assert validate_released_pins(ctx, []) == []
    assert any("allowed under the release grace" in r.message for r in caplog.records)

    # replaced: the machine stands on the build, no proof yet -- the run that verifies is allowed
    ms.clear_pending_replacement("test2")
    ms.open_generation("test2", kind="durable", run_id=ctx.run_id, how="observed",
                       launch_params={"build": "ami-new", "hostname": "test2-002"})
    assert "launched; verify it" in (release_grace(ctx, inst, "ami-new")[0] or "")

    # the proof FAILED: refused, naming it
    ms.record_image_test("ami-new", {"ok": False, "run": "rX", "instance": "test2", "runtime": runtime, "checks": []})
    errors = validate_released_pins(ctx, [])
    assert len(errors) == 1 and "no grace: the build FAILED its post-bake tests in run rX" in errors[0]

    # the proof passed: the run that releases is allowed
    ms.record_image_test("ami-new", {"ok": True, "run": "rY", "instance": "test2", "runtime": runtime, "checks": []})
    assert "verified; release it" in (release_grace(ctx, inst, "ami-new")[0] or "")
    assert validate_released_pins(ctx, []) == []

    # released: the grace is no longer consulted
    release(ctx, image, "ami-new")
    assert validate_released_pins(ctx, []) == []


def test_the_grace_is_only_for_the_series_head_that_was_verified_in_bake(run):
    from cs_image_system.base.release import release_grace, validate_released_pins
    ctx = run.ctx
    ms = ctx.meta_state
    inst = next(i for i in ctx.instances if i.get_name() == "test2")
    image, runtime = str(inst.image), str(inst.runtime)
    ctx.config["require_released_builds"] = True
    _build(ms, "ami-a", image, runtime)
    _build(ms, "ami-b", image, runtime, in_bake=False)
    # pinned to a build that is no longer the head: refused
    ms.move_pin("instance", "test2", "ami-a", ctx.run_id)
    allowed, missing = release_grace(ctx, inst, "ami-a")
    assert allowed is None and "not the head of series" in missing
    # the head, but never verified in bake: refused
    ms.move_pin("instance", "test2", "ami-b", ctx.run_id)
    allowed, missing = release_grace(ctx, inst, "ami-b")
    assert allowed is None and "no in-bake verification record" in missing
    # the head, verified, but the instance neither stands on it nor is being replaced onto it
    _build(ms, "ami-c", image, runtime)
    ms.bind_instance("test2", "ami-c", ctx.run_id)
    allowed, missing = release_grace(ctx, inst, "ami-c")
    assert allowed is None and "neither stands on the build nor is a pending replacement" in missing
    errors = validate_released_pins(ctx, [])
    assert len(errors) == 1 and "ami-c" in errors[0] and "no grace:" in errors[0]
    # a pin lineage does not know at all
    assert release_grace(ctx, inst, "ami-nowhere") == (None, "lineage does not record the build")


def test_the_upgrade_recipe_is_the_second_release_procedure_with_the_rule_left_on():
    # stage 64: the cycle recipes live in a configuration repository's Justfile, which the release ships
    text = (REPO / "docs" / "examples" / "complete" / "Justfile").read_text()
    assert "cloud-upgrade" not in (REPO / "Justfile").read_text()
    body = text[text.index("cloud-upgrade runtime instance"):]
    body = body[:body.index("\n\n")]
    lines = [ln.strip() for ln in body.splitlines()]
    assert lines[0].endswith(": cloud-preflight"), "never starts on a false belief or a lapsing session"
    assert any(ln.startswith("{{cli}} upgrade instance {{instance}}") for ln in lines)
    order = [next(i for i, ln in enumerate(lines) if key in ln) for key in
             ("upgrade instance", "just cloud-launch {{runtime}}", "just cloud-verify {{runtime}} {{instance}}",
              "run release --only-runtime {{runtime}}")]
    assert order == sorted(order), "pin, replace, proof, release -- in that order"
    assert lines.count("just cloud-launch {{runtime}}") == 2, "one more launch gives the machine its names"
    assert "require_released_builds" not in body.replace("# ", ""), "the rule is never switched off"


# ------------------------------------ 61.5 the tfvars belong to instance-image alone

def test_release_and_retention_never_write_an_instance_roots_tfvars(tmp_path: Path, monkeypatch):
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.base.lifecycles import Lifecycle
    from cs_image_system.base.release import RELEASE_LIFECYCLE
    from cs_image_system.base.retention import RETENTION_LIFECYCLE
    from tests.test_v2_gate6_lineage_pins import _fake_manifest
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["instance-image"], apply=False).ok
        ctx = run.ctx
        _fake_manifest(run, "instance-image", "block-000", {"imgfile-basic-dask": "ami-0dask0007"})
        ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
        ctx.image_builders["pckr-ebs-ans"].post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
        ib = ctx.instance_builders["open-tofu"]
        for lc in (RELEASE_LIFECYCLE, RETENTION_LIFECYCLE):
            ctx.current_lifecycle = lc
            ib.pre_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
            assert list((run.generated / lc.name).rglob("*.tfvars")) == [], f"{lc.name} wrote an instance root's tfvars"
        ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
        ib.pre_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
        tfvars = run.generated / "instance-image" / "open-tofu" / "instance-generation" / "instances.auto.tfvars"
        assert 'test2_ami_id = "ami-0dask0007"' in tfvars.read_text(), "the instance-image lifecycle still gets it"
    finally:
        ctx.current_lifecycle = None
        run.restore_cwd()
