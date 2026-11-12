# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A tree whose storage and instance roots are this plugin's alone: the
fixture's GCP storage builders (`tf-gcp-pd`, `tf-gcp-gcs`) and its
`tofu-gce` instance builder kept, every other storage and instance root
gone. A dry `run --all` emits the two storage roots and
the instance root with the google provider, the plugin's module calls and
the remote-state read of the disk the instance mounts."""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from harness import V2Run, copy_config

GCE_RUNTIME = "gcloud-east1"
GCE_INSTANCE = "gce-test"


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def gcp_only_roots(root: Path) -> tuple[list[str], list[str]]:
    """Only the GCP storage builders, the GCE instance builder, the GCP
    storages and the GCE instance; returns (storage builders, storages)."""
    builders: list[str] = []

    def prune_storage_builders(d):
        d["storage_builders"] = [b for b in d["storage_builders"] if b["type"].startswith("tf-gcp-")]
        d["storage_builders"][0]["is_default"] = True         # a classification's list names a default
        builders.extend(b["name"] for b in d["storage_builders"])
    _edit(root / "cfg" / "storage-builders.yml", prune_storage_builders)

    def prune_instance_builders(d):
        d["instance_builders"] = [b for b in d["instance_builders"] if b["type"] == "tofu-gce"]
        d["instance_builders"][0]["is_default"] = True
    _edit(root / "cfg" / "instance-builders.yml", prune_instance_builders)
    storages: list[str] = []
    for p in sorted((root / "storages").glob("*.y*ml")):
        doc = yaml.safe_load(p.read_text())
        kept = [s for s in doc["storages"] if s.get("type") in builders]
        if kept:
            storages.extend(s["name"] for s in kept)
            p.write_text(yaml.safe_dump({"storages": kept}, sort_keys=False))
        else:
            p.unlink()
    for p in sorted((root / "instances").glob("*.y*ml")):
        doc = yaml.safe_load(p.read_text())
        kept = [i for i in doc["instances"] if i.get("runtime") == GCE_RUNTIME]
        if kept:
            p.write_text(yaml.safe_dump({"instances": kept}, sort_keys=False))
        else:
            p.unlink()
    shutil.rmtree(root / "overlays", ignore_errors=True)

    def gcp_storage_types(d):               # a base declares the storage types its instances may attach: these alone
        for base in d["os_builders"]:
            base["storage_types"] = ["pd", "gcs"]
    _edit(root / "cfg" / "os-builders.yml", gcp_storage_types)
    return builders, storages


def test_a_dry_run_over_the_gcp_roots_alone_emits_them_with_the_plugins_modules(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    builders, storages = gcp_only_roots(root)
    assert sorted(builders) == ["gcp-gcs", "gcp-pd"] and sorted(storages) == ["gce_bucket", "gce_data"]
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert set(run.ctx.storage_builders) == set(builders)
        assert set(run.ctx.instance_builders) == {"tofu-gce"}
        assert [i.get_name() for i in run.ctx.instances] == [GCE_INSTANCE]
        summary = run.run("all")
        assert summary.ok, summary.error
        roots = sorted(p.name for p in (run.generated / "storage").iterdir() if p.is_dir() and p.name != "temp_assets")
        assert roots == sorted(builders), roots
        pd = "\n".join(p.read_text() for p in (run.generated / "storage" / "gcp-pd").rglob("*.tf"))
        gcs = "\n".join(p.read_text() for p in (run.generated / "storage" / "gcp-gcs").rglob("*.tf"))
        assert 'provider "google"' in pd and 'module "storage_gce_data"' in pd and "tfmodules/gcp_storage_pd" in pd
        assert 'provider "google"' in gcs and 'module "storage_gce_bucket"' in gcs and "tfmodules/gcp_storage_gcs" in gcs
        # the instance roots are the instance builders' directories (the image builders' bakes sit beside them)
        inst_roots = sorted(p.name for p in (run.generated / "instance-image").iterdir()
                            if p.is_dir() and p.name not in set(run.ctx.image_builders) | {"temp_assets"})
        assert inst_roots == ["tofu-gce"], inst_roots
        inst = "\n".join(p.read_text() for p in (run.generated / "instance-image" / "tofu-gce").rglob("*.tf"))
        assert 'module "instance_gce_test"' in inst and "tfmodules/gce_instance" in inst
        assert 'data "terraform_remote_state" "gcp_pd"' in inst, "the instance root does not read the disk's state"
        assert 'data "terraform_remote_state" "aws_ebs"' not in inst
        assert "hashicorp/aws" not in pd + gcs + inst
    finally:
        run.restore_cwd()
