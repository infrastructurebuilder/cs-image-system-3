# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 46: several state backends, used and proven collision-proof.

A configured root keeps its state in exactly one location, and no two roots
may write the same state object. The fixture binds its storage roots to a
second backend (a different bucket and prefix), so the golden carries two
buckets and cross-backend remote-state reads; `validate` resolves every
root's location from the declarations alone and refuses collisions; every
run records the locations in meta-state; a rebinding of a root with live
resources is refused and names both locations and both routes; the escape
is the `--migrate-state` operation, which a dry run refuses, and whose
begin/finish steps are proven over a fake tofu.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from v2_support import V2Run, command_lines, copy_config

EAST1 = "s3://my-east1-tfstate-bucket/statefiles/csia"
EAST2 = "s3://noaa-ioos-cloud-sandbox-tfstate/statefiles/csia-image-system-test"


def _rebind_storage(root: Path, backend: str) -> None:
    p = root / "cfg" / "storage-builders.yml"
    p.write_text(p.read_text().replace("state_configuration: s3-east1", f"state_configuration: {backend}"))


def _errors(ctx) -> list[str]:
    from cs_image_system.base.commands.validate import check_state_locations
    return [str(e) for e in check_state_locations(ctx)]


def _records(run: V2Run) -> dict[str, dict]:
    return yaml.safe_load((run.meta_state / "state-locations.yaml").read_text())["workspaces"]


# ------------------------------------------------------------- resolution and records

def test_every_root_resolves_a_location_the_run_records_and_the_emission_carries(tmp_path, monkeypatch):
    v2 = V2Run(tmp_path, monkeypatch)
    assert _errors(v2.ctx) == []
    assert v2.run("all", apply=False).ok
    rec = _records(v2)
    assert set(rec) >= {"aws-ebs", "aws-efs", "aws-s3", "gcp-pd", "gcp-gcs", "open-tofu", "tofu-gce",
                        "oktagroups", "okta-tf-users"}
    assert rec["aws-ebs"] == {"backend": "s3-east1", "type": "s3", "bucket": "my-east1-tfstate-bucket",
                              "key": "statefiles/csia/aws_ebs.tfstate", "region": "us-east-1", "encrypt": True,
                              "use_lockfile": True, "profile": "noaa", "run": v2.ctx.run_id}
    assert rec["open-tofu"]["bucket"] == "noaa-ioos-cloud-sandbox-tfstate"      # own value: s3-east2
    assert rec["oktagroups"]["bucket"] == "noaa-ioos-cloud-sandbox-tfstate"     # the default
    # the cross-backend read: the instance root (backend A) reads storage state in backend B
    inst = v2.generated / "instance-image" / "open-tofu" / "instance-generation"
    root = (inst / "open-tofu-instance-generation.tf").read_text()
    assert 'bucket = "my-east1-tfstate-bucket"' in root and 'key = "statefiles/csia/aws_ebs.tfstate"' in root
    assert 'bucket = "noaa-ioos-cloud-sandbox-tfstate"' in (inst / "open-tofu-instance-generation.tfbackend.hcl").read_text()


def test_the_chain_reads_the_runtimes_backend_when_the_root_is_silent(tmp_path, monkeypatch):
    """A builder naming its own backend, a builder inheriting its runtime's,
    and a builder whose runtime is silent too, falling through to the default."""
    root = copy_config(tmp_path)
    _rebind_storage(root, "default")                              # the storage roots say nothing of their own
    p = root / "cfg" / "runtime-builders.yml"
    d = yaml.safe_load(p.read_text())
    assert not any("state_configuration" in rt for rt in d["runtime_builders"])
    next(rt for rt in d["runtime_builders"] if rt["name"] == "aws-east2-runtime")["state_configuration"] = "s3-east1"
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    v2 = V2Run(tmp_path, monkeypatch, config_root=root)
    assert _errors(v2.ctx) == []
    assert v2.run(["identity", "storage", "instance-image"], apply=False).ok
    rec = _records(v2)
    assert rec["aws-ebs"]["backend"] == "s3-east1"                # inherited from aws-east2-runtime
    assert rec["gcp-pd"]["backend"] == "s3-east2"                 # gcloud-east1 is silent: the default
    assert rec["open-tofu"]["backend"] == "s3-east2"              # names its own


# ------------------------------------------------------------- collisions

def test_two_roots_that_would_share_a_state_object_are_refused_before_anything_is_emitted(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    p = root / "cfg" / "instance-builders.yml"
    d = yaml.safe_load(p.read_text())
    twin = dict(next(b for b in d["instance_builders"] if b["name"] == "open-tofu"))
    twin["name"] = "open_tofu"                                    # super_safe_name collapses both to open_tofu
    twin.pop("is_default", None)
    d["instance_builders"].append(twin)
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    v2 = V2Run(tmp_path, monkeypatch, config_root=root)
    errors = _errors(v2.ctx)
    assert errors == [f"state location collision: workspaces open-tofu, open_tofu would share the state object {EAST2}/open_tofu.tfstate"]
    summary = v2.run(["instance-image"], apply=False)
    assert not summary.ok and any("would share the state object" in e for e in summary.validation_errors)


def test_an_undeclared_backend_name_is_refused(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    _rebind_storage(root, "s3-nowhere")
    v2 = V2Run(tmp_path, monkeypatch, config_root=root)
    assert any("names state backend 's3-nowhere', which is not declared" in e for e in _errors(v2.ctx))


# ------------------------------------------------------------- the move guard

def test_a_rebinding_with_nothing_deployed_passes_and_with_live_resources_is_refused(tmp_path, monkeypatch, caplog):
    v2 = V2Run(tmp_path, monkeypatch)
    assert v2.run("all", apply=False).ok                          # records every location
    _rebind_storage(v2.config_root, "default")                    # the storage roots move to the default backend
    again = V2Run(tmp_path, monkeypatch, config_root=v2.config_root)
    with caplog.at_level(logging.INFO):
        assert _errors(again.ctx) == []
    moved = [r.getMessage() for r in caplog.records if "moves its state" in r.getMessage()]
    assert moved and all("nothing is deployed" in m for m in moved)
    # now the records say a storage stands in aws-efs's state
    (v2.config_root / "meta-state" / "storage-state.yaml").write_text(yaml.safe_dump(
        {"storages": {"efs-storage": {"state": "active", "history": [], "facts": {"builder": "aws-efs"}}}}))
    third = V2Run(tmp_path, monkeypatch, config_root=v2.config_root)
    errors = _errors(third.ctx)
    assert len(errors) == 1, errors
    msg = errors[0]
    assert f"workspace 'aws-efs' would move its state from {EAST1}/aws_efs.tfstate to {EAST2}/aws_efs.tfstate" in msg
    assert "storage efs-storage (active)" in msg
    assert "--migrate-state aws-efs" in msg and "import and forget" in msg      # both routes, named
    summary = third.run(["storage"], apply=False)
    assert not summary.ok and any("would move its state" in e for e in summary.validation_errors)
    third.ctx.migrate_state = ["aws-efs"]                         # the operation, not an override
    assert _errors(third.ctx) == []


def test_migrate_state_on_a_dry_run_is_refused_before_anything_runs(tmp_path, monkeypatch):
    """The CLI refuses the pair up front (exit 2) and the run itself refuses it
    too, so no path -- a hook, a script, a future command -- moves state dry."""
    v2 = V2Run(tmp_path, monkeypatch)
    v2.ctx.migrate_state = ["aws-efs"]
    summary = v2.run(["storage"], apply=False)
    assert not summary.ok and "needs --no-dry-run" in (summary.error or "") and "never moves state" in (summary.error or "")
    assert not (v2.generated / "storage").exists()                # refused before anything was generated
    from cs_image_system.system import cli
    src = Path(cli.__file__).read_text()
    assert "needs --no-dry-run: a dry run never moves state" in src and "raise typer.Exit(code=2)" in src


def test_a_migration_run_emits_the_operation_for_that_root_alone(tmp_path, monkeypatch):
    v2 = V2Run(tmp_path, monkeypatch)
    assert v2.run("all", apply=False).ok
    _rebind_storage(v2.config_root, "default")
    # a real run's validators want every runtime session present: static keys and an ADC file
    adc = tmp_path / "adc.json"
    adc.write_text(json.dumps({"type": "authorized_user"}))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-test")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(adc))
    real = V2Run(tmp_path, monkeypatch, dry_run=False, config_root=v2.config_root)
    real.ctx.migrate_state = ["aws-efs"]
    summary = real.run(["storage"], apply=True)
    assert summary.ok, summary.error
    lines = command_lines((real.generated / "storage" / "run-storage.sh").read_text())
    efs = "\n".join(line for line in lines if '"aws-efs/storage-generation"' in line)
    for needle in ("state-migration begin --workspace aws-efs --tofu",
                   "--backend-config aws-efs-storage-generation.tfbackend.hcl",
                   "init -input=false -migrate-state -force-copy -backend-config=aws-efs-storage-generation.tfbackend.hcl",
                   "-detailed-exitcode", "gate-plan", "state-migration finish --workspace aws-efs"):
        assert needle in efs, needle
    order = [efs.index(s) for s in ("state-migration begin", "-migrate-state -force-copy", "-detailed-exitcode",
                                    "gate-plan", "state-migration finish")]
    assert order == sorted(order)
    assert "--no-dry-run" in efs and "--root-dir" in efs           # the steps load the configuration
    ebs = "\n".join(line for line in lines if '"aws-ebs/storage-generation"' in line)
    assert "-reconfigure" in ebs and "migrate" not in ebs and "-detailed-exitcode" not in ebs
    # the run leaves the migrating workspace's record to `finish`; the others moved with the run
    rec = _records(real)
    assert rec["aws-efs"]["bucket"] == "my-east1-tfstate-bucket"
    assert rec["aws-ebs"]["bucket"] == "noaa-ioos-cloud-sandbox-tfstate"


# ------------------------------------------------------------- begin and finish, over a fake tofu

@pytest.fixture
def migration(tmp_path):
    """A root directory, a fake tofu that remembers the backend file it was
    last initialised against and answers `state pull` from a canned state per
    backend file, and a meta-state recording the workspace's previous
    location."""
    from cs_image_system.base.meta_state import MetaState
    root = tmp_path / "ws" / "storage-generation"
    root.mkdir(parents=True)
    tofu = tmp_path / "tofu"
    tofu.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = init ]; then for a in "$@"; do case "$a" in -backend-config=*) printf %s "${a#-backend-config=}" > .current-backend;; esac; done; exit 0; fi\n'
        'if [ "$1" = state ] && [ "$2" = pull ]; then f=$(cat .current-backend); [ -f "state-for-$f.json" ] && cat "state-for-$f.json"; exit 0; fi\n'
        'echo "unexpected: $*" >&2; exit 1\n')
    tofu.chmod(0o755)
    (root / "ws.tfbackend.hcl").write_text(
        "# Backend 's3-east2' (s3) partial configuration for workspace ws\n"
        'bucket = "new-bucket"\nkey = "statefiles/new/ws.tfstate"\nregion = "us-east-2"\nencrypt = true\nuse_lockfile = true\n')
    ms = MetaState.at(tmp_path / "cfg")
    ms.record_state_locations({"ws": {"backend": "s3-east1", "type": "s3", "bucket": "old-bucket",
                                      "key": "statefiles/old/ws.tfstate", "region": "us-east-1",
                                      "encrypt": True, "use_lockfile": True}}, "r0")
    ctx = SimpleNamespace(meta_state=ms)
    return SimpleNamespace(root=root, tofu=str(tofu), ctx=ctx, ms=ms)


def _old_state(migration, serial: int = 7, lineage: str = "L1") -> None:
    (migration.root / "state-for-ws.tfbackend.previous.hcl.json").write_text(
        json.dumps({"version": 4, "serial": serial, "lineage": lineage, "resources": [{"type": "aws_efs_file_system"}]}))


def test_begin_backs_the_old_state_up_and_finish_records_the_move(migration):
    from cs_image_system.base.commands.state_migration import begin, finish
    _old_state(migration)
    assert begin(migration.ctx, "ws", migration.tofu, Path("ws.tfbackend.hcl"), "r1", migration.root) == 0
    previous = (migration.root / "ws.tfbackend.previous.hcl").read_text()
    assert 'bucket = "old-bucket"' in previous and 'key = "statefiles/old/ws.tfstate"' in previous and "PREVIOUS" in previous
    backup = json.loads((migration.root / "ws.backup-r1.tfstate").read_text())
    assert backup["serial"] == 7 and backup["lineage"] == "L1"
    assert (migration.root / ".current-backend").read_text() == "ws.tfbackend.previous.hcl"   # left on the OLD location
    progress = json.loads((migration.root / "ws.state-migration.json").read_text())
    assert progress["serial"] == 7 and progress["backup"] == "ws.backup-r1.tfstate" and progress["already"] is False
    assert migration.ms.state_locations()["ws"]["bucket"] == "old-bucket"                    # begin records nothing
    assert finish(migration.ctx, "ws", "r1", migration.root) == 0
    migration.ms.invalidate()
    assert migration.ms.state_locations()["ws"]["bucket"] == "new-bucket"
    (move,) = migration.ms.state_migrations()
    assert move["workspace"] == "ws" and move["from"]["bucket"] == "old-bucket" and move["to"]["bucket"] == "new-bucket"
    assert move["serial"] == 7 and move["backup"] == "ws.backup-r1.tfstate" and move["run"] == "r1" and move["at"]
    assert not (migration.root / "ws.state-migration.json").exists()
    assert (migration.root / "ws.backup-r1.tfstate").exists()                                # never deleted


def test_begin_refuses_a_new_location_that_holds_someone_elses_state(migration, caplog):
    from cs_image_system.base.commands.state_migration import begin
    _old_state(migration)
    (migration.root / "state-for-ws.tfbackend.hcl.json").write_text(json.dumps({"serial": 1, "lineage": "OTHER"}))
    with caplog.at_level(logging.ERROR):
        assert begin(migration.ctx, "ws", migration.tofu, Path("ws.tfbackend.hcl"), "r1", migration.root) == 1
    assert any("already holds state" in r.getMessage() and "collision" in r.getMessage() for r in caplog.records)
    assert not list(migration.root.glob("*.backup-*"))                                          # nothing copied


def test_begin_recognises_a_move_that_already_happened(migration):
    from cs_image_system.base.commands.state_migration import begin, finish
    _old_state(migration, serial=9, lineage="L1")
    (migration.root / "state-for-ws.tfbackend.hcl.json").write_text(json.dumps({"serial": 10, "lineage": "L1"}))
    assert begin(migration.ctx, "ws", migration.tofu, Path("ws.tfbackend.hcl"), "r2", migration.root) == 0
    assert (migration.root / ".current-backend").read_text() == "ws.tfbackend.hcl"           # left on the NEW one: the migrating init is a no-op
    assert json.loads((migration.root / "ws.state-migration.json").read_text())["already"] is True
    assert finish(migration.ctx, "ws", "r2", migration.root) == 0
    migration.ms.invalidate()
    assert migration.ms.state_locations()["ws"]["bucket"] == "new-bucket"


def test_begin_needs_a_record_and_the_backend_file(migration):
    from cs_image_system.base.commands.state_migration import begin, finish
    assert begin(migration.ctx, "ws", migration.tofu, None, "r1", migration.root) == 2
    assert begin(migration.ctx, "never-generated", migration.tofu, Path("ws.tfbackend.hcl"), "r1", migration.root) == 2
    assert finish(migration.ctx, "ws", "r1", migration.root) == 2                              # begin did not run
