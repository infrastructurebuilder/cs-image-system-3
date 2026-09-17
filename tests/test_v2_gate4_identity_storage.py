# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""V2 gate 4 (DESIGN §4, phase D+E): read-models, the gid reference chain
and the storage state machine.

* the identity root emits an outputs block (group -> gid) fed by the
  plugin's queryable shim (N7), and a structural read-model file (N6);
* a storage root resolves gids through ``data.terraform_remote_state`` --
  no literal gid anywhere in generated IaC;
* the storage read-model is the instance inventory (N10);
* state transitions validate (unattached-only guards, no resurrection,
  tombstone permanence) and fire the plugin's transition action (N21);
* the attach rule (N2/N3) and cardinality (N16) are hard failures.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from v2_support import V2Run, command_lines, copy_config, tree

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


# ---------------------------------------------------------------- identity

def test_identity_root_emits_gid_outputs_via_the_shim(v2):
    assert v2.run(["identity"], apply=False).ok
    gen = tree(v2.generated / "identity" / "oktagroups" / "group-generation")
    outputs = gen["oktagroups-group-generation-outputs.tf"]
    assert 'data "external" "group_gids"' in outputs
    assert '"cs-image-system"' in outputs and '"export-gids"' in outputs
    assert 'output "group_gids"' in outputs
    assert "tonumber(gid)" in outputs
    assert 'output "groups"' in outputs
    assert "module.group_coops.user_group_id" in outputs
    root_tf = gen["oktagroups-group-generation.tf"]
    assert "hashicorp/external" in root_tf
    # the query is the shim's structural input: identity type, org/team, group names
    assert 'identity_type = "okta"' in outputs
    assert "basic,coops,secofs,stofs,tcmet" in outputs
    assert not LITERAL_GID.search("\n".join(gen.values()))


def test_identity_read_model_is_structural(v2):
    assert v2.run(["identity"], apply=False).ok
    model = yaml.safe_load((v2.meta_state / "identity.yaml").read_text())
    coops = model["groups"]["coops"]
    assert coops["identity_type"] == "okta"
    assert coops["gid_policy"] == "creation-only"
    assert coops["builder"] == "oktagroups"
    assert coops["members"] == ["avery.alpha", "casey.charlie"]   # mirrors live OPA (2026-08-31)
    assert "avery.alpha" in coops["admins"]
    assert coops["managed"] is True
    assert model["groups"]["basic"]["is_root"] is True
    assert "avery.alpha" in model["users"]
    assert not re.search(r"\bgid: \d+", yaml.safe_dump(model))


def test_identity_runner_script_is_gated_and_never_applies_unless_configured(v2):
    assert v2.run(["identity"], apply=False).ok
    script = (v2.generated / "identity" / "run-identity.sh").read_text()
    cmds = command_lines(script)
    assert any("tofu plan -input=false -out=tfplan" in c for c in cmds)
    assert any("cs-image-system gate-plan --planfile tfplan" in c for c in cmds)
    assert not any(" apply " in c for c in cmds), "apply_identity is off in the fixture"
    assert "# state: workspace oktagroups -> s3://noaa-ioos-cloud-sandbox-tfstate/" in script


def test_group_disappearance_is_a_hard_failure(tmp_path, monkeypatch):
    def mutate(root: Path):
        ms = root / "meta-state"
        ms.mkdir()
        _write_yaml(ms / "identity.yaml", {"groups": {"ghost": {"managed": True, "builder": "oktagroups"}}})
    run = _prepared(tmp_path, monkeypatch, mutate)
    try:
        summary = run.run(["identity"], apply=False)
        assert not summary.ok
        assert any("group 'ghost' was managed" in e for e in summary.validation_errors)
    finally:
        run.restore_cwd()


def test_unmanaged_group_is_state_rm_never_destroyed(tmp_path, monkeypatch):
    def mutate(root: Path):
        p = root / "groups" / "group-tcmet.yaml"
        data = yaml.safe_load(p.read_text())
        data["groups"][0]["unmanaged"] = True
        _write_yaml(p, data)
        ms = root / "meta-state"
        ms.mkdir()
        _write_yaml(ms / "identity.yaml", {"groups": {"tcmet": {"managed": True, "builder": "oktagroups"}}})
    run = _prepared(tmp_path, monkeypatch, mutate)
    try:
        assert run.run(["identity"], apply=False).ok
        gen = tree(run.generated / "identity" / "oktagroups" / "group-generation")
        assert 'module "group_tcmet"' not in gen["oktagroups-group-generation-group-tcmet.tf"]
        assert "UNMANAGED" in gen["oktagroups-group-generation-group-tcmet.tf"]
        cmds = command_lines((run.generated / "identity" / "run-identity.sh").read_text())
        assert any("tofu state rm module.group_tcmet" in c for c in cmds)
        assert not any("destroy" in c for c in cmds)
        model = yaml.safe_load((run.meta_state / "identity.yaml").read_text())
        assert model["groups"]["tcmet"]["managed"] is False
    finally:
        run.restore_cwd()


# ----------------------------------------------------------------- storage

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
    # stage 46: the storage root keeps its own state in the second backend and
    # reads the identity root's from the first -- the isolation is real
    backend = efs["aws-efs-storage-generation.tfbackend.hcl"]
    assert 'bucket = "my-east1-tfstate-bucket"' in backend and 'key = "statefiles/csia/aws_efs.tfstate"' in backend
    assert 'bucket = "noaa-ioos-cloud-sandbox-tfstate"' in root and "csia-image-system-test/oktagroups.tfstate" in root
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
    assert sum("tofu plan -input=false -out=tfplan" in c for c in cmds) == 5  # 3 aws + pd/gcs
    assert sum("gate-plan --planfile tfplan" in c for c in cmds) == 5  # 3 aws + pd/gcs
    assert not any(" apply " in c for c in cmds)


def test_archiving_an_attached_storage_is_refused(tmp_path, monkeypatch):
    run = _prepared(tmp_path, monkeypatch, lambda root: (
        _seed_storage_state(root, {"mnt_data": "active"}),
        _set_storage(root, "mnt_data", state="archived")))
    try:
        summary = run.run(["storage"], apply=False)
        assert not summary.ok
        assert any("cannot move active -> archived while attached by ['test2']" in e
                   for e in summary.validation_errors)
    finally:
        run.restore_cwd()


def test_archive_and_restore_are_legal_when_unattached(tmp_path, monkeypatch):
    # the state machine is the subject; archiving is realized by the pd builder only
    # (stage 11.6), so EFS is stubbed as archive-capable here
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
        from cs_image_system.base.lifecycles import Lifecycle
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
    # the state machine is the subject; archiving is realized by the pd builder only
    # (stage 11.6), so EFS is stubbed as archive-capable here
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
            assert utils.apply_enabled(key) is False
    finally:
        run.restore_cwd()


def test_new_storages_start_active_and_a_tombstone_regenerates(tmp_path, monkeypatch):
    """stage 10.12 replaced 'destroyed is terminal': a declared storage whose
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
        assert "cannot be resurrected" not in errs
        assert "default-bucket' has never been applied; a new storage must start 'active'" in errs
    finally:
        run.restore_cwd()


def test_a_recorded_storage_that_left_the_yaml_is_a_planned_destroy(tmp_path, monkeypatch):
    """stage 10.11 replaced N22 ('entries never leave the YAML'): the demise
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
        assert any("may not attach storage 'mnt_data': allowed groups are ['stofs'] (N2)" in e
                   for e in summary.validation_errors)
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
        assert any("is single-attach but instances ['test', 'test2'] all attach it (N16)" in e
                   for e in summary.validation_errors)
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
        assert any("storage 'efs-storage' allows unknown group 'nope'" in e for e in summary.validation_errors)
    finally:
        run.restore_cwd()


# ------------------------------------------------------------- apply gate

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
