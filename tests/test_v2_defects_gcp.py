# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 63, the GCP medium items (14, 17): the gcloud a runtime runs is the
one it declares, a session needs a declared mechanism, Filestore answers the
state query, and ``tf-gcp`` is not a storage builder type. Decided by the
operator 2026-09-25; every test here failed before its fix.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml

from tests.v2_support import FIXTURE_CONFIG, copy_config, load_context, reset_singletons, stub_environment

DECLARED = "/usr/local/bin/gcloud"          # the fixture's executables entry named gcloud


@pytest.fixture
def ctx(monkeypatch):
    stub_environment(monkeypatch)
    c = load_context(FIXTURE_CONFIG)
    yield c
    reset_singletons()


class _Recorder:
    def __init__(self, rc: int = 0, stdout: str = "", stderr: str = ""):
        self.calls: list[list[str]] = []
        self.result = SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)

    def __call__(self, cmd, *a, **kw):
        self.calls.append([str(c) for c in cmd])
        return self.result


# ----------------------------------------- 14. the declared gcloud binary

def test_the_gcp_runtime_names_its_gcloud_entry_and_resolves_its_binary(ctx):
    rtb = ctx.runtime_builders["gcloud-east1"]
    assert rtb.model.get_executable() == "gcloud"
    assert rtb.gcloud_binary() == DECLARED


def test_an_undeclared_gcloud_entry_is_refused_by_validate(tmp_path: Path, monkeypatch):
    # the harness stubs the executables check (no real binaries in tests); the
    # existence half it wraps is called directly
    from cs_image_system.base.commands.validate import check_existence_of_executable
    root = copy_config(tmp_path)
    ex = root / "cfg" / "executables.yml"
    data = yaml.safe_load(ex.read_text())
    data["executables"] = [e for e in data["executables"] if e["name"] != "gcloud"]
    ex.write_text(yaml.safe_dump(data, sort_keys=False))
    stub_environment(monkeypatch)
    c = load_context(root)
    try:
        errors = [str(e) for e in check_existence_of_executable(c.executables, cast(Any, c.runtime_builders))]
        assert any("Executable gcloud specified for provider gcloud-east1" in e for e in errors), errors
        with pytest.raises(ValueError, match="executable 'gcloud' is not declared"):
            cast(Any, c.runtime_builders["gcloud-east1"]).gcloud_binary()
    finally:
        reset_singletons()


def test_the_session_command_runs_the_declared_gcloud(ctx, monkeypatch):
    rec = _Recorder(0, "ok")
    monkeypatch.setattr(subprocess, "run", rec)
    rc, _ = ctx.runtime_builders["gcloud-east1"].run_session_command("gce-test", "true")
    assert rc == 0 and rec.calls and rec.calls[0][0] == DECLARED, rec.calls
    assert "--tunnel-through-iap" in rec.calls[0]


def test_a_session_on_a_runtime_without_a_mechanism_is_refused_before_any_call(ctx, monkeypatch):
    rtb = ctx.runtime_builders["gcloud-east1"]
    monkeypatch.setattr(rtb.model, "session_mechanism", None)
    rec = _Recorder()
    monkeypatch.setattr(subprocess, "run", rec)
    with pytest.raises(RuntimeError, match="declares no session_mechanism"):
        rtb.run_session_command("gce-test", "true")
    assert rec.calls == [], "nothing was tunnelled"


def _storage_on(ctx, builder: str) -> Any:
    found = [s for s in ctx.storages if str(getattr(s, "type_", "")) == builder]
    assert found, f"the fixture has no storage on {builder}"
    return found[0]


def test_the_generated_archive_and_wipe_scripts_run_the_declared_gcloud(tmp_path: Path, monkeypatch):
    # a COPY: the scripts are written under the context's generation path,
    # which for the frozen fixture would be inside tests/fixtures/config
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    from cs_image_system.base.models.storage import (STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED,
                                                     STORAGE_STATE_DESTROYED)
    pd = ctx.storage_builders["gcp-pd"]
    disk = _storage_on(ctx, "gcp-pd")
    actions = pd.transition_actions(disk, STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED)
    assert actions, "archiving a disk writes a snapshot script"
    for e in actions:
        body = (Path(str(ctx.generation_path)) / str(e.working_directory) / e.args[0]).read_text()
        assert f"{DECLARED} compute disks snapshot" in body and "\ngcloud " not in body, body
    gcs = ctx.storage_builders["gcp-gcs"]
    bucket = _storage_on(ctx, "gcp-gcs")
    (wipe,) = gcs.transition_actions(bucket, STORAGE_STATE_ACTIVE, STORAGE_STATE_DESTROYED)
    body = (Path(str(ctx.generation_path)) / str(wipe.working_directory) / wipe.args[0]).read_text()
    assert f"out=$({DECLARED} storage rm" in body, body
    assert str(tmp_path) in str(ctx.generation_path)
    reset_singletons()


def test_the_bucket_lookup_runs_the_declared_gcloud(ctx, monkeypatch):
    rec = _Recorder(0, '{"name": "b"}')
    monkeypatch.setattr(subprocess, "run", rec)
    gcs = ctx.storage_builders["gcp-gcs"]
    gcs._lookup(_storage_on(ctx, "gcp-gcs"))
    assert rec.calls[0][0] == DECLARED, rec.calls


# --------------------------------- 17. Filestore in the state query; tf-gcp

def _with_filestore(tmp_path: Path) -> Path:
    root = copy_config(tmp_path)
    sb = root / "cfg" / "storage-builders.yml"
    data = yaml.safe_load(sb.read_text())
    data["storage_builders"].append({"name": "gcp-fs", "type": "tf-gcp-filestore", "executable": "open-tofu-1",
                                     "runtime": "gcloud-east1", "state_configuration": "s3-east1"})
    sb.write_text(yaml.safe_dump(data, sort_keys=False))
    (root / "storages" / "filestore.yaml").write_text(yaml.safe_dump(
        {"storages": [{"name": "shared_nfs", "type": "gcp-fs", "mount_point": "/mnt/shared", "state": "active"}]}))
    return root


def test_an_unimplemented_lookup_is_reported_unavailable_not_dropped():
    from cs_image_system.base.state_query import StateReport, _query
    report = StateReport(run="test")

    def cannot():
        raise NotImplementedError("SomeBuilder cannot query identity state")
    assert _query(report, "groups/some", cannot) is None
    assert report.unavailable == ["groups/some: cannot be queried (SomeBuilder cannot query identity state)"]


def test_filestore_looks_itself_up_through_the_declared_gcloud(tmp_path: Path, monkeypatch):
    # the harness stubs every storage builder's query_state; keep the real one
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuStorageBuilder
    real_query_state = TofuStorageBuilder.query_state
    stub_environment(monkeypatch)
    c = load_context(_with_filestore(tmp_path))
    try:
        fs: Any = c.storage_builders["gcp-fs"]
        storage = _storage_on(c, "gcp-fs")
        found = _Recorder(0, '{"name": "projects/p/locations/us-east1-b/instances/shared-nfs", "state": "READY", '
                             '"fileShares": [{"name": "share", "capacityGb": "1024"}], "labels": {"csis": "true"}}')
        monkeypatch.setattr(subprocess, "run", found)
        rec = fs._lookup(storage)
        cmd = found.calls[0]
        assert cmd[:5] == [DECLARED, "filestore", "instances", "describe", "shared-nfs"], cmd
        assert cmd[cmd.index("--location") + 1] == "us-east1-b"
        assert rec == {"id": "shared-nfs", "state": "READY", "tags": {"csis": "true"}, "size": 1024}
        state = real_query_state(fs)
        assert state["shared_nfs"]["present"] is True and state["shared_nfs"]["type"] == "filestore", state

        monkeypatch.setattr(subprocess, "run", _Recorder(1, "", "ERROR: (gcloud.filestore.instances.describe) NOT_FOUND: resource"))
        assert fs._lookup(storage) is None
        assert real_query_state(fs)["shared_nfs"]["present"] is False

        monkeypatch.setattr(subprocess, "run", _Recorder(1, "", "ERROR: PERMISSION_DENIED"))
        with pytest.raises(RuntimeError, match="PERMISSION_DENIED"):
            fs._lookup(storage)
    finally:
        reset_singletons()


def test_the_base_tf_gcp_type_is_refused_at_load(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    sb = root / "cfg" / "storage-builders.yml"
    data = yaml.safe_load(sb.read_text())
    data["storage_builders"].append({"name": "gcp-any", "type": "tf-gcp", "executable": "open-tofu-1",
                                     "runtime": "gcloud-east1"})
    sb.write_text(yaml.safe_dump(data, sort_keys=False))
    stub_environment(monkeypatch)
    try:
        with pytest.raises(Exception) as exc:
            load_context(root)
        message = str(exc.value)
        assert "type 'tf-gcp' is the shared base" in message and "tf-gcp-pd" in message, message
    finally:
        reset_singletons()
