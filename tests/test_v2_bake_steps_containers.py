# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 86: the bake's step runner against a package database that is
REALLY held -- AlmaLinux 10 (rpm's transaction lock) and Debian 12 (dpkg's
frontend lock) -- under docker.

The walk's second `perform` lost its base bake to `rpm --import` failing at
once on "can't create transaction lock" while the account's fleet management
held the database. Here another process takes that same lock for a while,
the bake's own settle step writes the runner, and a package step is run the
way packer runs one (the emitted `execute_command`): it must fail with the
tool's real words, wait, and pass once the lock is free.

Runs only from `just test-bake-steps` (a leg of `just full-test`), which sets
CSIS_CONTAINER_TESTS=1; under `just test` every test here is skipped, and so
is every test when docker is not there.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from cs_image_system.base import bake_steps

IMAGES = {"el10": "almalinux:10", "debian12": "debian:12"}

#: Takes the family's package-database lock the way its own tools do (an
#: fcntl write lock) and keeps it for the seconds given.
HOLD = {
    "el10": ("python3 -c \"import fcntl,time; f=open('/usr/lib/sysimage/rpm/.rpm.lock','a'); "
             "fcntl.lockf(f, fcntl.LOCK_EX); time.sleep({seconds})\" &"),
    "debian12": ("perl -e 'use Fcntl qw(F_SETLK F_WRLCK SEEK_SET); open(my $f, \">>\", \"/var/lib/dpkg/lock-frontend\") "
                 "or die; my $l = pack(\"s s q q i\", F_WRLCK, SEEK_SET, 0, 0, 0); "
                 "fcntl($f, F_SETLK, $l) or die \"lock: $!\"; sleep {seconds}' &"),
}
#: A package step that needs that lock, and what the tool says when it is held.
STEP = {
    "el10": ("rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-AlmaLinux-10", "can't create transaction lock"),
    "debian12": ("dpkg --configure -a", "dpkg frontend lock was locked by another process"),
}


def _docker_answers() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0


_WANTED = os.environ.get("CSIS_CONTAINER_TESTS") == "1"
pytestmark = [
    pytest.mark.skipif(not _WANTED, reason="container leg: run by `just test-bake-steps` (a leg of `just full-test`)"),
    pytest.mark.skipif(_WANTED and not _docker_answers(), reason="docker is not answering (is its daemon running?)"),
]


def _run(family: str, body: str) -> subprocess.CompletedProcess[str]:
    """One throwaway container: a stand-in `sudo` (the images have none and the
    container is root), the bake's settle step as packer would run it, then
    `body`. `step` in the body runs /tmp/step.sh through the emitted
    execute_command and prints `STEP_EXIT=<n> after <s>s`."""
    execute = bake_steps.EXECUTE_COMMAND.replace("{{ .Vars }}", "CSIS_STEP_WAIT=4").replace("{{ .Path }}", "/tmp/step.sh")
    driver = "\n".join([
        "set -u",
        "printf '#!/bin/sh\\nexec \"$@\"\\n' > /usr/local/bin/sudo; chmod +x /usr/local/bin/sudo",
        "cat > /tmp/settle.sh <<'CSIS_SETTLE_SCRIPT'",
        "#!/bin/sh -e",
        *bake_steps.settle_commands([]),
        "CSIS_SETTLE_SCRIPT",
        "sh -e /tmp/settle.sh; echo SETTLE_EXIT=$?",
        "cat > /tmp/execute.sh <<'CSIS_EXECUTE'",
        execute,
        "CSIS_EXECUTE",
        "step() { start=$(date +%s); sh /tmp/execute.sh; echo \"STEP_EXIT=$? after $(( $(date +%s) - start ))s\"; }",
        body,
    ])
    return subprocess.run(["docker", "run", "--rm", IMAGES[family], "sh", "-c", driver],
                          capture_output=True, text=True, timeout=600)


@pytest.mark.parametrize("family", sorted(IMAGES))
def test_the_settle_step_runs_and_leaves_the_runner(family: str):
    done = _run(family, f"test -r {bake_steps.STEP_RUNNER} && head -2 {bake_steps.STEP_RUNNER}")
    assert "SETTLE_EXIT=0" in done.stdout, done.stdout + done.stderr
    assert "# cs-image-system: runs ONE step of a bake." in done.stdout


@pytest.mark.parametrize("family", sorted(IMAGES))
def test_a_package_step_waits_out_a_really_held_database(family: str):
    command, said = STEP[family]
    done = _run(family, "\n".join([
        HOLD[family].format(seconds=11),
        "sleep 1",
        f"printf '#!/bin/sh -e\\n{command}\\necho STEP_PASSED\\n' > /tmp/step.sh",
        "step",
    ]))
    out = done.stdout + done.stderr
    assert said in out, f"the tool's own refusal, as the walk saw it: {out}"
    assert "csis-step: the package database was held by another process (attempt 1 of 10)" in out, out
    assert "STEP_PASSED" in out and "STEP_EXIT=0" in out, out


@pytest.mark.parametrize("family", sorted(IMAGES))
def test_a_step_that_fails_for_its_own_reason_is_not_waited_for(family: str):
    done = _run(family, "\n".join([
        "printf '#!/bin/sh -e\\necho \"package git is not installed\" >&2\\nexit 1\\n' > /tmp/step.sh",
        "step",
    ]))
    out = done.stdout + done.stderr
    assert "STEP_EXIT=1 after 0s" in out or "STEP_EXIT=1 after 1s" in out, out
    assert "held by another process" not in out
