# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A tree whose only state backend is this plugin's `inmem`:
every root of a dry `run --all` carries the inmem backend, every
state location is in memory, and the one setting reaches every backend
file. Over a copy of the frozen fixture with its backends replaced."""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from harness import V2Run, copy_config

from cs_image_system.contract.names import super_safe_name
from cs_image_system.contract_example_plugin.models import INMEM

BACKEND = "scratch"


def inmem_only(root: Path) -> None:
    """The fixture's backends gone; one inmem backend, and every root on it."""
    cfg = root / "cfg"
    for p in cfg.glob("*.yml"):                 # every file that declares backends (state-backends*.yml, state-gcm.yml)
        if "state_backends" in (yaml.safe_load(p.read_text()) or {}):
            p.unlink()
    (cfg / "state-backends.yml").write_text(yaml.safe_dump({"state_backends": [
        {"name": BACKEND, "type": INMEM, "is_default": True, "lock_id": "proof"}]}, sort_keys=False))
    for p in cfg.glob("*.yml"):
        text = p.read_text()
        rewritten = re.sub(r"^(\s+state_configuration:) \S+", rf"\1 {BACKEND}", text, flags=re.M)
        if rewritten != text:
            p.write_text(rewritten)


def test_a_dry_run_over_an_inmem_only_tree_puts_every_root_in_memory(tmp_path, monkeypatch):
    from cs_image_system.hashicorp_utils.collector import terraform_collector
    root = copy_config(tmp_path)
    inmem_only(root)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert set(run.ctx.state_backends) == {BACKEND}
        summary = run.run("all")
        assert summary.ok, summary.error
        backend_files = sorted(run.generated.rglob("*.tfbackend.hcl"))
        assert len(backend_files) >= 8, [str(p.relative_to(run.generated)) for p in backend_files]
        for backend_file in backend_files:
            text = backend_file.read_text()
            assert f"Backend '{BACKEND}' ({INMEM})" in text and 'lock_id = "proof"' in text, backend_file
            assert any('backend "inmem" {' in p.read_text() for p in backend_file.parent.glob("*.tf")), backend_file
        tf = "\n".join(p.read_text() for p in run.generated.rglob("*.tf"))
        assert 'backend = "s3"' not in tf and 'backend = "local"' not in tf
        locations = terraform_collector(run.ctx).state_locations()
        assert locations and all(loc.type == INMEM for loc in locations.values()), locations
        assert all(str(loc) == f"inmem://memory/{super_safe_name(ws)}.tfstate" for ws, loc in locations.items())
        recorded = yaml.safe_load((run.meta_state / "state-locations.yaml").read_text())["workspaces"]
        assert recorded and all(entry["backend"] == BACKEND and entry["type"] == INMEM for entry in recorded.values()), recorded
    finally:
        run.restore_cwd()
