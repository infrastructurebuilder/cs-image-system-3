# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The proof of the starter: ``docs/examples/standard-docker``
AS IT STANDS (only an overlay that lets the storage and instance roots apply)
goes from nothing to nothing on the local daemon. The runtime names no
address, so the caller's environment's daemon is used, which is how a team
tries the starter on a laptop. One real run bakes the base and the instance
image, makes the volume and stands the container; the accounts and the group
are there, the volume is mounted, the instance verifies, the strict state
query agrees; the instance is undeclared and destroyed, the volume destroyed,
the builds disposed.

A leg of ``just full-test`` (``just test-docker-cycle``); under ``just test``
the file is skipped. It refuses to run on a daemon that already holds a
container or volume the starter would use, rather than risk removing someone's."""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest
import yaml
from harness import docker_binary, load_context, reset_singletons
from test_docker_bake_live import _docker_answers, require_engine_for_leg
from test_docker_cycle_live import _cli, _exec, _inspect, _standing, _tail
from test_docs_examples import copy_example

DOCKER = docker_binary()
PACKER = shutil.which("packer")
ANSIBLE = shutil.which("ansible-playbook")
TOFU = shutil.which("tofu")
INSTANCE, VOLUME, RUNTIME, REPOSITORY = "team-node-1", "data", "docker-main", "csis/standard-docker"

_WANTED = os.environ.get("CSIS_DOCKER_CYCLE") == "1"
pytestmark = [
    pytest.mark.skipif(not _WANTED, reason="docker cycle leg: run by `just test-docker-cycle` (a leg of `just full-test`)"),
    pytest.mark.skipif(_WANTED and not _docker_answers(), reason="docker is not answering (is its daemon running?)"),
    pytest.mark.skipif(_WANTED and not PACKER, reason="packer is not on PATH"),
    pytest.mark.skipif(_WANTED and not ANSIBLE, reason="ansible-playbook is not on PATH"),
    pytest.mark.skipif(_WANTED and not TOFU, reason="tofu is not on PATH"),
]


def _taken() -> list[str]:
    """What the starter would use that already stands on this daemon."""
    out = []
    if _inspect(INSTANCE) is not None:
        out.append(f"a container named {INSTANCE}")
    if subprocess.run([DOCKER, "volume", "inspect", VOLUME], capture_output=True).returncode == 0:
        out.append(f"a volume named {VOLUME}")
    ls = subprocess.run([DOCKER, "images", "-q", REPOSITORY], capture_output=True, text=True)
    if ls.stdout.strip():
        out.append(f"images of {REPOSITORY}")
    return out


def test_the_docker_starter_goes_from_nothing_to_nothing_as_it_stands(tmp_path, monkeypatch):
    require_engine_for_leg()
    taken = _taken()
    if taken:
        pytest.skip("this daemon already holds " + ", ".join(taken) + ": the leg would not know what is its own")
    root = copy_example(tmp_path, "standard-docker")
    (root / "overlays" / "leg.yaml").write_text(yaml.safe_dump({"config": {"apply_storage": True, "apply_instances": True}}))
    (root / "overlays" / "leg-destroy.yaml").write_text(yaml.safe_dump({"storages": [{
        "name": VOLUME, "groups": ["team"], "share_mode": "2770", "state": "destroyed"}]}))
    env = dict(os.environ)
    env["CSIS_CONFIG_IDENTITY"] = str(root / ".age-identity")
    env.setdefault("USER", "leg")
    if os.environ.get("CSIS_DOCKER_KEEP_HOST") != "1":     # the Podman leg names the daemon it is aimed at (test-podman-cycle)
        env.pop("DOCKER_HOST", None)                  # the runtime names no address: the environment's daemon
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", env["CSIS_CONFIG_IDENTITY"])
    leg = ("--overlay", "overlays/leg.yaml")
    try:
        # 1. a dry run first, as always
        dry = _cli(root, *leg, "--dry-run", "run", "storage", "base-image", "instance-image", env=env, timeout=1800)
        assert dry.returncode == 0, _tail(dry)
        # 2. the real run: the volume, the two bakes, the container, the launch script by exec
        res = _cli(root, *leg, "--no-dry-run", "run", "storage", "base-image", "instance-image", env=env)
        assert res.returncode == 0, _tail(res)
        reset_singletons()
        ctx = load_context(root, dry_run=True, overlays=[root / "overlays" / "leg.yaml"])
        builds = {str(b["series"]): b for b in ctx.meta_state.builds() if b.get("runtime") == RUNTIME}
        assert set(builds) == {"el10", "team-node"}, builds
        info = _standing(INSTANCE)
        assert info["State"]["Status"] == "running" and info["Image"] == str(builds["team-node"]["build_id"])
        assert info["Config"]["Hostname"] == f"{INSTANCE}-001"
        assert info["HostConfig"]["NanoCpus"] == 1_000_000_000 and info["HostConfig"]["Memory"] == 1024 * 1024 * 1024   # `small`
        mounts = [m for m in info["Mounts"] if m["Destination"] == "/mnt/data"]
        assert mounts and mounts[0]["Name"] == VOLUME, info["Mounts"]
        # 3. the accounts and the group the launch script made, the image's own tests' effects
        rc, out = _exec(INSTANCE, "getent group team | cut -d: -f3; id -u avery_alpha; id -u casey_charlie; "
                                  "stat -c '%G %a' /mnt/data/team; grep -rl avery_alpha /etc/sudoers.d | wc -l; "
                                  "cat /etc/team-node.conf; python3 --version")
        assert rc == 0, out
        lines = [ln.strip() for ln in out.strip().splitlines()]
        assert lines[:4] == ["3000", "3001", "3002", "team 2770"], out
        assert int(lines[4]) >= 1 and lines[5] == "role=worker" and lines[6].startswith("Python 3"), out
        # 4. the verification and the strict state query
        ver = _cli(root, *leg, "--no-dry-run", "verify", "instance", INSTANCE, env=env, timeout=900)
        assert ver.returncode == 0, _tail(ver)
        query = _cli(root, *leg, "state", "query", "--strict", env=env, timeout=600)
        assert query.returncode == 0, _tail(query)
        # 5. the instance undeclared for this invocation: destroyed through the gate
        res = _cli(root, *leg, "--no-dry-run", "--undeclare", f"instance:{INSTANCE}", "run", "instance-image", env=env)
        assert res.returncode == 0, _tail(res)
        assert _inspect(INSTANCE) is None
        # 6. the volume, requested destroyed
        destroy = ("--overlay", "overlays/leg.yaml", "--overlay", "overlays/leg-destroy.yaml")
        res = _cli(root, *destroy, "--no-dry-run", "--undeclare", f"instance:{INSTANCE}", "run", "storage", env=env)
        assert res.returncode == 0, _tail(res)
        assert subprocess.run([DOCKER, "volume", "inspect", VOLUME], capture_output=True).returncode != 0
        # 7. the builds, disposed through the runtime, the child first
        reset_singletons()
        ctx = load_context(root, dry_run=True, overlays=[root / "overlays" / "leg.yaml"])
        rtb = ctx.runtime_builders[RUNTIME]
        for bid in (str(builds["team-node"]["build_id"]), str(builds["el10"]["build_id"])):
            assert rtb.dispose_image(bid) is True
    finally:
        subprocess.run([DOCKER, "rm", "--force", INSTANCE], capture_output=True)
        subprocess.run([DOCKER, "volume", "rm", "--force", VOLUME], capture_output=True)
        ls = subprocess.run([DOCKER, "images", "--format", "{{.ID}}", REPOSITORY], capture_output=True, text=True)
        for iid in {ln.strip() for ln in (ls.stdout or "").splitlines() if ln.strip()}:
            subprocess.run([DOCKER, "image", "rm", "--force", iid], capture_output=True)
        ps = subprocess.run([DOCKER, "ps", "-aq", "--filter", f"name=csis-bake-{RUNTIME}-"], capture_output=True, text=True)
        for cid in (ps.stdout or "").split():
            subprocess.run([DOCKER, "rm", "--force", cid], capture_output=True)
