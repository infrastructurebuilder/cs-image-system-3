# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The storage roots and the storage state machine.

* a storage root resolves gids through ``data.terraform_remote_state`` --
  no literal gid anywhere in generated IaC -- and keeps its own state in
  its declared backend; the storage read-model is the instance inventory;
  the runner is gated;
* state transitions validate (unattached-only guards, no resurrection,
  tombstone permanence), fire the plugin's transition action and are
  recorded only under an enabled apply; a recorded storage that left the
  YAML is a planned destroy; a tombstone regenerates as a new generation;
* the attach rule, public_read's exemption, cardinality and unknown groups
  are hard failures; retired fields are refused at load;
* the apply gate whitelists only operation-driven destroys;
* the S3 lookup asks for the storage's own bucket.

History: gate 4 (storage half), stage 63 dead-code item 9.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from harness import V2Run, command_lines, copy_config, load_context, reset_singletons, stub_environment, tree

LITERAL_GID = re.compile(r"\b(?:owner_)?gid\s*=\s*\d+\b")


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _write_yaml(path: Path, data) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _prepared(tmp_path, monkeypatch, mutate):
    """A config copy mutated BEFORE the context loads."""
    root = copy_config(tmp_path)
    mutate(root)
    return V2Run(tmp_path, monkeypatch, config_root=root)


def _set_storage(root: Path, name: str, **fields) -> None:
    p = root / "storages" / "storage0.yaml"
    data = yaml.safe_load(p.read_text())
    for s in data["storages"]:
        if s["name"] == name:
            s.update(fields)
    _write_yaml(p, data)


def _seed_storage_state(root: Path, states: dict[str, str]) -> None:
    ms = root / "meta-state"
    ms.mkdir(exist_ok=True)
    _write_yaml(ms / "storage-state.yaml",
                {"storages": {n: {"state": s, "history": [{"from": None, "to": s, "run": "seed"}]}
                              for n, s in states.items()}})


def test_storage_root_consumes_gids_by_reference_only(v2):
    assert v2.run(["identity", "storage"], apply=False).ok
    efs = tree(v2.generated / "storage" / "aws-efs" / "storage-generation")
    root = efs["aws-efs-storage-generation.tf"]
    assert 'data "terraform_remote_state" "oktagroups"' in root
    assert "oktagroups.tfstate" in root
    module = efs["aws-efs-storage-generation-storage-efs_storage.tf"]
    assert 'data.terraform_remote_state.oktagroups.outputs.group_gids["coops"]' in module
    assert 'data.terraform_remote_state.oktagroups.outputs.group_gids["stofs"]' in module
    assert '"path" = "/coops"' in module and '"permissions" = "2775"' in module
    assert 'output "storage_efs_storage"' in module
    # the storage root keeps its own state in the second S3 backend
    # and reads the identity root's from the LOCAL backend -- across buckets and types
    backend = efs["aws-efs-storage-generation.tfbackend.hcl"]
    assert 'bucket = "my-east1-tfstate-bucket"' in backend and 'key = "statefiles/csia/aws_efs.tfstate"' in backend
    assert 'backend = "local"' in root and 'path = "../../../../state/oktagroups.tfstate"' in root
    everything = "\n".join(tree(v2.generated / "storage").values())
    assert not LITERAL_GID.search(everything), "a literal gid leaked into storage IaC (N7)"
    # ebs carries no gid at the cloud level (ownership is applied at mount time)
    ebs = tree(v2.generated / "storage" / "aws-ebs" / "storage-generation")
    assert "group_gids" not in ebs["aws-ebs-storage-generation-storage-mnt_data.tf"]
    s3 = tree(v2.generated / "storage" / "aws-s3" / "storage-generation")
    assert "public_read = true" in s3["aws-s3-storage-generation-storage-default_bucket.tf"]


def test_storage_read_model_is_the_instance_inventory(v2):
    assert v2.run(["storage"], apply=False).ok
    model = yaml.safe_load((v2.meta_state / "storage.yaml").read_text())
    st = model["storages"]
    assert st["mnt_data"]["type"] == "ebs"
    assert st["mnt_data"]["attachment_cardinality"] == "single"
    assert st["mnt_data"]["allowed_groups"] == ["coops"]
    assert st["mnt_data"]["attachments"] == ["test2"]
    assert st["mnt_data"]["requested_state"] == "active"
    assert st["mnt_data"]["current_state"] is None  # never applied yet
    assert st["efs-storage"]["type"] == "efs" and st["efs-storage"]["share_mode"] == "2775"
    assert st["default-bucket"]["public_read"] is True and st["default-bucket"]["posix"] is False


def test_storage_runner_is_gated(v2):
    assert v2.run(["storage"], apply=False).ok
    cmds = command_lines((v2.generated / "storage" / "run-storage.sh").read_text())
    roots = len(yaml.safe_load((v2.config_root / "cfg" / "storage-builders.yml").read_text())["storage_builders"])
    assert roots >= 5
    assert sum("tofu plan -input=false -out=tfplan" in c for c in cmds) == roots   # one plan per declared storage root
    assert sum("gate-plan --planfile tfplan" in c for c in cmds) == roots          # and one gate per plan
    assert not any(" apply " in c for c in cmds)


def test_archiving_an_attached_storage_is_refused(tmp_path, monkeypatch):
    run = _prepared(tmp_path, monkeypatch, lambda root: (
        _seed_storage_state(root, {"mnt_data": "active"}),
        _set_storage(root, "mnt_data", state="archived")))
    try:
        summary = run.run(["storage"], apply=False)
        assert not summary.ok
        assert any("archived" in e and "test2" in e for e in summary.validation_errors)
    finally:
        run.restore_cwd()


def test_archive_and_restore_are_legal_when_unattached(tmp_path, monkeypatch):
    # the state machine is the subject; archiving is realized by the pd builder only,
    # so EFS is stubbed as archive-capable here
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuEfsStorageBuilder
    monkeypatch.setattr(TofuEfsStorageBuilder, "supports_archive", lambda self: True)
    run = _prepared(tmp_path, monkeypatch, lambda root: (
        _seed_storage_state(root, {"efs-storage": "active"}),
        _set_storage(root, "efs-storage", state="archived")))
    try:
        summary = run.run(["storage"], apply=False)
        assert summary.ok, summary.validation_errors
        # archived: the resource is retained, the read-model shows requested vs current
        model = yaml.safe_load((run.meta_state / "storage.yaml").read_text())
        assert model["storages"]["efs-storage"] == {**model["storages"]["efs-storage"],
                                                    "requested_state": "archived",
                                                    "current_state": "active"}
        # after a real apply the transition is recorded and becomes authoritative
        from cs_image_system.contract.lifecycles import Lifecycle
        from cs_image_system.base.read_models import record_storage_transitions
        # truthful-recorders (finding 21): the recorder refuses to write a
        # reality-claiming record while the apply flag is off ...
        record_storage_transitions(run.ctx, Lifecycle.STORAGE)
        state = yaml.safe_load((run.meta_state / "storage-state.yaml").read_text())
        assert state["storages"]["efs-storage"]["state"] == "active"  # unchanged
        # ... and records only under an enabled apply
        run.ctx.config["apply_storage"] = True
        record_storage_transitions(run.ctx, Lifecycle.STORAGE)
        state = yaml.safe_load((run.meta_state / "storage-state.yaml").read_text())
        assert state["storages"]["efs-storage"]["state"] == "archived"
        assert state["storages"]["efs-storage"]["history"][-1]["to"] == "archived"
        assert state["storages"]["efs-storage"]["history"][-1]["run"] == run.ctx.run_id
    finally:
        run.restore_cwd()


def test_apply_off_run_records_no_transitions(tmp_path, monkeypatch):
    """truthful-recorders (finding 21): a full storage run with the apply
    flag off leaves storage-state.yaml exactly as seeded — the after-apply
    hook must not write reality-claiming records without a real apply."""
    # the state machine is the subject; archiving is realized by the pd builder only,
    # so EFS is stubbed as archive-capable here
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuEfsStorageBuilder
    monkeypatch.setattr(TofuEfsStorageBuilder, "supports_archive", lambda self: True)
    run = _prepared(tmp_path, monkeypatch, lambda root: (
        _seed_storage_state(root, {"efs-storage": "active"}),
        _set_storage(root, "efs-storage", state="archived")))
    try:
        summary = run.run(["storage"], apply=True)  # apply step runs; flag stays false
        assert summary.ok, summary.validation_errors
        state = yaml.safe_load((run.meta_state / "storage-state.yaml").read_text())
        assert state["storages"]["efs-storage"]["state"] == "active"
        assert state["storages"]["efs-storage"]["history"][-1]["run"] == "seed"
    finally:
        run.restore_cwd()


def test_absent_apply_flag_key_means_false(tmp_path, monkeypatch):
    """finding 20 pinned: a missing apply_<lifecycle> key behaves as OFF."""
    run = _prepared(tmp_path, monkeypatch, lambda root: None)
    try:
        from cs_image_system.base import utils
        for key in ("storage", "instances", "identity", "release", "never-a-lifecycle"):
            run.ctx.config.pop(f"apply_{key}", None)
            assert utils.apply_enabled(run.ctx, key) is False
    finally:
        run.restore_cwd()


def test_new_storages_start_active_and_a_tombstone_regenerates(tmp_path, monkeypatch):
    """'Destroyed is terminal' is replaced: a declared storage whose
    record is a tombstone is a NEW generation of the name (legal), while a
    never-applied storage still must start active."""
    run = _prepared(tmp_path, monkeypatch, lambda root: (
        _seed_storage_state(root, {"efs-storage": "destroyed"}),
        _set_storage(root, "efs-storage", state="active"),
        _set_storage(root, "default-bucket", state="destroyed")))
    try:
        summary = run.run(["storage"], apply=False)
        assert not summary.ok
        errs = "\n".join(summary.validation_errors)
        assert "default-bucket" in errs and "'active'" in errs
    finally:
        run.restore_cwd()


def test_a_recorded_storage_that_left_the_yaml_is_a_planned_destroy(tmp_path, monkeypatch):
    """DESIGN N22 ('entries never leave the YAML') is replaced: the demise
    of a storage is its un-declaration; a still-live record that no longer
    has an entry is destroyed by the next run (its root known from the
    record's facts), and a tombstone that left the YAML is simply history."""
    def mutate(root: Path):
        _seed_storage_state(root, {"old_scratch": "destroyed"})
    run = _prepared(tmp_path, monkeypatch, mutate)
    try:
        summary = run.run(["storage"], apply=False)
        assert summary.ok, summary.validation_errors      # a tombstone needs nothing
    finally:
        run.restore_cwd()


def test_destroy_transition_fires_plugin_action_and_whitelists_only_that_destroy(tmp_path, monkeypatch):
    run = _prepared(tmp_path, monkeypatch, lambda root: (
        _seed_storage_state(root, {"default-bucket": "active"}),
        _set_storage(root, "default-bucket", state="destroyed")))
    try:
        summary = run.run(["storage"], apply=False)
        assert summary.ok, summary.validation_errors
        s3 = tree(run.generated / "storage" / "aws-s3" / "storage-generation")
        assert 'module "storage_default_bucket"' not in s3["aws-s3-storage-generation-storage-default_bucket.tf"]
        assert "DESTROYED (tombstone" in s3["aws-s3-storage-generation-storage-default_bucket.tf"]
        cmds = command_lines((run.generated / "storage" / "run-storage.sh").read_text())
        assert any("aws s3 rm s3://noscsb-csis-test-514190660293-default-bucket --recursive --profile noaa" in c for c in cmds)
        gates = [c for c in cmds if "gate-plan" in c]
        s3_gate = next(c for c in gates if 'cd "aws-s3/storage-generation"' in c)
        assert "--allow-destroy module.storage_default_bucket" in s3_gate
        for other in (c for c in gates if c is not s3_gate):
            assert "--allow-destroy" not in other
    finally:
        run.restore_cwd()


def test_attach_rule_is_a_hard_failure(tmp_path, monkeypatch):
    # test2's image belongs to coops; take coops off mnt_data's allowed list
    run = _prepared(tmp_path, monkeypatch, lambda root: _set_storage(root, "mnt_data", groups=["stofs"]))
    try:
        summary = run.run(["storage"], apply=False)
        assert not summary.ok
        assert any("'mnt_data'" in e and "(N2)" in e for e in summary.validation_errors)
    finally:
        run.restore_cwd()


def test_public_read_exempts_the_attach_rule(tmp_path, monkeypatch):
    run = _prepared(tmp_path, monkeypatch,
                    lambda root: _set_storage(root, "mnt_data", groups=["stofs"], public_read=True))
    try:
        assert run.run(["storage"], apply=False).ok
    finally:
        run.restore_cwd()


def test_single_attach_cardinality_is_enforced(tmp_path, monkeypatch):
    def mutate(root: Path):
        p = root / "instances" / "instances.yaml"
        data = yaml.safe_load(p.read_text())
        data["instances"][0]["storages"] = [{"name": "mnt_data", "mount_point": "/mnt/data"}]
        _write_yaml(p, data)
    run = _prepared(tmp_path, monkeypatch, mutate)
    try:
        summary = run.run(["storage"], apply=False)
        assert not summary.ok
        assert any("(N16)" in e and "mnt_data" in e for e in summary.validation_errors)
    finally:
        run.restore_cwd()


def test_retired_all_value_and_per_instance_groups_are_rejected_at_load(tmp_path, monkeypatch):
    from cs_image_system.base.models.storage import Storage
    with pytest.raises(ValueError, match="retired 'ALL'"):
        Storage(name="x", type_="aws-ebs", runtime="aws", groups=["ALL"])
    from cs_image_system.base.models.instance import Instance
    with pytest.raises(ValueError, match="V2 removed per-instance groups"):
        Instance(name="i", image="img", **{"groups": ["coops"]})   # type: ignore[call-arg]   a V1-era key, no longer a field
    with pytest.raises(ValueError, match="share_mode"):
        Storage(name="x", type_="aws-ebs", runtime="aws", share_mode="0777")
    with pytest.raises(ValueError, match="unknown state"):
        Storage(name="x", type_="aws-ebs", runtime="aws", state="deleted")


def test_unknown_allowed_group_is_a_hard_failure(tmp_path, monkeypatch):
    run = _prepared(tmp_path, monkeypatch, lambda root: _set_storage(root, "efs-storage", groups=["nope"]))
    try:
        summary = run.run(["storage"], apply=False)
        assert not summary.ok
        assert any("'nope'" in e and "efs-storage" in e for e in summary.validation_errors)
    finally:
        run.restore_cwd()


def test_gate_plan_whitelists_only_operation_driven_destroys(tmp_path):
    from cs_image_system.base.commands.gate import gate_plan
    plan = {"resource_changes": [
        {"address": "module.storage_default_bucket.aws_s3_bucket.this", "change": {"actions": ["delete"]}},
        {"address": "module.storage_mnt_data.aws_ebs_volume.this", "change": {"actions": ["update"]}},
        {"address": "module.instance_test.aws_instance.this", "change": {"actions": ["delete", "create"]}},
        {"address": "module.group_coops.oktapam_group.user", "change": {"actions": ["delete"]}},
    ]}
    assert gate_plan(plan, ["module.storage_default_bucket", "module.instance_test.aws_instance.this"]) == [
        "module.group_coops.oktapam_group.user"]
    assert gate_plan(plan, []) == [
        "module.storage_default_bucket.aws_s3_bucket.this",
        "module.instance_test.aws_instance.this",
        "module.group_coops.oktapam_group.user"]
    p = tmp_path / "plan.json"
    import json
    p.write_text(json.dumps({"resource_changes": []}))
    assert gate_plan(p, []) == []


# -------------------------------------------------------- the S3 lookup

def test_the_s3_lookup_asks_for_the_storages_own_bucket(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace
    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuS3StorageBuilder
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    try:
        s3b = ctx.storage_builders["aws-s3"]
        asked: list[str] = []
        fake = SimpleNamespace(get_bucket_tagging=lambda Bucket: asked.append(Bucket) or {"TagSet": []})
        monkeypatch.setattr(TofuS3StorageBuilder, "_aws_client", lambda self, service: fake)
        storage = next(s for s in ctx.storages if str(s.get_type()) == "aws-s3")
        TofuS3StorageBuilder._lookup(cast(Any, s3b), storage)
        expected = getattr(storage, "bucket_name", None) or storage.get_name()
        assert asked == [expected], asked
        other = SimpleNamespace(bucket_name="second-bucket", get_name=lambda: "second")
        TofuS3StorageBuilder._lookup(cast(Any, s3b), cast(Any, other))
        assert asked[-1] == "second-bucket", "a second storage on the same builder is its own bucket"
    finally:
        reset_singletons()

