# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 53: an in-bake assertion must be able to STOP the bake.

The assertions are spliced into a packer shell provisioner as `inline` lines
behind a leading `set -e`, so "exits nonzero on failure" is not enough: POSIX
suppresses errexit for a command that is part of an AND-OR list, and a line
ending in `|| { ... }` therefore cannot fail a build however false it is.
Stage 19's first image baked green twice while asserting `rpm -q vim` on
AlmaLinux 10, which has no package of that name, and an instance launched from
that AMI then failed the same check.

These tests run each generated assertion the way packer runs it -- `sh -e`,
one script, a sentinel after it -- and assert on BEHAVIOUR rather than on the
text, because the text is what was wrong and looked right.
"""
from __future__ import annotations

import subprocess

from cs_image_system.base.image_tests import declared_test_commands

SENTINEL = "REACHED-THE-LINE-AFTER"


def _aborts(assertion: str) -> bool:
    """Does this assertion stop a `set -e` script, as packer would run it?"""
    proc = subprocess.run(["sh", "-e", "-c", f"{assertion}\necho {SENTINEL}"],
                          capture_output=True, text=True)
    return SENTINEL not in proc.stdout


def test_a_false_package_assertion_stops_the_bake():
    """The regression. `rpm -q <nothing>` used to be written `a || { b && c; }`,
    which errexit ignores -- so the bake carried on and the image shipped."""
    assertion = declared_test_commands({"packages": ["nope-not-a-real-package-xyz"]})[0]
    assert _aborts(assertion), f"a false package assertion cannot stop the bake: {assertion}"


def test_a_false_package_assertion_says_which_package():
    assertion = declared_test_commands({"packages": ["nope-not-a-real-package-xyz"]})[0]
    proc = subprocess.run(["sh", "-e", "-c", assertion], capture_output=True, text=True)
    assert "nope-not-a-real-package-xyz" in proc.stderr
    assert "not installed" in proc.stderr


def test_no_assertion_ends_in_an_unenforceable_fallback():
    """The shape, as well as the behaviour: a trailing `|| { ... }` is the form
    errexit cannot see, and it reads exactly like a working assertion."""
    spec = {"files": [{"path": "/etc/x", "mode": "0644", "contains": "y"}],
            "packages": ["git"], "commands": [{"run": "true", "contains": "z"}],
            "services_enabled": ["sftd"], "users": ["csisadmin"]}
    for assertion in declared_test_commands(spec):
        assert not assertion.rstrip().endswith("}"), f"unenforceable under set -e: {assertion}"


def test_every_false_assertion_form_stops_the_bake():
    """Each primitive, individually false, must abort -- the property the
    provisioner depends on and nothing was checking."""
    cases = {
        "files": {"files": [{"path": "/definitely/not/here"}]},
        "packages": {"packages": ["nope-not-a-real-package-xyz"]},
        "commands": {"commands": [{"run": "echo nothing", "contains": "ABSENT-STRING"}]},
        "commands-rc": {"commands": [{"run": "false", "expect_rc": 0}]},
        "users": {"users": ["nosuchuser-xyz"]},
    }
    unenforced = [name for name, spec in cases.items()
                  if not all(_aborts(a) for a in declared_test_commands(spec))]
    assert unenforced == [], f"these assertion kinds cannot fail a bake: {unenforced}"


def test_a_true_assertion_does_not_stop_the_bake():
    """The other half: the fix must not make a passing assertion abort."""
    for spec in ({"commands": [{"run": "echo hello", "contains": "hello"}]},
                 {"files": [{"path": "/etc"}]}):
        for assertion in declared_test_commands(spec):
            assert not _aborts(assertion), assertion
