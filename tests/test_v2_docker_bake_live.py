# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 103, branch 1, the proof: the docker runtime BAKES on the local
daemon, from nothing to nothing. A tree of nothing but a docker runtime is
written from the frozen fixture's pieces (the fixture itself does not
change); its AlmaLinux 10 and Debian 12 base images and a posix-owned
instance image with a bash and an ansible modification are baked by
``run base-image instance-image`` under ``--no-dry-run``; the lineage, the
labels and the tags are read back from the daemon; the strict state query
finds no drift; the three builds are disposed through the runtime.

A leg of ``just full-test`` (``just test-docker-bake``); under ``just test``
the file is skipped. Needs docker (a daemon that answers), packer with the
docker and ansible plugins, and ansible-playbook. Several minutes: the
pulls, a package update per family, the modifications."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from v2_support import copy_config, docker_binary, load_context, reset_singletons

RUNTIME = "leg-docker"
BUILDER = "pckr-docker-ans"
REPOSITORY = "csis/leg"
ALMA = "leg-alma-10"
DEB = "leg-deb-12"
IMAGE = "leg-instance"
DOCKER = docker_binary()
PACKER = shutil.which("packer")
ANSIBLE = shutil.which("ansible-playbook")


def _docker_answers() -> bool:
    if shutil.which(DOCKER) is None:
        return False
    return subprocess.run([DOCKER, "info"], capture_output=True, timeout=30).returncode == 0

def require_engine_for_leg() -> None:
    """The Podman leg (``just test-podman-cycle``) is aimed at Podman's API
    service by ``CSIS_PODMAN_HOST``; it must not pass by quietly running on a
    docker daemon that happened to answer. Fails unless the daemon says it is
    Podman. A no-op for the docker legs."""
    if os.environ.get("CSIS_PODMAN_CYCLE") != "1":
        return
    res = subprocess.run([DOCKER, "version"], capture_output=True, text=True, timeout=60)
    assert "podman" in (res.stdout + res.stderr).lower(), (
        "CSIS_PODMAN_CYCLE=1 but the daemon CSIS_PODMAN_HOST names does not say it is Podman:\n" + (res.stdout + res.stderr)[-1500:])



_WANTED = os.environ.get("CSIS_DOCKER_BAKE") == "1"
pytestmark = [
    pytest.mark.skipif(not _WANTED, reason="docker bake leg: run by `just test-docker-bake` (a leg of `just full-test`)"),
    pytest.mark.skipif(_WANTED and not _docker_answers(), reason="docker is not answering (is its daemon running?)"),
    pytest.mark.skipif(_WANTED and not PACKER, reason="packer is not on PATH"),
    pytest.mark.skipif(_WANTED and not ANSIBLE, reason="ansible-playbook is not on PATH"),
]


def _write(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def docker_only_tree(root: Path) -> None:
    """Prune a copy of the frozen fixture to a tree of one docker runtime."""
    cfg = root / "cfg"
    _write(cfg / "runtime-builders.yml", {"runtime_builders": [{
        "name": RUNTIME, "type": "docker", "is_default": True, "executable": "docker", "repository": REPOSITORY,
        "default_machine_type": "small", "default_image_builder": BUILDER, "state_configuration": "local-dev",
        "machine_types": {"small": {"cpus": 2, "memory": "2g"}}, "networking": {"network": "bridge"},
        "tags": {"Project": "stage-103-leg"}}]})
    _write(cfg / "image-builders.yml", {"image_builders": [{
        "name": BUILDER, "type": "packer-docker", "is_default": True, "runtime": RUNTIME, "executable": "packer",
        "required_plugins": [{"name": "docker", "source": "github.com/hashicorp/docker", "version": ">= 1.0.0"},
                             {"name": "ansible", "source": "github.com/hashicorp/ansible", "version": ">= 1.0.0"}]}]})
    _write(cfg / "os-builders.yml", {"os_builders": [
        {"name": ALMA, "is_default": True, "identity_types": ["posix"], "storage_types": [], "type": "rhel",
         "family": "alma-linux", "family_version": 10, "tags": {"OS": "alma"},
         "runtimes": [{"name": "docker-alma", "image_builder": BUILDER}]},
        {"name": DEB, "identity_types": ["posix"], "storage_types": [], "type": "debian", "family": "debian",
         "family_version": 12, "tags": {"OS": "debian"}, "runtimes": [{"name": "docker-deb", "image_builder": BUILDER}]},
    ]})
    _write(cfg / "instance-builders.yml", {"instance_builders": []})
    _write(cfg / "storage-builders.yml", {"storage_builders": []})
    _write(cfg / "group-builders.yml", {"group_builders": [{"name": "posix-local", "type": "posix", "is_default": True}],
                                        "user_builders": [{"name": "posix-users", "type": "posix", "is_default": True}]})
    for stale in ("state-backends-2.yml", "state-backends-3.yml", "state-gcm.yml"):
        (cfg / stale).unlink(missing_ok=True)
    _write(cfg / "state-backends.yml", {"state_backends": [{"name": "local-dev", "type": "local", "is_default": True,
                                                            "path": "state"}]})
    exes = [{"name": "docker", "binary": DOCKER, "version": ">=24"},
            {"name": "packer", "binary": PACKER, "version": ">=1.14"},
            {"name": "ansible-playbook", "binary": ANSIBLE, "version": ">=2.16"},
            {"name": "bash", "binary": shutil.which("bash")}]
    _write(cfg / "executables.yml", {"executables": exes})
    # the posix group and its two personas alone
    users = yaml.safe_load((root / "groups" / "users.yaml").read_text())["users"]
    posix = [u for u in users if isinstance(u, dict) and u.get("type") == "posix-users"]
    assert len(posix) == 2, "the fixture's two posix personas"
    for p in (root / "groups").iterdir():
        if p.name != "group-pxgroup.yaml":
            p.unlink()
    _write(root / "groups" / "users.yaml", {"users": posix})
    # a tree has exactly one root group; here the posix group is it
    groups = yaml.safe_load((root / "groups" / "group-pxgroup.yaml").read_text())
    groups["groups"][0]["is_root"] = True
    _write(root / "groups" / "group-pxgroup.yaml", groups)
    for sub in ("images", "instances", "storages", "overlays", "base_images"):
        shutil.rmtree(root / sub, ignore_errors=True)
    for sub in ("images", "instances", "storages"):      # the loader reads each kind's directory, empty or not
        (root / sub).mkdir()
    (root / "leg.yml").write_text(
        "- hosts: all\n  become: true\n  tasks:\n"
        "    - name: a file the ansible modification leaves\n"
        "      copy:\n        dest: /etc/leg-ansible\n        content: \"baked by ansible through the daemon\\n\"\n")
    _write(root / "images" / "leg.yaml", {"images": [{
        "name": IMAGE, "group": "pxgroup", "source_image": DEB, "type": BUILDER, "description": "the leg's instance image",
        "runtimes": [{"image_builder": BUILDER}],
        # accounts come at launch (reconcile_accounts), so no `users:` here; the group is baked
        "tests": {"files": [{"path": "/etc/leg-ansible", "contains": "daemon"}, {"path": "/etc/leg-shell"}],
                  "services_enabled": ["chronyd"]},
        "modifications": [
            {"name": "leg-shell", "type": "bash-remote", "script": ["echo 'baked by a shell step' | sudo tee /etc/leg-shell"]},
            {"name": "leg-ansible", "type": "ansible-default", "playbooks": ["leg.yml"]},
        ]}]})
    cfg_text = (cfg / "_config.yml").read_text().replace("sleep_before_finalization: 30", "sleep_before_finalization: 0")
    (cfg / "_config.yml").write_text(cfg_text)


def _cli(root: Path, *args: str, env: dict[str, str], timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "cs_image_system.system", "--root-dir", str(root), *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=str(root))


def _inspect(image_id: str) -> dict:
    res = subprocess.run([DOCKER, "image", "inspect", image_id], capture_output=True, text=True, check=True)
    return json.loads(res.stdout)[0]


def test_the_docker_runtime_bakes_from_nothing_to_nothing(tmp_path, monkeypatch):
    root = copy_config(tmp_path, "leg")
    docker_only_tree(root)
    env = dict(os.environ)
    env["CSIS_CONFIG_IDENTITY"] = str(root / ".age-identity")
    env.setdefault("USER", "leg")
    if os.environ.get("CSIS_DOCKER_KEEP_HOST") != "1":     # the Podman leg names the daemon it is aimed at (test-podman-cycle)
        env.pop("DOCKER_HOST", None)                  # the runtime names no address: the environment's daemon
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", env["CSIS_CONFIG_IDENTITY"])
    built: list[str] = []
    try:
        # 1. a dry run first, as always: validate + the emission, no daemon work beyond the pulls
        dry = _cli(root, "--dry-run", "run", "base-image", "instance-image", env=env, timeout=1800)
        assert dry.returncode == 0, dry.stdout[-3000:] + dry.stderr[-3000:]
        # 2. the bake
        res = _cli(root, "--no-dry-run", "run", "base-image", "instance-image", env=env)
        assert res.returncode == 0, res.stdout[-4000:] + res.stderr[-4000:]
        # 3. the lineage: three builds on the runtime, each an image id
        reset_singletons()
        ctx = load_context(root, dry_run=True)
        builds = [b for b in ctx.meta_state.builds() if b.get("runtime") == RUNTIME]
        by_series = {str(b["series"]): b for b in builds}
        assert set(by_series) == {ALMA, DEB, IMAGE}, by_series
        for series, b in by_series.items():
            bid = str(b["build_id"])
            assert bid.startswith("sha256:") and len(bid) == 71, bid
            built.append(bid)
        # 4. what the daemon holds: labels as built, the final name and the floating tag, the movable tags
        from cs_image_system.docker_runtime.docker_names import parse_movable_tag, short_id

        def movable_of(tags) -> dict[str, tuple[str, str]]:
            """``{key: (short id, value)}`` of the movable tags among ``tags``."""
            out: dict[str, tuple[str, str]] = {}
            for t in tags:
                parsed = parse_movable_tag(t)
                if parsed is not None:
                    out[parsed[1]] = (parsed[0], parsed[2])
            return out
        for series, b in by_series.items():
            info = _inspect(str(b["build_id"]))
            labels = info["Config"]["Labels"]
            assert labels["csis_series"] == series and labels["csis_config"], labels
            if series in (ALMA, DEB):
                assert labels["OS"] == ("alma" if series == ALMA else "debian"), labels   # the OS builder's tags
            tags = {t.split(":", 1)[1] for t in info["RepoTags"] if t.startswith(REPOSITORY + ":")}
            prefix = f"{series}-{RUNTIME}" if series in (ALMA, DEB) else f"{series}-{BUILDER}"
            assert prefix in tags, (series, tags)                              # the floating tag
            assert any(t.startswith(prefix + "-20") for t in tags), (series, tags)   # the final name
            movable = movable_of(tags)
            assert "csis_fingerprint" in movable and "csis_parent" in movable, (series, tags)
            assert all(sid == short_id(info["Id"]) for sid, _ in movable.values()), (series, tags)
        # the instance image's parent is the Debian base, bound after the bake and said by a tag
        inst = _inspect(str(by_series[IMAGE]["build_id"]))
        inst_tags = [t.split(":", 1)[1] for t in inst["RepoTags"] if t.startswith(REPOSITORY + ":")]
        parent = movable_of(inst_tags)["csis_parent"][1]
        assert parent == str(by_series[DEB]["build_id"]), (parent, by_series[DEB]["build_id"])
        assert str(by_series[IMAGE].get("parent")) == str(by_series[DEB]["build_id"])
        # the modifications and the tests ran inside the committed image
        probe = subprocess.run([DOCKER, "run", "--rm", str(by_series[IMAGE]["build_id"]), "sh", "-c",
                                "cat /etc/leg-ansible /etc/leg-shell && getent group pxgroup"],
                               capture_output=True, text=True)
        assert probe.returncode == 0 and "daemon" in probe.stdout and "shell step" in probe.stdout, probe.stdout + probe.stderr
        assert "pxgroup:x:3101" in probe.stdout, probe.stdout
        # 5. the strict state query sees the lineage in the daemon and nothing else of ours
        query = _cli(root, "state", "query", "--strict", env=env, timeout=600)
        assert query.returncode == 0, query.stdout[-3000:] + query.stderr[-3000:]
        # 6. disposal through the runtime: the instance image first (it stands on the base), then the bases
        rtb = ctx.runtime_builders[RUNTIME]
        for series in (IMAGE, DEB, ALMA):
            assert rtb.dispose_image(str(by_series[series]["build_id"])) is True
            built.remove(str(by_series[series]["build_id"]))
            assert subprocess.run([DOCKER, "image", "inspect", str(by_series[series]["build_id"])],
                                  capture_output=True).returncode != 0
    finally:
        # whatever a failure left standing: every image in the leg's repository
        # (the daemon is shared with the next run, whose strict query would
        # call them foreign) and any bake container
        ls = subprocess.run([DOCKER, "images", "--format", "{{.ID}}", REPOSITORY], capture_output=True, text=True)
        for iid in {*built, *[ln.strip() for ln in (ls.stdout or "").splitlines() if ln.strip()]}:
            subprocess.run([DOCKER, "image", "rm", "--force", iid], capture_output=True)
        ps = subprocess.run([DOCKER, "ps", "-aq", "--filter", f"name=csis-bake-{RUNTIME}-"], capture_output=True, text=True)
        for cid in (ps.stdout or "").split():
            subprocess.run([DOCKER, "rm", "--force", cid], capture_output=True)
