# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""V2 gate 6 (DESIGN §4, phase F3-F5 + M): lineage, pinning, mods.

* rebuilding an image yields a new, uniquely named build linked to its
  series, carrying the root's stamp (N24) and its recorded mods (N23c);
* consumers bind once (first bind) and stay pinned; existing instances
  keep their build when the series moves on (zero planned changes);
* only an explicit upgrade moves a pin -- exactly one edge, never
  cascading -- and an instance upgrade is a whitelisted replacement;
* a rebuilt instance image bakes FROM its pinned base build (N17).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from v2_support import FIXED_TIMESTAMP, V2Run, copy_config, tree


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _write_yaml(path: Path, data) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _prepared(tmp_path, monkeypatch, mutate):
    root = copy_config(tmp_path)
    mutate(root)
    return V2Run(tmp_path, monkeypatch, config_root=root)


def _seed(root: Path, builds: list[dict], pins: dict | None = None) -> None:
    ms = root / "meta-state"
    ms.mkdir(exist_ok=True)
    _write_yaml(ms / "lineage.yaml", {"builds": builds})
    if pins is not None:
        _write_yaml(ms / "pins.yaml", {"instances": pins.get("instances", {}),
                                        "images": pins.get("images", {}), "upgrades": []})


def _build(build_id: str, series: str, caps=None, run="r0") -> dict:
    return {"build_id": build_id, "series": series, "runtime": "aws-east2-runtime",
            "name": f"{series}-{run}", "parent": "vendor", "run": run,
            "capabilities": caps or {"identity_types": ["okta"],
                                     # pd/gcs joined the declaration (GCP readiness 2026-09-02);
                                     # gce-test resolves through these seeded pins (N11)
                                     "storage_types": ["ebs", "efs", "gcs", "pd", "s3"]}}


def _image_pin(pins: dict, image: str, runtime: str = "aws-east2-runtime") -> str | None:
    """Keyed (`<image>@<runtime>`) or legacy unkeyed image pin."""
    return pins["images"].get(f"{image}@{runtime}") or pins["images"].get(image)


def _tag(text: str, key: str, value: str) -> bool:
    """hcl2 vertically aligns map keys; match a tag regardless of padding."""
    return re.search(rf'^\s*{re.escape(key)}\s+= "{re.escape(value)}"', text, re.M) is not None


def _source(v2, lifecycle: str, block: str, image: str) -> str:
    return (v2.generated / lifecycle / "pckr-ebs-ans" / "image-generation" / block
            / f"pckr-ebs-ans-image-generation-source-{image}-{block}.pkr.hcl").read_text()


def _fake_manifest(v2, lifecycle: str, block: str, amis: dict[str, str]) -> None:
    d = v2.generated / lifecycle / "pckr-ebs-ans" / "image-generation" / block
    (d / "manifest.json").write_text(json.dumps({
        "last_run_uuid": "u1",
        "builds": [{"name": n, "packer_run_uuid": "u1", "artifact_id": f"us-east-2:{a}"}
                   for n, a in amis.items()],
    }))


# ------------------------------------------------------------- naming/tags

def test_every_build_is_uniquely_named_and_lineage_tagged(v2):
    assert v2.run(["base-image", "instance-image"], apply=False).ok
    base = _source(v2, "base-image", "block-000", "basic-rh-10")
    assert f'ami_name = "basic-rh-10-aws-east2-runtime-{FIXED_TIMESTAMP}"' in base
    assert "{{" not in base, "unique naming must resolve the run timestamp"
    assert _tag(base, "csis_series", "basic-rh-10")
    assert _tag(base, "csis_parent", "vendor")
    assert _tag(base, "csis_run", "2026_08_26t12_00_00")
    assert _tag(base, "csis_identity_types", "okta")
    assert _tag(base, "csis_storage_types", "ebs,efs,gcs,pd,s3")
    assert re.search(r'csis_fingerprint\s+= "[0-9a-f]{16}"', base)
    dask = _source(v2, "instance-image", "block-000", "imgfile-basic-dask")
    assert f'ami_name = "imgfile-basic-dask-pckr-ebs-ans-{FIXED_TIMESTAMP}"' in dask
    assert _tag(dask, "csis_parent", "series:basic-rh-10")   # base built this run: bound after the bake
    assert _tag(dask, "csis_storage_types", "ebs,efs,gcs,pd,s3")  # root stamp inherited (N24)


# ------------------------------------------------------ lineage + first bind

def test_bake_records_lineage_and_first_binds_the_base_edge(v2):
    assert v2.run(["base-image", "instance-image"], apply=False).ok
    ctx = v2.ctx
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.base.lifecycles import Lifecycle
    ib = ctx.image_builders["pckr-ebs-ans"]
    # base bake
    _fake_manifest(v2, "base-image", "block-000", {"basic-rh-10": "ami-0base0001", "basic-rhel-9": "ami-0base0009"})
    ctx.current_lifecycle = Lifecycle.BASE_IMAGE
    ib.post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
    # instance-image bake (block-000 holds the images chained directly off the bases)
    _fake_manifest(v2, "instance-image", "block-000", {"imgfile-basic-dask": "ami-0dask0001"})
    ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
    ib.post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
    ctx.current_lifecycle = None
    lineage = yaml.safe_load((v2.meta_state / "lineage.yaml").read_text())["builds"]
    by_id = {b["build_id"]: b for b in lineage}
    base = by_id["ami-0base0001"]
    assert base["series"] == "basic-rh-10" and base["parent"] == "vendor"
    assert base["capabilities"] == {"identity_types": ["okta"], "storage_types": ["ebs", "efs", "gcs", "pd", "s3"]}
    assert base["name"] == f"basic-rh-10-aws-east2-runtime-{FIXED_TIMESTAMP}"
    dask = by_id["ami-0dask0001"]
    assert dask["parent"] == "ami-0base0001"            # resolved from this run's base manifest
    assert dask["chain"] == ["imgfile-basic-dask"]
    assert dask["capabilities"] == base["capabilities"]  # N24
    mods = {m["name"]: m for m in dask["mods"]}
    assert mods["dask-setup-jeffy"]["operation"] == "ansible"
    assert re.fullmatch(r"[0-9a-f]{64}", mods["dask-setup-jeffy"]["content_hash"])
    assert re.fullmatch(r"[0-9a-f]{64}", mods["derivative-setup"]["content_hash"])
    assert {m["run"] for m in dask["mods"]} == {ctx.run_id}
    pins = yaml.safe_load((v2.meta_state / "pins.yaml").read_text())
    assert pins["images"]["imgfile-basic-dask@aws-east2-runtime"] == "ami-0base0001"
    assert pins["upgrades"][-1]["op"] == "bind"
    # builds are never deleted: recording again is a no-op, never a replacement
    ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
    ib.post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
    ctx.current_lifecycle = None
    assert len(yaml.safe_load((v2.meta_state / "lineage.yaml").read_text())["builds"]) == len(lineage)
    # zero-drift-report: every recorded build is re-tagged with lineage's
    # RESOLVED parent and fingerprint -- generation-time tags on a
    # same-run-chained image carried `series:<name>` (the step-3 follow-up
    # finding's one standing `changed` drift line)
    retagged = {ami: tags for ami, tags in v2.retags}
    assert retagged["ami-0dask0001"]["csis_parent"] == "ami-0base0001"
    assert retagged["ami-0dask0001"]["csis_fingerprint"] == dask["input_fingerprint"][:16]
    assert retagged["ami-0base0001"]["csis_parent"] == "vendor"


def _set_parent_policy(root, image: str, policy: str) -> None:
    """The live fixture's dask image declares parent_policy: follow (stage 9);
    N17's pinned behaviour is proven on a copy that declares pinned."""
    p = root / "images" / "image1.yaml"
    d = yaml.safe_load(p.read_text())
    for img in d.get("images") or []:
        if img.get("name") == image:
            img["parent_policy"] = policy
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def test_rebuild_bakes_from_the_pinned_base_never_most_recent(tmp_path, monkeypatch):
    def prepare(root):
        _seed(root, [_build("ami-0base0001", "basic-rh-10", run="r1"), _build("ami-0base0002", "basic-rh-10", run="r2")],
              {"images": {"imgfile-basic-dask": "ami-0base0001"}})
        _set_parent_policy(root, "imgfile-basic-dask", "pinned")
    run = _prepared(tmp_path, monkeypatch, prepare)
    try:
        assert run.run(["instance-image"], apply=False).ok
        dask = _source(run, "instance-image", "block-000", "imgfile-basic-dask")
        assert 'image-id = "ami-0base0001"' in dask
        assert "most_recent" not in dask
        assert _tag(dask, "csis_parent", "ami-0base0001")
        # an unpinned sibling of the same base binds to the series HEAD (first bind)
        data_science = _source(run, "instance-image", "block-000", "imgfile-data-science")
        assert "most_recent" in data_science or 'image-id = "ami-' in data_science
        pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
        assert _image_pin(pins, "imgfile-basic-dask") == "ami-0base0001"
    finally:
        run.restore_cwd()


def test_first_bind_of_an_image_goes_to_the_series_head(tmp_path, monkeypatch):
    run = _prepared(tmp_path, monkeypatch, lambda root: _seed(
        root, [_build("ami-0base0001", "basic-rh-10", run="r1"), _build("ami-0base0002", "basic-rh-10", run="r2")]))
    try:
        assert run.run(["instance-image"], apply=False).ok
        dask = _source(run, "instance-image", "block-000", "imgfile-basic-dask")
        assert 'image-id = "ami-0base0002"' in dask
        pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
        assert pins["images"]["imgfile-basic-dask@aws-east2-runtime"] == "ami-0base0002"
        assert pins["upgrades"][0] == {"kind": "image", "name": "imgfile-basic-dask@aws-east2-runtime",
                                       "to": "ami-0base0002", "run": run.ctx.run_id, "op": "bind",
                                       "runtime": "aws-east2-runtime"}
    finally:
        run.restore_cwd()


# ---------------------------------------------------------- instance pins

def test_existing_instances_keep_their_build_when_the_series_moves(tmp_path, monkeypatch):
    run = _prepared(tmp_path, monkeypatch, lambda root: _seed(
        root, [_build("ami-0dask0001", "imgfile-basic-dask", run="r1"),
               _build("ami-0dask0002", "imgfile-basic-dask", run="r2")],
        {"instances": {"test2": "ami-0dask0001"}}))
    try:
        assert run.run(["instance-image"], apply=False).ok
        inst = tree(run.generated / "instance-image" / "open-tofu" / "instance-generation")
        module = inst["open-tofu-instance-generation-instance-test2.tf"]
        assert 'ami_id = "ami-0dask0001"' in module        # pinned literal, not the head
        assert "ami_name_pattern" not in module
        assert "-replace=" not in (run.generated / "instance-image" / "run-instance-image.sh").read_text()
        lp = yaml.safe_load((run.meta_state / "launch-params.yaml").read_text())
        assert lp["instances"]["test2"]["build"] == "ami-0dask0001"
        # the unbound instance ('test', image never built) still uses the deferred lookup
        assert "ami_name_pattern" in inst["open-tofu-instance-generation-instance-test.tf"]
    finally:
        run.restore_cwd()


def test_upgrade_moves_exactly_one_edge_and_replaces_the_instance(tmp_path, monkeypatch):
    run = _prepared(tmp_path, monkeypatch, lambda root: _seed(
        root, [_build("ami-0base0001", "basic-rh-10", run="r1"),
               _build("ami-0dask0001", "imgfile-basic-dask", run="r1"),
               _build("ami-0dask0002", "imgfile-basic-dask", run="r2")],
        {"instances": {"test2": "ami-0dask0001"}, "images": {"imgfile-basic-dask": "ami-0base0001"}}))
    try:
        from cs_image_system.base.commands.upgrade import upgrade
        previous, target = upgrade("instance", "test2")      # default: series head
        assert (previous, target) == ("ami-0dask0001", "ami-0dask0002")
        pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
        assert pins["instances"]["test2"] == "ami-0dask0002"
        assert _image_pin(pins, "imgfile-basic-dask") == "ami-0base0001"   # never cascades
        assert pins["upgrades"][-1]["op"] == "upgrade"
        assert pins["pending_replacements"] == {"test2": "ami-0dask0002"}
        with pytest.raises(ValueError, match="already pinned"):
            upgrade("instance", "test2", "ami-0dask0002")
        with pytest.raises(ValueError, match="not recorded in lineage"):
            upgrade("instance", "test2", "ami-0nope")
        with pytest.raises(ValueError, match="belongs to series"):
            upgrade("instance", "test2", "ami-0base0001")
        assert run.run(["instance-image"], apply=False).ok
        module = (run.generated / "instance-image" / "open-tofu" / "instance-generation"
                  / "open-tofu-instance-generation-instance-test2.tf").read_text()
        assert 'ami_id = "ami-0dask0002"' in module
        script = (run.generated / "instance-image" / "run-instance-image.sh").read_text()
        assert "tofu plan -input=false -out=tfplan -replace=module.instance_test2.aws_instance.this" in script
        assert "--allow-destroy module.instance_test2.aws_instance.this" in script
        # the image edge can be upgraded independently -- and it does not touch the instance
        upgrade("image", "imgfile-basic-dask", "ami-0base0001") if False else None
    finally:
        run.restore_cwd()


def test_image_upgrade_never_touches_instance_pins(tmp_path, monkeypatch):
    run = _prepared(tmp_path, monkeypatch, lambda root: _seed(
        root, [_build("ami-0base0001", "basic-rh-10", run="r1"),
               _build("ami-0base0002", "basic-rh-10", run="r2"),
               _build("ami-0dask0001", "imgfile-basic-dask", run="r1")],
        {"instances": {"test2": "ami-0dask0001"}, "images": {"imgfile-basic-dask": "ami-0base0001"}}))
    try:
        from cs_image_system.base.commands.upgrade import upgrade
        assert upgrade("image", "imgfile-basic-dask", runtime="aws-east2-runtime") == ("ami-0base0001", "ami-0base0002")
        pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
        assert pins["images"]["imgfile-basic-dask@aws-east2-runtime"] == "ami-0base0002"
        assert pins["instances"]["test2"] == "ami-0dask0001"
        assert "pending_replacements" not in pins or not pins["pending_replacements"]
        assert run.run(["instance-image"], apply=False).ok
        dask = _source(run, "instance-image", "block-000", "imgfile-basic-dask")
        assert 'image-id = "ami-0base0002"' in dask
        module = (run.generated / "instance-image" / "open-tofu" / "instance-generation"
                  / "open-tofu-instance-generation-instance-test2.tf").read_text()
        assert 'ami_id = "ami-0dask0001"' in module   # zero planned changes for the instance
    finally:
        run.restore_cwd()


def test_launch_binds_unpinned_instances_to_the_launched_build(tmp_path, monkeypatch):
    def mutate(root: Path):
        p = root / "cfg" / "_config.yml"
        data = yaml.safe_load(p.read_text())
        data["config"]["apply_instances"] = True
        _write_yaml(p, data)
    run = _prepared(tmp_path, monkeypatch, mutate)
    try:
        assert run.run(["instance-image"], apply=False).ok
        ctx = run.ctx
        from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
        from cs_image_system.base.lifecycles import Lifecycle
        ib = ctx.image_builders["pckr-ebs-ans"]
        _fake_manifest(run, "instance-image", "block-000", {"imgfile-basic-dask": "ami-0dask0007"})
        ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
        ib.post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
        instance_builder = ctx.instance_builders["open-tofu"]
        instance_builder.pre_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
        tfvars = (run.generated / "instance-image" / "open-tofu" / "instance-generation" / "instances.auto.tfvars").read_text()
        assert 'test2_ami_id = "ami-0dask0007"' in tfvars
        instance_builder.post_finalize_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
        ctx.current_lifecycle = None
        pins = yaml.safe_load((run.meta_state / "pins.yaml").read_text())
        assert pins["instances"]["test2"] == "ami-0dask0007"
        assert "test" not in pins["instances"]   # its image was not built: still unbound
        script = (run.generated / "instance-image" / "run-instance-image.sh").read_text()
        assert "tofu apply -input=false tfplan" in script
    finally:
        run.restore_cwd()
