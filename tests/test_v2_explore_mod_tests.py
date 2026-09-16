# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""EXPLORE "Automated Testing for Modifications" (branch
v2-explore-mod-tests): every modification runs twice against a throwaway
local target; run 1 must succeed, run 2 must change nothing.

The harness is exercised with a FAKE target (no docker); one docker-backed
test runs only with CSIS_DOCKER_TESTS=1.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from v2_support import V2Run


class FakeTarget:
    """Records commands; simulates a filesystem diff that grows on the
    first application only (idempotent) or on every application (not)."""
    instances: list["FakeTarget"] = []

    def __init__(self, image: str, idempotent: bool = True, fail_first: bool = False):
        self.image = image
        self.name = f"fake-{len(FakeTarget.instances)}"
        self.commands: list[str] = []
        self.copied: list[tuple[Path, str]] = []
        self._diff: set[str] = set()
        self._applies = 0
        self.idempotent = idempotent
        self.fail_first = fail_first
        self.closed = False
        FakeTarget.instances.append(self)

    def exec(self, command: str):
        self.commands.append(command)
        # one "application" = the inline step (the last command of an apply)
        if command == "sh /tmp/csis-test/inline.sh":
            self._applies += 1
            if self.fail_first and self._applies == 1:
                return 1, "boom"
            if self._applies == 1 or not self.idempotent:
                self._diff.add(f"A /opt/derivative/run{self._applies}")
            self._diff.add("C /tmp/csis-test")   # volatile, ignored by the harness
        return 0, ""

    def copy_in(self, source: Path, dest: str):
        self.copied.append((source, dest))

    def diff(self):
        return sorted(self._diff)

    def close(self):
        self.closed = True


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    FakeTarget.instances.clear()
    yield run
    run.restore_cwd()


def _only_bash(ctx):
    """Keep the fixture's bash mod only (ansible needs a real ansible run)."""
    for img in ctx.images:
        img.modifications = [m for m in (img.modifications or []) if not isinstance(m, dict)
                             and getattr(m, "get_type", lambda: "")() == "bash-remote"]


def test_container_image_is_derived_from_the_root_os(v2):
    from cs_image_system.base.mod_tests import test_image_for
    dask = v2.ctx.images_map["imgfile-basic-dask"]           # <- basic-rh-10
    assert test_image_for(v2.ctx, dask) == "almalinux:10"     # family_version 10 since stage 13; AlmaLinux from 10 (§16)
    ds = v2.ctx.images_map["imgfile-data-science"]           # <- my-deb-11
    assert test_image_for(v2.ctx, ds) == "debian:11"
    v2.ctx.os_builders["basic-rh-10"].model.local_test_image = "registry.example/ubi8"
    assert test_image_for(v2.ctx, dask) == "registry.example/ubi8"


def test_bash_mod_passes_and_is_idempotent(v2):
    from cs_image_system.base.mod_tests import run_mod_tests
    _only_bash(v2.ctx)
    results = run_mod_tests(v2.ctx, images=["imgfile-basic-dask"], make_target=lambda img: FakeTarget(img))
    assert [r.status for r in results] == ["pass"]
    r = results[0]
    assert r.mod == "derivative-setup" and r.idempotent is True and r.changes_on_rerun == []
    t = FakeTarget.instances[-1]
    assert t.image == "almalinux:10" and t.closed
    # staged files reached the target and both script forms ran, twice
    assert any(dest == "/tmp/csis-test-src" for _, dest in t.copied)
    assert t.commands.count("sh /tmp/csis-test/mod_image.sh") == 2
    assert t.commands.count("sh /tmp/csis-test/inline.sh") == 2
    assert t.commands[0].startswith("command -v sudo")     # the sudo shim comes first
    recorded = yaml.safe_load((v2.meta_state / "mod-tests.yaml").read_text())["results"]
    assert recorded[r.content_hash]["status"] == "pass"


def test_non_idempotent_mod_is_reported(v2):
    from cs_image_system.base.mod_tests import run_mod_tests
    _only_bash(v2.ctx)
    results = run_mod_tests(v2.ctx, images=["imgfile-basic-dask"],
                            make_target=lambda img: FakeTarget(img, idempotent=False))
    r = results[0]
    assert r.status == "pass" and r.idempotent is False
    assert r.changes_on_rerun == ["A /opt/derivative/run2"]


def test_failing_mod_is_reported_and_cached_results_are_reused(v2):
    from cs_image_system.base.mod_tests import run_mod_tests
    _only_bash(v2.ctx)
    results = run_mod_tests(v2.ctx, images=["imgfile-basic-dask"],
                            make_target=lambda img: FakeTarget(img, fail_first=True))
    assert results[0].status == "fail" and results[0].first_run_rc == 1 and "boom" in results[0].detail
    # a pass is cached by content hash; the next run does not touch a target
    ok = run_mod_tests(v2.ctx, images=["imgfile-basic-dask"], make_target=lambda img: FakeTarget(img))
    assert ok[0].status == "pass"
    n = len(FakeTarget.instances)
    again = run_mod_tests(v2.ctx, images=["imgfile-basic-dask"], make_target=lambda img: FakeTarget(img))
    assert again[0].status == "pass" and again[0].detail.startswith("cached")
    assert len(FakeTarget.instances) == n
    forced = run_mod_tests(v2.ctx, images=["imgfile-basic-dask"], make_target=lambda img: FakeTarget(img), force=True)
    assert forced[0].status == "pass" and len(FakeTarget.instances) == n + 1


def test_without_docker_results_are_skipped_not_failed(v2, monkeypatch):
    from cs_image_system.base import mod_tests
    monkeypatch.setattr(mod_tests, "docker_available", lambda docker="docker": False)
    _only_bash(v2.ctx)
    results = mod_tests.run_mod_tests(v2.ctx, images=["imgfile-basic-dask"])
    assert [r.status for r in results] == ["skipped"]


@pytest.mark.skipif(not os.environ.get("CSIS_DOCKER_TESTS"), reason="set CSIS_DOCKER_TESTS=1 to run against docker")
def test_live_docker_bash_mod(v2):
    from cs_image_system.base.mod_tests import docker_available, run_mod_tests
    if not docker_available():
        pytest.skip("docker not available")
    _only_bash(v2.ctx)
    results = run_mod_tests(v2.ctx, images=["imgfile-basic-dask"], force=True)
    r = results[0]
    assert r.status == "pass", r.detail
    assert r.idempotent is True, r.changes_on_rerun
    subprocess.run(["docker", "image", "inspect", "almalinux:10"], check=True, capture_output=True)
