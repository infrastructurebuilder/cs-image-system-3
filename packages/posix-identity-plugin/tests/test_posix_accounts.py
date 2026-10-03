# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The accounts script's parts, as text: what each part asks of the machine,
that it adopts what is equal and refuses what differs, and that it quotes
what it is given. Whether the script really does that on EL10 and Debian is
the container leg's question (tests/test_v2_posix_containers.py)."""
from __future__ import annotations

import subprocess

import pytest

from cs_image_system.posix_identity_plugin import accounts


def _bash_n(script: str) -> None:
    """The script parses as bash (no execution)."""
    proc = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_a_group_is_created_with_its_gid_or_adopted_or_refused():
    text = "\n".join(accounts.group_part("pxgroup", 3101))
    assert "groupadd -g 3101 pxgroup" in text
    assert "getent group pxgroup" in text and "getent group 3101" in text      # by name, then by id
    assert "has gid $have here; the configuration says 3101" in text
    assert "gid 3101 belongs to group $other here; the configuration gives it to pxgroup" in text


def test_a_user_brings_its_private_group_and_a_home():
    text = "\n".join(accounts.user_part("taylor_tango", 3201))
    assert text.index("groupadd -g 3201 taylor_tango") < text.index("useradd -m -u 3201 -g 3201 -s /bin/bash taylor_tango")
    assert "has uid $have here; the configuration says 3201" in text


def test_membership_is_set_exactly_and_waits_for_accounts_that_do_not_stand():
    text = "\n".join(accounts.membership_part("pxgroup", ["uma_uniform", "taylor_tango", "taylor_tango"]))
    assert "members of pxgroup: taylor_tango, uma_uniform" in text
    assert text.count("getent passwd") == 2                                     # once per distinct member
    assert "not a member of pxgroup until it does" in text
    assert "gpasswd -M \"$want\" pxgroup" in text


def test_keys_are_written_only_when_they_differ_and_never_when_none_are_declared():
    text = "\n".join(accounts.keys_part("taylor_tango", ["ssh-ed25519 AAAAC3Nza tango@example.invalid", "  "]))
    assert "authorized keys of taylor_tango: 1" in text and "install -m 0600" in text
    assert accounts.keys_part("uma_uniform", []) == [
        "# authorized keys of uma_uniform: none declared; the file is left as it stands"]


def test_sudo_is_checked_by_visudo_before_it_is_installed_and_removed_with_no_admins():
    text = "\n".join(accounts.sudo_part("pxgroup", ["taylor_tango"]))
    assert "taylor_tango ALL=(ALL) NOPASSWD:ALL" in text
    assert text.index("visudo -cf") < text.index("install -m 0440")
    assert accounts.sudo_part("pxgroup", []) == ["# sudo for pxgroup: no admins", "rm -f /etc/sudoers.d/60-csis-pxgroup"]


def test_the_whole_script_parses_and_orders_users_before_their_groups_members():
    script = accounts.accounts_script(groups={"pxgroup": 3101}, users={"taylor_tango": 3201, "uma_uniform": 3202},
                                      members={"pxgroup": ["taylor_tango", "uma_uniform"]},
                                      keys={"taylor_tango": ["ssh-ed25519 AAAAC3Nza tango@example.invalid"]},
                                      admins={"pxgroup": ["taylor_tango"]})
    _bash_n(script)
    assert script.startswith("#!/usr/bin/env bash\n") and "set -euo pipefail" in script
    assert script.index("useradd") < script.index("groupadd -g 3101 pxgroup") < script.index("gpasswd -M")
    assert script.rstrip().endswith("echo 'posix accounts: in place'")


def test_beside_okta_only_groups_and_members_are_written():
    script = accounts.accounts_script(groups={"coops": 60123}, members={"coops": ["avery.alpha"]})
    _bash_n(script)
    assert "useradd" not in script and "sudoers" not in script and "authorized_keys" not in script


@pytest.mark.parametrize("hostile", ["px'group", "pxgroup; rm -rf /", "$(id)"])
def test_whatever_reaches_the_script_is_quoted(hostile):
    script = accounts.accounts_script(groups={hostile: 3101})
    _bash_n(script)
    assert f"groupadd -g 3101 {hostile}" not in script
