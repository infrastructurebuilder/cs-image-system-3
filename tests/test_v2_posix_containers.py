# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 75 step 3: the posix accounts script on real systems -- AlmaLinux 10
(the AWS chain's family) and Debian 12 -- under docker.

Runs only from `just test-posix-accounts` (a leg of `just full-test`), which
sets CSIS_CONTAINER_TESTS=1; under `just test` every test here is skipped,
and so is every test when docker is not there. Each test is one throwaway
container: the scenario's setup, then the script, then what the test reads
back. The script is the plugin's own (`accounts.accounts_script`), the text
a machine receives.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from cs_image_system.posix_identity_plugin import accounts

IMAGES = {"el10": "almalinux:10", "debian12": "debian:12"}
SUDO = {"el10": "dnf -q -y install sudo >/dev/null 2>&1", "debian12": "apt-get -qq update >/dev/null && apt-get -qq install -y sudo >/dev/null"}

def _docker_answers() -> bool:
    """The client is there AND its daemon answers (OrbStack or Docker Desktop
    not running leaves the client installed and every container failing)."""
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0


_WANTED = os.environ.get("CSIS_CONTAINER_TESTS") == "1"
pytestmark = [
    pytest.mark.skipif(not _WANTED, reason="container leg: run by `just test-posix-accounts` (a leg of `just full-test`)"),
    pytest.mark.skipif(_WANTED and not _docker_answers(), reason="docker is not answering (is its daemon running?)"),
]

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITangoTangoTangoTangoTangoTangoTangoTango taylor_tango@example.invalid"


def _full_script() -> str:
    return accounts.accounts_script(groups={"pxgroup": 3101}, users={"taylor_tango": 3201, "uma_uniform": 3202},
                                    members={"pxgroup": ["taylor_tango", "uma_uniform"]},
                                    keys={"taylor_tango": [KEY]}, admins={"pxgroup": ["taylor_tango"]})


def _run(family: str, setup: str, script: str, after: str) -> subprocess.CompletedProcess:
    """One container: install sudo, the setup, the script as /tmp/acc.sh, then
    `after` (which may run the script again). The script's own exit status is
    printed as `SCRIPT_EXIT=<n>`; the container's is the whole run's."""
    driver = "\n".join([
        "set -u",
        SUDO[family],
        setup,
        "cat > /tmp/acc.sh <<'CSIS_ACCOUNTS_SCRIPT'",
        script.rstrip("\n"),
        "CSIS_ACCOUNTS_SCRIPT",
        "bash /tmp/acc.sh; echo SCRIPT_EXIT=$?",
        after,
    ])
    return subprocess.run(["docker", "run", "--rm", "-i", IMAGES[family], "bash", "-s"], input=driver,
                          capture_output=True, text=True, timeout=600)


FAMILIES = sorted(IMAGES)


@pytest.mark.parametrize("family", FAMILIES)
def test_a_fresh_machine_gets_everything_and_a_second_run_changes_nothing(family):
    after = "\n".join([
        "sum1=$(cat /etc/group /etc/passwd /etc/sudoers.d/60-csis-pxgroup ~taylor_tango/.ssh/authorized_keys | md5sum)",
        "bash /tmp/acc.sh >/dev/null; echo SECOND_EXIT=$?",
        "sum2=$(cat /etc/group /etc/passwd /etc/sudoers.d/60-csis-pxgroup ~taylor_tango/.ssh/authorized_keys | md5sum)",
        "[ \"$sum1\" = \"$sum2\" ] && echo UNCHANGED || echo CHANGED",
        "getent group pxgroup; getent passwd taylor_tango | cut -d: -f1,3,4,6,7; id uma_uniform",
        "stat -c '%a %U' ~taylor_tango/.ssh ~taylor_tango/.ssh/authorized_keys /etc/sudoers.d/60-csis-pxgroup",
        "visudo -c >/dev/null && echo SUDOERS_OK",
        "sudo -l -U taylor_tango | grep -q NOPASSWD && echo ADMIN_SUDO",
        "sudo -l -U uma_uniform | grep -q NOPASSWD || echo MEMBER_NO_SUDO",
    ])
    out = _run(family, "", _full_script(), after).stdout
    assert "SCRIPT_EXIT=0" in out and "SECOND_EXIT=0" in out and "UNCHANGED" in out, out
    assert "pxgroup:x:3101:taylor_tango,uma_uniform" in out, out
    assert "taylor_tango:3201:3201:/home/taylor_tango:/bin/bash" in out, out
    assert "uid=3202(uma_uniform) gid=3202(uma_uniform)" in out and "3101(pxgroup)" in out, out
    assert "700 taylor_tango" in out and "600 taylor_tango" in out and "440 root" in out, out
    assert "SUDOERS_OK" in out and "ADMIN_SUDO" in out and "MEMBER_NO_SUDO" in out, out


@pytest.mark.parametrize("family", FAMILIES)
def test_a_group_that_stands_equal_is_adopted(family):
    out = _run(family, "groupadd -g 3101 pxgroup", accounts.accounts_script(groups={"pxgroup": 3101}),
               "getent group pxgroup").stdout
    assert "SCRIPT_EXIT=0" in out and "pxgroup:x:3101:" in out, out


@pytest.mark.parametrize("family", FAMILIES)
def test_a_group_that_stands_with_another_gid_is_refused_with_both(family):
    proc = _run(family, "groupadd -g 4000 pxgroup", accounts.accounts_script(groups={"pxgroup": 3101}),
                "getent group pxgroup")
    assert "SCRIPT_EXIT=3" in proc.stdout and "pxgroup:x:4000:" in proc.stdout, proc.stdout
    assert "group pxgroup has gid 4000 here; the configuration says 3101" in proc.stderr, proc.stderr


@pytest.mark.parametrize("family", FAMILIES)
def test_a_gid_another_group_holds_is_refused(family):
    proc = _run(family, "groupadd -g 3101 squatter", accounts.accounts_script(groups={"pxgroup": 3101}),
                "getent group pxgroup || echo NO_PXGROUP")
    assert "SCRIPT_EXIT=3" in proc.stdout and "NO_PXGROUP" in proc.stdout, proc.stdout
    assert "gid 3101 belongs to group squatter here; the configuration gives it to pxgroup" in proc.stderr, proc.stderr


@pytest.mark.parametrize("family", FAMILIES)
def test_beside_okta_a_member_without_an_account_waits_and_the_next_run_adds_it(family):
    """The groups-only shape: the group and its members, the members' accounts
    made by someone else -- here by hand, as OPA's sync would."""
    script = accounts.accounts_script(groups={"coops": 60123}, members={"coops": ["avery.alpha", "blake.bravo"]})
    after = "\n".join(["getent group coops", "useradd -m blake.bravo", "bash /tmp/acc.sh >/dev/null 2>&1; echo SECOND_EXIT=$?",
                       "getent group coops"])
    proc = _run(family, "useradd -m avery.alpha", script, after)
    assert "SCRIPT_EXIT=0" in proc.stdout and "SECOND_EXIT=0" in proc.stdout, proc.stdout
    assert "coops:x:60123:avery.alpha\n" in proc.stdout and "coops:x:60123:avery.alpha,blake.bravo" in proc.stdout, proc.stdout
    assert "blake.bravo has no account here yet; not a member of coops until it does" in proc.stderr, proc.stderr
