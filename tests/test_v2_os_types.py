# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The OS type owns the package manager.

Every plugin that bakes a package asks the OS type that serves the image's
family for the manager's lines (``package_install_command`` and its
siblings on ``OsBuilderModelProtocol``); the core resolves the type from
the family (``os_types.os_type_for_family``) and never names a manager
itself. The proof that this holds is the registered alpine type, which the
frozen fixture declares no base image for: every prerequisite, verify and
package-test line a plugin renders for an alpine image goes through the
hooks and says ``apk``, and none of them says what the rpm or deb families
would. The rpm and deb lines themselves are held by the golden.
"""
from __future__ import annotations

import re
import subprocess
from types import SimpleNamespace
from typing import Any, cast

import pytest

from v2_support import V2Run

OTHER_MANAGERS = re.compile(r"(?<![a-z0-9])(yum|dnf|apt-get|apt|dpkg|rpm)(?![a-z0-9])")


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _says_only_apk(lines: list[str]) -> None:
    commands = [l for l in lines if not l.startswith("#")]
    wrong = [l for l in commands if OTHER_MANAGERS.search(l)]
    assert wrong == [], f"an alpine bake would run another family's package manager: {wrong}"


# ------------------------------------------------------------ the resolver
def test_the_resolver_finds_the_type_that_serves_a_family():
    from cs_image_system.base.os_types import os_type_for_family
    assert os_type_for_family("alpine").csis_name() == "alpine"
    assert os_type_for_family("debian").csis_name() == "debian"
    assert os_type_for_family("Ubuntu").csis_name() == "ubuntu"
    # the rhel type serves the rebuilds the image-source catalog says ARE rhel
    assert os_type_for_family("alma-linux").csis_name() == "rhel"
    assert os_type_for_family("rhel").csis_name() == "rhel"


def test_the_resolver_refuses_an_unserved_or_missing_family():
    from cs_image_system.base.os_types import os_type_for_family
    with pytest.raises(ValueError, match="no registered OS type serves the family 'plan9'"):
        os_type_for_family("plan9")
    with pytest.raises(ValueError, match="no OS family given"):
        os_type_for_family(None)


def test_the_core_base_type_names_no_manager():
    """A type that implements none of the hooks fails by name at the first
    bake that asks, never with another family's line."""
    from cs_image_system.base.models.os_builder_model import OsBuilderModel
    with pytest.raises(NotImplementedError, match="declares no package manager.*package_install_command"):
        OsBuilderModel.package_install_command(["x"])
    with pytest.raises(NotImplementedError, match="package_present_check"):
        OsBuilderModel.package_present_check("x")


# ------------------------------------------------------------ the three types
@pytest.mark.parametrize("family,fmt,install", [
    ("rhel", "rpm", "sudo yum install -y curl unzip"),
    ("debian", "deb", "sudo apt-get -o DPkg::Lock::Timeout=600 install -y curl unzip"),
    ("alpine", "apk", "sudo apk add --no-cache curl unzip"),
])
def test_each_type_answers_its_own_manager(family, fmt, install):
    from cs_image_system.base.os_types import os_type_for_family
    from cs_image_system.contract.operating_system import PACKAGE_LOCK_TIMEOUT
    t = os_type_for_family(family)
    assert t.package_format() == fmt
    assert t.package_install_command(["curl", "unzip"], lock_timeout=PACKAGE_LOCK_TIMEOUT) == install
    assert t.service_enable_command("sshd")
    assert "python3" in t.ansible_python_install_command()


def test_the_lock_timeout_is_the_deb_families_alone():
    """apt-get takes the wait as an option; the rpm and alpine managers
    have no such option and ignore it, so a caller may always pass it."""
    from cs_image_system.base.os_types import os_type_for_family
    deb, rpm, apk = (os_type_for_family(f) for f in ("debian", "rhel", "alpine"))
    assert deb.package_install_command(["x"]) == "sudo apt-get install -y x"
    assert deb.package_install_command(["x"], lock_timeout=30) == "sudo apt-get -o DPkg::Lock::Timeout=30 install -y x"
    assert rpm.package_install_command(["x"], lock_timeout=30) == rpm.package_install_command(["x"])
    assert apk.package_install_command(["x"], lock_timeout=30) == apk.package_install_command(["x"])


SENTINEL = "REACHED-THE-LINE-AFTER"


@pytest.mark.parametrize("family", ["rhel", "debian", "alpine"])
def test_every_types_package_check_stops_a_bake_and_names_the_package(family):
    """The property tests/test_v2_in_bake_tests_enforce.py holds the rpm
    line to, for every type: a false package test exits for itself under
    ``sh -e`` and says which package (the host has none of the managers,
    so every check is false here)."""
    from cs_image_system.base.os_types import os_type_for_family
    line = os_type_for_family(family).package_present_check("nope-not-a-real-package-xyz")
    proc = subprocess.run(["sh", "-e", "-c", f"{line}\necho {SENTINEL}"], capture_output=True, text=True)
    assert SENTINEL not in proc.stdout, line
    assert "nope-not-a-real-package-xyz" in proc.stderr and "not installed" in proc.stderr


# ------------------------------------------------------------ the alpine proof
def test_an_alpine_image_bakes_through_the_hooks(v2):
    """What the fixture's plugins would bake for an alpine base image: the
    posix group's and the ebs storage's prerequisites (nothing to install:
    no manager at all), the efs and s3 storages' and the runtimes' session
    agents (apk lines), and the declared package tests (apk's own test).
    Nothing says yum, dnf, apt, dpkg or rpm."""
    from cs_image_system.base.image_tests import declared_test_commands
    from cs_image_system.base.os_types import os_type_for_family
    ctx = v2.ctx
    alpine = os_type_for_family("alpine")
    posix = ctx.group_builders["posix-local"]
    ebs, efs, s3 = (ctx.storage_builders[n] for n in ("aws-ebs", "aws-efs", "aws-s3"))
    for b in (posix, ebs):
        lines = b.base_image_prerequisites("alpine") + b.verify_commands("alpine")
        _says_only_apk(lines)
        assert not any("apk" in l for l in lines), "nothing to install: no package line at all"
    efs_lines = efs.base_image_prerequisites("alpine")
    s3_lines = s3.base_image_prerequisites("alpine")
    assert "sudo apk add --no-cache nfs-utils" in efs_lines
    assert any("sudo apk add --no-cache curl unzip" in l for l in s3_lines)
    _says_only_apk(efs_lines + s3_lines + efs.verify_commands("alpine") + s3.verify_commands("alpine"))
    # the runtimes' session agents
    aws = next(r for r in ctx.runtime_builders.values() if r.session_mechanism() == "ssm")
    gcp = next(r for r in ctx.runtime_builders.values() if r.session_mechanism() == "iap")
    with pytest.raises(ValueError, match="no agent package in the apk format"):
        aws.session_agent_commands("alpine")      # Amazon ships no apk of its agent: refused, not guessed
    gcp_lines = gcp.session_agent_commands("alpine")
    assert any("sudo apk add --no-cache google-guest-agent" in l for l in gcp_lines)
    _says_only_apk(gcp_lines)
    # the declared package tests
    checks = declared_test_commands({"packages": ["nfs-utils"]}, os_type=alpine)
    assert checks == [alpine.package_present_check("nfs-utils")]
    assert "apk info -e nfs-utils" in checks[0]
    _says_only_apk(checks)
    # the local modification tests' ansible preparation
    assert alpine.ansible_python_install_command() == "command -v python3 >/dev/null 2>&1 || apk add --no-cache python3"


def test_the_filestore_storage_bakes_apk_on_alpine():
    from cs_image_system.tf_gcp_plugin.tf_gcp_storage_builder import TofuFilestoreStorageBuilder
    stub = cast(Any, SimpleNamespace(get_name=lambda: "fs"))
    lines = TofuFilestoreStorageBuilder.base_image_prerequisites(stub, "alpine")
    assert lines[1] == "sudo apk add --no-cache nfs-utils"
    _says_only_apk(lines)


def test_okta_refuses_an_alpine_image_rather_than_guessing(v2):
    """OktaPAM publishes deb and rpm repositories and nothing for alpine:
    the identity plugin says so instead of emitting another family's lines."""
    okta = v2.ctx.group_builders["oktagroups"]
    with pytest.raises(ValueError, match="publishes no apk package"):
        okta.base_image_prerequisites("alpine")


def test_a_package_test_needs_the_os_type():
    from cs_image_system.base.image_tests import declared_test_commands
    with pytest.raises(ValueError, match="needs the image's OS type"):
        declared_test_commands({"packages": ["git"]})
    assert declared_test_commands({"files": [{"path": "/etc/x"}]}) == ["test -e /etc/x"]
