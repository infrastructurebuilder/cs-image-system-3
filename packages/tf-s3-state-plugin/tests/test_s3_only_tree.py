# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A tree whose state backends are all this plugin's `s3` (stage 128,
item 6): the fixture's local backend gone and its roots moved to the
default bucket, a dry `run --all` puts every root's state in a bucket, each
backend file carrying the bucket, the key under the declared prefix, the
region, the profile and the lockfile. Over a copy of the frozen fixture."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from cs_image_system.contract.names import super_safe_name
from cs_image_system.tf_s3_state_plugin.tf_s3_state_models import S3_KIND
from harness import V2Run, copy_config

LOCAL = "local-dev"


def s3_only(root: Path) -> dict[str, dict]:
    """Every non-s3 backend removed; the roots that named one moved to the
    default s3 backend. Returns the s3 backends by name."""
    cfg = root / "cfg"
    backends: dict[str, dict] = {}
    for p in sorted(cfg.glob("*.yml")):          # every file that declares backends (state-backends*.yml, state-gcm.yml)
        doc = yaml.safe_load(p.read_text()) or {}
        if "state_backends" not in doc:
            continue
        entries = [e for e in doc.get("state_backends") or [] if e.get("type") == "s3"]
        if entries:
            backends.update({e["name"]: e for e in entries})
            p.write_text(yaml.safe_dump({"state_backends": entries}, sort_keys=False))
        else:
            p.unlink()
    default = next(e["name"] for e in backends.values() if e.get("is_default"))
    for p in cfg.glob("*.yml"):
        text = p.read_text()
        rewritten = re.sub(rf"^(\s+state_configuration:) {LOCAL}\b", rf"\1 {default}", text, flags=re.M)
        if rewritten != text:
            p.write_text(rewritten)
    return backends


def test_the_kind_renders_the_key_under_the_prefix():
    settings = {"bucket": "b", "region": "us-east-2", "key_prefix": "statefiles/x/", "encrypt": True,
                "use_lockfile": True, "profile": "noaa"}
    assert str(S3_KIND.location(settings, "aws-ebs")) == "s3://b/statefiles/x/aws_ebs.tfstate"
    backend = S3_KIND.backend_settings(settings, "aws-ebs")
    assert backend["bucket"] == "b" and backend["key"] == "statefiles/x/aws_ebs.tfstate" and backend["region"] == "us-east-2"


def test_a_dry_run_over_an_s3_only_tree_puts_every_root_in_a_bucket(tmp_path, monkeypatch):
    from cs_image_system.hashicorp_utils.collector import terraform_collector
    root = copy_config(tmp_path)
    backends = s3_only(root)
    assert len(backends) >= 2, backends
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert set(run.ctx.state_backends) == set(backends)
        summary = run.run("all")
        assert summary.ok, summary.error
        backend_files = sorted(run.generated.rglob("*.tfbackend.hcl"))
        assert len(backend_files) >= 8, [str(p.relative_to(run.generated)) for p in backend_files]
        buckets = {e["bucket"] for e in backends.values()}
        for backend_file in backend_files:
            text = backend_file.read_text()
            bucket = re.search(r'^bucket = "([^"]+)"', text, flags=re.M)
            assert bucket and bucket.group(1) in buckets, backend_file
            workspace = backend_file.parent.parent.name            # <lifecycle>/<workspace>/<phase>/<file>
            key = re.search(r'^key = "([^"]+)"', text, flags=re.M)
            assert key and key.group(1).endswith(f"/{super_safe_name(workspace)}.tfstate"), (backend_file, key)
            assert 'region = "' in text and 'profile = "noaa"' in text and "use_lockfile = true" in text, backend_file
            assert any('backend "s3" {' in p.read_text() for p in backend_file.parent.glob("*.tf")), backend_file
        tf = "\n".join(p.read_text() for p in run.generated.rglob("*.tf"))
        assert 'backend = "local"' not in tf and 'backend = "inmem"' not in tf
        locations = terraform_collector(run.ctx).state_locations()
        assert locations and all(loc.type == "s3" for loc in locations.values()), locations
        recorded = yaml.safe_load((run.meta_state / "state-locations.yaml").read_text())["workspaces"]
        assert recorded and all(entry["type"] == "s3" and entry["backend"] in backends for entry in recorded.values()), recorded
    finally:
        run.restore_cwd()
