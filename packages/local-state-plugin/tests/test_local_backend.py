# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The `local` backend type (stage 47.3): its renderings, its place beside
S3 in the collision rule, and a real `tofu init` against it with no
credentials at all."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cs_image_system.hashicorp_utils.collector import BackendRegistration, StateLocation, TerraformCollector
from cs_image_system.local_state_plugin.local_state_models import LOCAL_KIND, LocalBackendKind


def test_the_kind_renders_a_relative_directory_from_the_roots_depth():
    loc = LOCAL_KIND.location({"path": "state"}, "oktagroups")
    assert loc == StateLocation(type="local", container="state", key="oktagroups.tfstate")
    assert str(loc) == "local://state/oktagroups.tfstate"
    assert LOCAL_KIND.backend_settings({"path": "state"}, "oktagroups") == {"path": "../../../../state/oktagroups.tfstate"}
    assert LOCAL_KIND.remote_state_settings({"path": "state"}, "okta-tf-users") == {"path": "../../../../state/okta_tf_users.tfstate"}
    assert LOCAL_KIND.backend_settings({"path": "."}, "ws") == {"path": "../../../../ws.tfstate"}


def test_the_kind_keeps_an_absolute_directory_and_normalises_spelling():
    assert LOCAL_KIND.backend_settings({"path": "/var/tf/state"}, "ws") == {"path": "/var/tf/state/ws.tfstate"}
    assert LocalBackendKind.directory({"path": "./state//dev/"}) == "state/dev"
    assert LocalBackendKind.directory({"path": "/"}) == "/"
    assert LocalBackendKind.directory({}) == "."
    assert LOCAL_KIND.location({"path": "state//"}, "a-b") == LOCAL_KIND.location({"path": "./state"}, "a_b")


def test_the_same_name_under_two_types_is_not_a_collision_but_two_roots_on_one_directory_are():
    from cs_image_system.tf_s3_state_plugin.tf_s3_state_models import S3_KIND
    col = TerraformCollector()
    col.reset()
    try:
        col.register_backend(BackendRegistration(
            name="s3-east2", type="s3", kind=S3_KIND, is_default=True,
            settings={"bucket": "b", "region": "us-east-2", "key_prefix": "state/", "encrypt": False,
                      "use_lockfile": True, "profile": None}))
        col.register_backend(BackendRegistration(name="local-dev", type="local", kind=LOCAL_KIND,
                                                 settings={"path": "state"}))
        col.set_backend("ws", "s3-east2")
        col.set_backend("ws-local", "local-dev")
        locations = col.state_locations()
        assert str(locations["ws"]) == "s3://b/state/ws.tfstate" and str(locations["ws-local"]) == "local://state/ws_local.tfstate"
        col.set_backend("other", "local-dev")
        col.validate_state_locations()                                   # different files: fine
        col.set_backend("ws_local", "local-dev")                         # collapses to ws_local.tfstate
        assert col.state_collisions(col.state_locations()) == [
            "workspaces ws-local, ws_local would share the state object local://state/ws_local.tfstate"]
    finally:
        col.reset()


@pytest.mark.skipif(shutil.which("tofu") is None, reason="tofu is not installed")
def test_a_real_init_against_the_local_backend_needs_no_credentials(tmp_path: Path):
    """Stage 47.6.2: what nothing in the suite could do before -- a real `tofu
    init` with an empty environment, against the file the kind renders."""
    root = tmp_path / "root"
    root.mkdir()
    state_dir = tmp_path / "state"
    (root / "main.tf").write_text('terraform {\n  backend "local" {}\n}\n')
    lines = TerraformCollector().render_backend_config(
        LOCAL_KIND.backend_settings({"path": str(state_dir)}, "ws"),
        "# Backend 'local-dev' (local) partial configuration for workspace ws")
    (root / "ws.tfbackend.hcl").write_text("\n".join(lines) + "\n")
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "TF_IN_AUTOMATION": "1"}
    assert not any(k.startswith(("AWS_", "GOOGLE_", "OKTA_")) for k in env)
    init = subprocess.run(["tofu", "init", "-input=false", "-backend-config=ws.tfbackend.hcl"],
                          cwd=root, env=env, capture_output=True, text=True)
    assert init.returncode == 0, init.stdout + init.stderr
    record = json.loads((root / ".terraform" / "terraform.tfstate").read_text())
    assert record["backend"]["type"] == "local"
    assert record["backend"]["config"]["path"] == f"{state_dir}/ws.tfstate"
    pull = subprocess.run(["tofu", "state", "pull"], cwd=root, env=env, capture_output=True, text=True)
    assert pull.returncode == 0 and pull.stdout.strip() == ""            # an empty location
