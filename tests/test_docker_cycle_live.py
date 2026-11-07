# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 103, branch 2, the proof: the docker runtime's CHANGE CYCLE on the
local daemon, from nothing to nothing. The bake leg's tree (one docker
runtime, written from the frozen fixture's pieces) gains a container
instance root, a volume root, one volume and two instances mounting it. In
one real run the images bake and the containers launch through OpenTofu's
``kreuzwerker/docker`` provider; the launch script arrives by exec, the
accounts are reconciled, the verification reads the marker, the mount and
the image. One container is stopped and the next apply leaves it stopped;
it is started again. One is upgraded to a new build of its image (a new
container, a new generation). Both are decommissioned, the volume is
destroyed, the builds are disposed.

A leg of ``just full-test`` (``just test-docker-cycle``); under ``just test``
the file is skipped. Needs what the bake leg needs plus tofu; several
minutes more (the bakes, the provider download, the applies)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from test_docker_bake_live import (ALMA, DEB, IMAGE, REPOSITORY, RUNTIME, _docker_answers, docker_only_tree,
                                      require_engine_for_leg)
from harness import copy_config, docker_binary, load_context, modules_beside, reset_singletons

INSTANCE_BUILDER = "tofu-leg"
VOLUME_BUILDER = "leg-volumes"
STORAGE = "leg_data"
A, B = "leg-a", "leg-b"
DOCKER = docker_binary()
PACKER = shutil.which("packer")
ANSIBLE = shutil.which("ansible-playbook")
TOFU = shutil.which("tofu")

_WANTED = os.environ.get("CSIS_DOCKER_CYCLE") == "1"
pytestmark = [
    pytest.mark.skipif(not _WANTED, reason="docker cycle leg: run by `just test-docker-cycle` (a leg of `just full-test`)"),
    pytest.mark.skipif(_WANTED and not _docker_answers(), reason="docker is not answering (is its daemon running?)"),
    pytest.mark.skipif(_WANTED and not PACKER, reason="packer is not on PATH"),
    pytest.mark.skipif(_WANTED and not ANSIBLE, reason="ansible-playbook is not on PATH"),
    pytest.mark.skipif(_WANTED and not TOFU, reason="tofu is not on PATH"),
]


def _write(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def cycle_tree(root: Path) -> None:
    """The bake leg's tree plus the instance root, the volume root, one
    volume and two instances on it; the applies enabled; the modules beside
    the root (the fixture's ``module_source_base`` is ``../tfmodules``)."""
    docker_only_tree(root)
    cfg = root / "cfg"
    exes = yaml.safe_load((cfg / "executables.yml").read_text())["executables"]
    exes.append({"name": "tofu", "binary": TOFU, "version": ">=1.6"})
    _write(cfg / "executables.yml", {"executables": exes})
    _write(cfg / "instance-builders.yml", {"instance_builders": [{
        "name": INSTANCE_BUILDER, "type": "tofu-docker", "is_default": True, "runtime": RUNTIME, "executable": "tofu",
        "state_configuration": "local-dev",
        "required_plugins": [{"name": "docker", "source": "kreuzwerker/docker", "version": ">= 3.0.0"}]}]})
    _write(cfg / "storage-builders.yml", {"storage_builders": [{
        "name": VOLUME_BUILDER, "type": "tf-docker-volume", "is_default": True, "runtime": RUNTIME, "executable": "tofu",
        "state_configuration": "local-dev", "variables": {"tags": {"Project": "stage-103-leg"}}}]})
    osbs = yaml.safe_load((cfg / "os-builders.yml").read_text())
    for e in osbs["os_builders"]:
        e["storage_types"] = ["volume"]
    _write(cfg / "os-builders.yml", osbs)
    _write(root / "storages" / "leg.yaml", {"storages": [
        {"name": STORAGE, "type": VOLUME_BUILDER, "runtime": RUNTIME, "mount_point": "/mnt/data", "groups": ["pxgroup"]}]})
    _write(root / "instances" / "leg.yaml", {"instances": [
        {"name": n, "image": IMAGE, "runtime": RUNTIME, "type": INSTANCE_BUILDER, "machine_type": "small",
         "tags": {"purpose": "leg"}, "storages": [{"name": STORAGE, "mount_point": "/mnt/data"}]} for n in (A, B)]})
    text = (cfg / "_config.yml").read_text()
    text = re.sub(r"^(  apply_(instances|storage):) \S+.*$", r"\1 true", text, flags=re.M)
    (cfg / "_config.yml").write_text(text)
    if not (root.parent / "tfmodules").exists():
        modules_beside(root)


def _cli(root: Path, *args: str, env: dict[str, str], timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "cs_image_system.system", "--root-dir", str(root), *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=str(root))


def _inspect(name: str) -> dict | None:
    res = subprocess.run([DOCKER, "container", "inspect", name], capture_output=True, text=True)
    if res.returncode != 0:
        return None
    return json.loads(res.stdout)[0]


def _standing(name: str) -> dict:
    info = _inspect(name)
    assert info is not None, f"{name} does not stand"
    return info


def _exec(name: str, script: str) -> tuple[int, str]:
    res = subprocess.run([DOCKER, "exec", "-i", "-u", "root", name, "bash", "-s"], input=script,
                         capture_output=True, text=True)
    return res.returncode, res.stdout + res.stderr


def _tail(res: subprocess.CompletedProcess[str]) -> str:
    return res.stdout[-4000:] + res.stderr[-4000:]


def test_the_docker_cycle_from_nothing_to_nothing(tmp_path, monkeypatch):
    require_engine_for_leg()
    root = copy_config(tmp_path, "leg")
    cycle_tree(root)
    env = dict(os.environ)
    env["CSIS_CONFIG_IDENTITY"] = str(root / ".age-identity")
    env.setdefault("USER", "leg")
    if os.environ.get("CSIS_DOCKER_KEEP_HOST") != "1":     # the Podman leg names the daemon it is aimed at (test-podman-cycle)
        env.pop("DOCKER_HOST", None)                  # the runtime names no address: the environment's daemon
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", env["CSIS_CONFIG_IDENTITY"])
    lifecycles = ("storage", "base-image", "instance-image")
    try:
        # 1. a dry run first, as always
        dry = _cli(root, "--dry-run", "run", *lifecycles, env=env, timeout=1800)
        assert dry.returncode == 0, _tail(dry)
        # 2. the real run: the bakes, the volume, the two containers, the launch scripts, the accounts
        res = _cli(root, "--no-dry-run", "run", *lifecycles, env=env)
        assert res.returncode == 0, _tail(res)
        reset_singletons()
        ctx = load_context(root, dry_run=True)
        ms = ctx.meta_state
        builds = {str(b["series"]): b for b in ms.builds() if b.get("runtime") == RUNTIME}
        assert set(builds) == {ALMA, DEB, IMAGE}, builds
        build_v1 = str(builds[IMAGE]["build_id"])
        for name in (A, B):
            info = _inspect(name)
            assert info is not None, f"{name} was not created"
            assert info["State"]["Status"] == "running" and info["Image"] == build_v1, info["State"]
            assert info["Config"]["Hostname"] == f"{name}-001" and info["HostConfig"]["Init"] is True
            assert info["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
            assert info["HostConfig"]["NanoCpus"] == 2_000_000_000 and info["HostConfig"]["Memory"] == 2048 * 1024 * 1024
            labels = info["Config"]["Labels"]
            assert labels["csis_config"] and labels["csis_instance"] == name and labels["csis_generation"] == "1"
            assert labels["csis_build"] == build_v1 and labels["purpose"] == "leg"
            mounts = [m for m in info["Mounts"] if m["Destination"] == "/mnt/data"]
            assert mounts and mounts[0]["Name"] == STORAGE, info["Mounts"]
            # the launch script ran by exec: the marker, the group's subtree on the volume, the accounts
            rc, out = _exec(name, "cat /var/lib/csis/launch-applied; stat -c '%G %a' /mnt/data/pxgroup; "
                                  "getent group pxgroup | cut -d: -f3; getent passwd | awk -F: '$3 >= 1000 && $3 < 60000' | wc -l")
            assert rc == 0, out
            lines = [ln.strip() for ln in out.strip().splitlines()]
            assert re.match(r"^\d{4}-\d\d-\d\dT", lines[0]), out                 # the marker is a timestamp
            assert lines[1] == "pxgroup 2770" and lines[2] == "3101", out        # the subtree, owned by the group
            assert int(lines[3]) >= 2, out                                       # the fixture's two posix personas
            launch = ms.launch_params()[name]
            assert launch["launched"] and launch["launch_delivery"] == "session" and launch["hostname"] == f"{name}-001"
            assert ms.instance_pin(name) == build_v1
            gen = ms.current_generation(name)
            assert gen and gen["number"] == 1 and gen.get("instance_id") == info["Id"], gen
        vol = subprocess.run([DOCKER, "volume", "inspect", STORAGE], capture_output=True, text=True)
        assert vol.returncode == 0 and json.loads(vol.stdout)[0]["Labels"]["csis_storage"] == STORAGE
        assert ms.storage_state(STORAGE) == "active"
        # 3. the verification, through the CLI: the marker, the mount, the image, the declared tests
        ver = _cli(root, "--no-dry-run", "verify", "instance", A, env=env, timeout=900)
        assert ver.returncode == 0, _tail(ver)
        reset_singletons()
        ctx = load_context(root, dry_run=True)
        last = [v for v in ctx.meta_state.verifications() if v["instance"] == A][-1]
        assert last["ok"] is True and {c["name"] for c in last["checks"]} >= {"launch script", "booted image", "data disks mounted"}
        # 4. the strict state query: the daemon agrees with the records
        query = _cli(root, "state", "query", "--strict", env=env, timeout=600)
        assert query.returncode == 0, _tail(query)
        # 5. the power state is the operator's: stop B, and the next apply leaves it stopped
        subprocess.run([DOCKER, "stop", B], check=True, capture_output=True)
        before = _standing(B)
        assert before["State"]["Status"] == "exited"
        rtb = ctx.runtime_builders[RUNTIME]
        assert rtb.query_instance_power_state(B) == "stopped"
        res = _cli(root, "--no-dry-run", "run", "instance-image", env=env)
        assert res.returncode == 0, _tail(res)
        after = _standing(B)
        assert after["Id"] == before["Id"] and after["State"]["Status"] == "exited", after["State"]
        # the hooks said so (rich wraps the log line, so the words may be split)
        assert re.search(r"waits\s+for\s+a\s+run\s+that\s+finds\s+it\s+running", res.stdout + res.stderr), _tail(res)
        # 6. started again, through the runtime
        assert rtb.start_instance(B) is True
        started = _inspect(B)
        assert started is not None and started["State"]["Status"] == "running" and started["Id"] == before["Id"]
        # 7. the upgrade: a changed modification makes a new build of the image; A moves to it, B stays
        images = yaml.safe_load((root / "images" / "leg.yaml").read_text())
        mods = images["images"][0]["modifications"]
        mods[0]["script"] = ["echo 'baked by a shell step, second edition' | sudo tee /etc/leg-shell"]
        _write(root / "images" / "leg.yaml", images)
        res = _cli(root, "--no-dry-run", "run", "base-image", "instance-image", env=env)
        assert res.returncode == 0, _tail(res)
        reset_singletons()
        ctx = load_context(root, dry_run=True)
        heads = [str(b["build_id"]) for b in ctx.meta_state.builds() if b.get("series") == IMAGE]
        assert len(heads) == 2 and build_v1 in heads, heads
        build_v2 = next(h for h in heads if h != build_v1)
        assert _standing(A)["Image"] == build_v1                                  # a pinned instance keeps its build
        up = _cli(root, "--no-dry-run", "upgrade", "instance", A, env=env, timeout=300)
        assert up.returncode == 0, _tail(up)
        res = _cli(root, "--no-dry-run", "run", "instance-image", env=env)
        assert res.returncode == 0, _tail(res)
        replaced = _inspect(A)
        assert replaced is not None and replaced["Image"] == build_v2 and replaced["Id"] != before["Id"]
        assert replaced["Config"]["Hostname"] == f"{A}-002" and replaced["Config"]["Labels"]["csis_generation"] == "2"
        assert replaced["State"]["Status"] == "running"
        rc, out = _exec(A, "cat /etc/leg-shell /var/lib/csis/launch-applied")
        assert rc == 0 and "second edition" in out, out                          # the new build, launched again
        reset_singletons()
        ctx = load_context(root, dry_run=True)
        ms = ctx.meta_state
        assert ms.instance_pin(A) == build_v2 and ms.instance_pin(B) == build_v1
        gen = ms.current_generation(A)
        assert gen and gen["number"] == 2 and gen.get("instance_id") == replaced["Id"], gen
        assert _standing(B)["Image"] == build_v1
        query = _cli(root, "state", "query", "--strict", env=env, timeout=600)
        assert query.returncode == 0, _tail(query)
        # 8. decommission both: the declarations go, the gate whitelists the destroys, the records close
        _write(root / "instances" / "leg.yaml", {"instances": []})
        res = _cli(root, "--no-dry-run", "run", "instance-image", env=env)
        assert res.returncode == 0, _tail(res)
        assert _inspect(A) is None and _inspect(B) is None
        reset_singletons()
        ctx = load_context(root, dry_run=True)
        assert not ctx.meta_state.launch_params() and ctx.meta_state.current_generation(A) is None
        # 9. the volume: requested destroyed, removed with its data
        _write(root / "storages" / "leg.yaml", {"storages": [
            {"name": STORAGE, "type": VOLUME_BUILDER, "runtime": RUNTIME, "mount_point": "/mnt/data",
             "groups": ["pxgroup"], "state": "destroyed"}]})
        res = _cli(root, "--no-dry-run", "run", "storage", env=env)
        assert res.returncode == 0, _tail(res)
        assert subprocess.run([DOCKER, "volume", "inspect", STORAGE], capture_output=True).returncode != 0
        reset_singletons()
        ctx = load_context(root, dry_run=True)
        assert ctx.meta_state.storage_state(STORAGE) == "destroyed"
        # 10. the builds, disposed through the runtime: the children first
        rtb = ctx.runtime_builders[RUNTIME]
        for bid in (build_v2, build_v1, str(builds[DEB]["build_id"]), str(builds[ALMA]["build_id"])):
            assert rtb.dispose_image(bid) is True
    finally:
        # whatever a failure left standing (the daemon is shared with the next run)
        for name in (A, B):
            subprocess.run([DOCKER, "rm", "--force", name], capture_output=True)
        subprocess.run([DOCKER, "volume", "rm", "--force", STORAGE], capture_output=True)
        ls = subprocess.run([DOCKER, "images", "--format", "{{.ID}}", REPOSITORY], capture_output=True, text=True)
        for iid in {ln.strip() for ln in (ls.stdout or "").splitlines() if ln.strip()}:
            subprocess.run([DOCKER, "image", "rm", "--force", iid], capture_output=True)
        ps = subprocess.run([DOCKER, "ps", "-aq", "--filter", f"name=csis-bake-{RUNTIME}-"], capture_output=True, text=True)
        for cid in (ps.stdout or "").split():
            subprocess.run([DOCKER, "rm", "--force", cid], capture_output=True)
