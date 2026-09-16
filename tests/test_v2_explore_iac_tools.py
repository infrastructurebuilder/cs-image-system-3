# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""EXPLORE "Possible Other Infra-as-Code tools" (investigation): the
launch-parameter ansible emitter says the same things as the cloud-init
user-data template, task for task."""
from __future__ import annotations

import yaml

from tests.v2_support import V2Run

from cs_image_system.base import ansible_launch, launch_params
from cs_image_system.base.lifecycles import Lifecycle


def _params(run: V2Run) -> dict[str, dict]:
    ctx = run.ctx
    return {i.get_name(): launch_params.compute_launch_params(ctx, i) for i in ctx.instances}


def test_playbook_mirrors_user_data(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        summary = run.run(["identity", "storage", "base-image", "instance-image"], apply=False)
        assert summary.ok, summary.error
        params = _params(run)
        assert params
        for name, p in params.items():
            ud = launch_params.user_data_template(p)
            play = yaml.safe_load(ansible_launch.launch_playbook(p))[0]
            assert play["hosts"] == name and play["become"] is True
            names = " ".join(t["name"] for t in play["tasks"])
            for m in p["mounts"]:
                # every mount decision appears in both renderings
                assert m["mount_point"] in ud and m["mount_point"] in names
                if m["type"] == "ebs":
                    assert m["device"] in ud and m["device"] in names
                    if p["group"]:
                        assert f"{m['mount_point']}/{p['group']}" in ud
                        sub = next(t for t in play["tasks"] if t["name"].startswith("private subtree"))
                        assert sub["ansible.builtin.file"]["group"] == "{{ group_gid }}"
                if m["type"] == "efs":
                    assert "access_point_id" in ud and any("access_point_id" in str(t) for t in play["tasks"])
            if (p.get("enrollment") or {}).get("enrollment") == "sftd-token":
                assert "enrollment.token" in ud
                tok = next(t for t in play["tasks"] if "enrollment token" in t["name"])
                assert tok["no_log"] is True and "sft_enrollment_token" in tok["ansible.builtin.copy"]["content"]
            # runtime values by reference only (extra-vars), never literals
            text = ansible_launch.launch_playbook(p)
            if p["group"] and any(m["type"] == "ebs" for m in p["mounts"]):
                assert "{{ group_gid }}" in text
            if (p.get("enrollment") or {}).get("enrollment") == "sftd-token":
                assert "{{ sft_enrollment_token }}" in text
            assert not any(v.isdigit() and len(v) >= 5 for v in text.replace("'", " ").split())
    finally:
        run.restore_cwd()


def test_inventory_groups_by_owner_and_identity_type(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        params = _params(run)
        inv = yaml.safe_load(ansible_launch.launch_inventory(params))
        assert set(inv["all"]["hosts"]) == set(params)
        for name, p in params.items():
            if p.get("group"):
                assert name in inv["all"]["children"][f"csis_{p['group']}"]["hosts"]
            if p.get("identity_type"):
                assert name in inv["all"]["children"][f"csis_{p['identity_type']}"]["hosts"]
    finally:
        run.restore_cwd()


def test_launch_params_are_unchanged_by_the_emitter(tmp_path, monkeypatch):
    """The emitter is a pure rendering: meta-state launch params are what
    the instance lifecycle recorded, byte for byte."""
    run = V2Run(tmp_path, monkeypatch)
    try:
        summary = run.run(["identity", "storage", "base-image", "instance-image"], apply=False)
        assert summary.ok, summary.error
        before = (run.meta_state / "launch-params.yaml").read_text()
        for p in _params(run).values():
            ansible_launch.launch_playbook(p)
        assert (run.meta_state / "launch-params.yaml").read_text() == before
        assert Lifecycle.INSTANCE_IMAGE in run.ctx.generated_lifecycles
    finally:
        run.restore_cwd()
