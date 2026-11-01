# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 109 item 3: the resolver behind ``just test-podman-desktop-cycle``.

``scripts/podman-machine-host`` turns ``podman machine`` into the DOCKER_HOST URL of
Podman Desktop's machine, or into one sentence saying why the leg is skipped. Here
the ``podman`` binary is a stub that answers from files, so no machine is needed:
running, stopped, none, two machines (with and without a default), a named machine,
a machine with no socket, and no binary at all. The leg's recipe and its place in
``full-test`` are checked against the Justfile text.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "podman-machine-host"

STUB = """#!/bin/sh
# a podman that answers `machine list --format json` and `machine inspect NAME` from files
case "$2" in
  list) cat "$STUB_DIR/list.json" ;;
  inspect) f="$STUB_DIR/inspect-$3.json"; [ -f "$f" ] && cat "$f" || echo '[]' ;;
esac
"""


def _machine(name: str, *, running: bool = True, default: bool = False) -> dict:
    return {"Name": name, "Default": default, "Running": running, "Starting": False, "VMType": "applehv"}


def _inspect(name: str, socket: str | None) -> list[dict]:
    return [{"Name": name, "ConnectionInfo": {"PodmanSocket": {"Path": socket} if socket else None}}]


def _run(tmp_path: Path, machines: list[dict], sockets: dict[str, str | None] | None = None, *extra: str, env: dict | None = None):
    stub = tmp_path / "podman"
    stub.write_text(STUB)
    stub.chmod(0o755)
    (tmp_path / "list.json").write_text(json.dumps(machines))
    for name, sock in (sockets or {}).items():
        (tmp_path / f"inspect-{name}.json").write_text(json.dumps(_inspect(name, sock)))
    import os
    environment = {**os.environ, "STUB_DIR": str(tmp_path), **(env or {})}
    environment.pop("CSIS_PODMAN_MACHINE", None)
    environment.pop("PODMAN", None)
    environment.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPT), "--podman", str(stub), *extra], capture_output=True, text=True,
                          env=environment, timeout=60)


def test_a_running_machine_gives_its_socket_even_when_desktop_did_not_mark_it_default(tmp_path: Path):
    done = _run(tmp_path, [_machine("podman-machine-default", default=False)], {"podman-machine-default": "/var/folders/x/podman.sock"})
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "unix:///var/folders/x/podman.sock" and done.stderr == ""


def test_no_machine_is_exit_4_and_says_how_to_make_one(tmp_path: Path):
    done = _run(tmp_path, [])
    assert done.returncode == 4 and "no podman machine exists" in done.stderr and done.stdout == ""


def test_a_stopped_machine_is_exit_5_and_is_never_started(tmp_path: Path):
    done = _run(tmp_path, [_machine("m1", running=False)], {"m1": "/s"})
    assert done.returncode == 5 and "not running" in done.stderr and "power state is yours" in done.stderr
    assert done.stdout == ""


def test_two_machines_need_a_default_or_a_name(tmp_path: Path):
    machines = [_machine("a"), _machine("b")]
    socks = {"a": "/sock-a", "b": "/sock-b"}
    refused = _run(tmp_path, machines, socks)
    assert refused.returncode == 6 and "none is the default" in refused.stderr
    marked = _run(tmp_path, [_machine("a"), _machine("b", default=True)], socks)
    assert marked.returncode == 0 and marked.stdout.strip() == "unix:///sock-b"
    named = _run(tmp_path, machines, socks, "--machine", "a")
    assert named.returncode == 0 and named.stdout.strip() == "unix:///sock-a"
    via_env = _run(tmp_path, machines, socks, env={"CSIS_PODMAN_MACHINE": "b"})
    assert via_env.returncode == 0 and via_env.stdout.strip() == "unix:///sock-b"
    wrong = _run(tmp_path, machines, socks, "--machine", "zzz")
    assert wrong.returncode == 4 and "'zzz'" in wrong.stderr


def test_a_default_machine_that_is_stopped_is_not_swapped_for_a_running_one(tmp_path: Path):
    done = _run(tmp_path, [_machine("a", running=False, default=True), _machine("b")], {"a": "/sa", "b": "/sb"})
    assert done.returncode == 5 and "'a'" in done.stderr


def test_a_machine_that_reports_no_socket_is_exit_7(tmp_path: Path):
    done = _run(tmp_path, [_machine("m1")], {"m1": None})
    assert done.returncode == 7 and "no API socket" in done.stderr


def test_no_podman_binary_is_exit_3(tmp_path: Path):
    done = subprocess.run([sys.executable, str(SCRIPT), "--podman", str(tmp_path / "absent")], capture_output=True, text=True, timeout=60)
    assert done.returncode == 3 and "no podman binary" in done.stderr


def test_the_recipe_skips_loudly_and_full_test_names_the_leg():
    just = (REPO / "Justfile").read_text()
    recipe = just[just.index("\ntest-podman-desktop-cycle *ARGS:"):]
    recipe = recipe[:recipe.index("\n\n", 1)]
    assert "scripts/podman-machine-host" in recipe and "SKIPPED --" in recipe
    assert 'CSIS_PODMAN_HOST="$host" just test-podman-cycle' in recipe       # test-podman-cycle stays the one knob
    assert not re.search(r"podman machine (start|stop|init|rm)", recipe)     # the leg never changes the machine's power state
    legs = just[just.index("\nfull-test-legs:"):]
    legs = legs[:legs.index("\n\n", 1)]
    assert "just test-podman-desktop-cycle -q" in legs
    assert "test-podman-cycle and test-podman-desktop-cycle -- docker is not available" in legs
