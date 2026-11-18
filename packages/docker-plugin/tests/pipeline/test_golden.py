# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the docker family's emission for its own fixture.

A failure here means what the docker runtime or its roots generate has
changed. If the change is intended, run ``just golden-regen docker`` and
read the rewritten files one by one.

The same test runs in two places and must agree with one golden in both:
with only this package installed (``just test-docker-alone``) and with
every provider installed beside it (``just pytest``).
"""
from __future__ import annotations

from cs_image_system.system import testing as kit


def test_the_emission_matches_the_family_golden(family_run, golden_dir):
    run = family_run()
    summary = run.run("all", apply=True)
    assert summary.ok, summary.error
    kit.assert_matches(golden_dir, kit.emitted(run.generated, run.meta_state),
                       regenerate_with="just golden-regen docker")


def test_the_fixture_declares_docker_and_nothing_of_another_provider(family_run):
    """The family's fixture is a docker tree: one runtime, of type docker,
    and no builder of a type another provider registers."""
    ctx = family_run().ctx
    assert [type(rb).__module__.split(".")[1] for rb in ctx.runtime_builders.values()] == ["docker_runtime"]
