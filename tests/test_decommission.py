# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Decommission through the gate (DESIGN N19) -- findings 52 and 53, found live
tearing down the first GCE instance, proven here on the AWS runtime.

The tests' meta-state records ``test2`` as launched and pinned
(``pins.yaml`` instances, ``launch-params.yaml``). Undeclaring it must:

* still emit its runtime's instance root and whitelist its destroy at the
  gate -- even when it was the LAST instance on that runtime (52: the root
  used to vanish with the last declaration, so nothing ever planned the
  destroy and the VM stayed orphaned in tofu state and the cloud);
* whitelist it only on ITS runtime's root, not every root (the pinned
  build's lineage record names the runtime);
* leave the record alone until a real apply destroyed it (53: the forget
  ran at generation, so a DRY run erased the record first and the gate
  then had nothing to whitelist -- the finding-21 truthful-recorders shape).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.harness import FixtureRun, cli_context, copy_config

AWS_ROOT = Path("instance-image") / "open-tofu" / "instance-generation"
#: the instance root of the fixture's other runtime (docker-fixture's container-test)
OTHER_ROOT = "tofu-docker/instance-generation"
AWS = "aws-east2-runtime"
#: the decommissioned subject, and the AWS runtime's other instance
SUBJECT, NEIGHBOUR = "test2", "test"
RUNNER = Path("instance-image") / "run-instance-image.sh"


def _undeclare(root: Path, *names: str) -> None:
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    d["instances"] = [i for i in d["instances"] if i["name"] not in names]
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _gate_lines(script: str) -> dict[str, str]:
    """{root dir: its gate-plan command line}"""
    out: dict[str, str] = {}
    for line in script.splitlines():
        if "gate-plan" in line:
            root = line.split('cd "', 1)[1].split('"', 1)[0]
            out[root] = line
    return out


AWS_BUILD = "ami-0dask0049"


def _seed_launched(root: Path, name: str, build: str, runtime: str) -> None:
    """copy_config drops meta-state; record ``name`` as launched from ``build``
    (pin + launch params) with a lineage record naming its runtime."""
    ms = root / "meta-state"
    ms.mkdir(exist_ok=True)
    (ms / "pins.yaml").write_text(yaml.safe_dump(
        {"images": {}, "instances": {name: build}, "upgrades": []}, sort_keys=True))
    # launched stays False: the whitelist keys on the record's presence, and a
    # launched instance would trip the launch-immutability validator (N26)
    # against freshly computed parameters when it is still declared
    (ms / "launch-params.yaml").write_text(yaml.safe_dump(
        {"instances": {name: {"build": build, "launched": False, "hostname": name}}}, sort_keys=True))
    (ms / "lineage.yaml").write_text(yaml.safe_dump({"builds": [{
        "build_id": build, "name": build, "series": "imgfile-basic-dask", "runtime": runtime,
        "parent": "ami-0basicrh100049", "run": "r0", "chain": ["imgfile-basic-dask"],
        "mods": [], "local_mods": False, "input_fingerprint": "0" * 64,
        "tests": {"assertions": 0, "in_bake": True}, "update": None,
        "capabilities": {"identity_types": ["okta"], "storage_types": ["ebs", "efs", "s3"]}}]},
        sort_keys=True))


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch):
    """A config copy recording test2 as launched, plus a factory that
    builds the run AFTER the test mutated the copy (FixtureRun loads the context
    at construction)."""
    root = copy_config(tmp_path)
    _seed_launched(root, SUBJECT, AWS_BUILD, AWS)
    runs: list[FixtureRun] = []

    def make_run(dry_run: bool = True) -> FixtureRun:
        run = FixtureRun(tmp_path, monkeypatch, config_root=root, dry_run=dry_run)
        runs.append(run)
        return run
    try:
        yield root, make_run
    finally:
        for run in runs:
            run.restore_cwd()


def test_undeclared_last_instance_still_gets_a_root_and_a_whitelisted_destroy(prepared):
    root, make_run = prepared
    _undeclare(root, SUBJECT, NEIGHBOUR)               # the AWS runtime's last instances
    run = make_run()
    assert run.run(["instance-image"], apply=False).ok
    aws = run.generated / AWS_ROOT
    assert aws.is_dir(), "finding 52: the root must still exist to plan the destroy"
    tf = "\n".join(p.read_text() for p in aws.glob("*.tf"))
    assert 'module "instance_test2"' not in tf           # undeclared: no module call
    assert "backend" in tf and 'provider "aws"' in tf    # terraform + provider + backend only
    gates = _gate_lines((run.generated / RUNNER).read_text())
    assert "--allow-destroy module.instance_test2" in gates["open-tofu/instance-generation"]
    # scoped to its own runtime (the pinned build was baked on aws-east2-runtime)
    assert "instance_test2" not in gates[OTHER_ROOT]


def test_dry_run_keeps_the_decommission_record(prepared):
    root, make_run = prepared
    _undeclare(root, SUBJECT)
    run = make_run()
    assert run.run(["instance-image"], apply=False).ok
    pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
    params = yaml.safe_load((run.meta_state / "launch-params.yaml").read_text())
    assert SUBJECT in pins["instances"], "finding 53: a dry run must not forget a launched instance"
    assert SUBJECT in params["instances"]
    assert not any(u.get("op") == "decommission" for u in pins.get("upgrades", []))


def test_declared_instances_keep_their_roots_unchanged(prepared):
    """Nothing changes for the ordinary shape: every declared instance's root
    and module call are emitted and no destroy is whitelisted."""
    _, make_run = prepared
    run = make_run()
    assert run.run(["instance-image"], apply=False).ok
    gates = _gate_lines((run.generated / RUNNER).read_text())
    assert all("--allow-destroy" not in line for line in gates.values()), gates


def test_after_apply_hooks_honour_per_root_scoping(prepared):
    """Per-root apply scoping: with apply_instances listing only
    the docker runtime, the AWS root merely planned -- so its decommission
    record must survive and its instances stay unlaunched, while the docker
    instance is marked launched. Listing the AWS root then forgets it."""
    from cs_image_system.base.launch_params import forget_decommissioned, mark_launched
    from cs_image_system.contract.lifecycles import Lifecycle
    root, make_run = prepared
    _undeclare(root, SUBJECT)
    run = make_run()
    assert run.run(["instance-image"], apply=False).ok
    ms = run.ctx.meta_state
    run.ctx.config["apply_instances"] = ["docker-fixture"]
    forget_decommissioned(run.ctx, Lifecycle.INSTANCE_IMAGE)
    mark_launched(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert SUBJECT in ms.instance_pins() and SUBJECT in ms.launch_params()
    launched = {n: bool(p.get("launched")) for n, p in ms.launch_params().items()}
    assert launched["container-test"], launched
    assert not launched[SUBJECT] and not launched[NEIGHBOUR], launched
    run.ctx.config["apply_instances"] = ["open-tofu"]
    forget_decommissioned(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert SUBJECT not in ms.instance_pins() and SUBJECT not in ms.launch_params()


def test_deferred_parent_binds_from_the_booted_image_after_apply(tmp_path, monkeypatch):
    """Finding 49: an instance launched from a family lookup (parent deferred),
    so nothing bound its pin at launch; a later re-bake's apply then bound
    it to the NEW series head while the VM kept running the old image.
    After a real apply the pin now comes from reality -- the image the
    instance actually booted -- when lineage records it."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    root = copy_config(tmp_path)
    # lineage knows the build the VM booted; no pin yet (deferred parent)
    _seed_launched(root, "someone-else", "unrelated", AWS)
    ms = root / "meta-state"
    (ms / "pins.yaml").write_text(yaml.safe_dump({"images": {}, "instances": {}, "upgrades": []}))
    lineage = yaml.safe_load((ms / "lineage.yaml").read_text())
    lineage["builds"][0]["build_id"] = AWS_BUILD
    lineage["builds"][0]["name"] = AWS_BUILD
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))
    cfg = root / "cfg" / "_config.yml"
    cfg.write_text(cfg.read_text().replace("  apply_instances: false", "  apply_instances: true"))
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_boot_image", lambda self, name: AWS_BUILD)
    run = FixtureRun(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["instance-image"], apply=False).ok
        builder = run.ctx.instance_builders["open-tofu"]
        builder.post_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)   # simulate the apply
        pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
        assert pins["instances"][SUBJECT] == AWS_BUILD
    finally:
        run.restore_cwd()


def test_an_applied_decommission_forgets_the_pin(prepared):
    """The other half of the dry-run rule above, and the one nothing covered:
    when the destroy really applied, the instance's pin must GO.

    A pin that outlives its instance is not merely untidy. With
    `config.require_released_builds` on, a declared instance pinned to a build
    that was never released makes `validate` refuse EVERY run -- including the
    run that would release it. The first live teardown met that deadlock after
    `coops-model` was destroyed and its pin stayed behind.
    """
    root, make_run = prepared
    _undeclare(root, SUBJECT)
    cfg = root / "cfg" / "_config.yml"
    cfg.write_text(cfg.read_text().replace("  apply_instances: false", "  apply_instances: true"))
    # dry_run=False: the after-apply hooks, which do the forgetting, never run
    # in a dry run -- that is what the test above pins
    run = make_run(dry_run=False)
    assert run.run(["instance-image"], apply=True).ok

    pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
    params = yaml.safe_load((run.meta_state / "launch-params.yaml").read_text())
    assert SUBJECT not in pins["instances"], \
        "a destroyed instance's pin outlived it (it will block every later run)"
    assert SUBJECT not in params["instances"], "and its launch parameters with it"
    assert any(u.get("op") == "decommission" and u.get("name") == SUBJECT
               for u in pins.get("upgrades", [])), "the forgetting is recorded"


def test_forget_drops_records_that_outlived_their_instance(prepared):
    """`forget instance` is the recourse when a decommission did not clean up.

    It happened live: coops-model was destroyed through the gate and
    its pin and launch parameters stayed in the records, which -- with
    require_released_builds on -- made validate refuse every run. The
    mechanism works in this fixture (the test above), so the live failure was
    situational and remains unexplained; what was missing either way was any
    way to correct the records without editing meta-state by hand."""
    from cs_image_system.system.cli import forget_instance_command

    root, make_run = prepared
    _undeclare(root, SUBJECT)
    run = make_run()
    try:
        assert run.run(["instance-image"], apply=False).ok      # a dry run keeps them
        assert SUBJECT in yaml.safe_load((run.meta_state / "pins.yaml").read_text())["instances"]

        forget_instance_command(cli_context(run.ctx), SUBJECT)

        pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
        params = yaml.safe_load((run.meta_state / "launch-params.yaml").read_text())
        assert SUBJECT not in pins["instances"]
        assert SUBJECT not in params["instances"]
        assert any(u.get("op") == "forget" and u.get("name") == SUBJECT
                   for u in pins.get("upgrades", [])), "the correction is recorded, not silent"
    finally:
        run.restore_cwd()


def test_forget_refuses_an_instance_that_is_still_declared(prepared):
    """The way to remove a live instance is to undeclare it and let its destroy
    apply. `forget` cleans up after that; it is not a way around it."""
    import typer

    from cs_image_system.system.cli import forget_instance_command

    root, make_run = prepared
    run = make_run()
    try:
        assert run.run(["instance-image"], apply=False).ok
        with pytest.raises(typer.Exit) as ei:
            forget_instance_command(cli_context(run.ctx), SUBJECT)
        assert ei.value.exit_code == 2
        pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
        assert SUBJECT in pins["instances"], "a declared instance keeps its pin"
    finally:
        run.restore_cwd()


def test_an_overlay_can_undeclare_a_tree_entry_for_one_invocation(tmp_path: Path, monkeypatch):
    """`{name: X, undeclare: true}` removes the tree's entry for this run only:
    a launched instance decommissions through the gate exactly as if its
    entry had left the YAML; the tree on disk is untouched."""
    root = copy_config(tmp_path)
    _seed_launched(root, SUBJECT, AWS_BUILD, AWS)
    run = FixtureRun(tmp_path, monkeypatch, config_root=root,
                     overlays=[root / "overlays" / "aws-cycle-decommission.yaml"])
    try:
        assert not any(i.get_name() == SUBJECT for i in run.ctx.instances)
        assert any(i.get_name() == NEIGHBOUR for i in run.ctx.instances)        # the others stay
        summary = run.run(["instance-image"], apply=True, only=["none"])
        assert summary.ok, summary.error
        gates = _gate_lines((run.generated / RUNNER).read_text())
        assert "--allow-destroy module.instance_test2" in gates["open-tofu/instance-generation"]
        live = yaml.safe_load((root / "instances" / "instances.yaml").read_text())
        assert any(i["name"] == SUBJECT for i in live["instances"])            # the tree still declares it
    finally:
        run.restore_cwd()
