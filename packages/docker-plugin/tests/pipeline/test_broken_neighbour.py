# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A broken plugin installed beside the docker family changes nothing.

A plugin that fails to import is supplied as an entry point, in the same
group as the docker runtime. The family's fixture still validates, the
whole run completes, and what it emits is the family's golden byte for
byte: the neighbour is an absence, named once, and nothing more.
"""
from __future__ import annotations

import logging

from cs_image_system.system import testing as kit


def test_the_family_validates_runs_and_emits_its_golden_beside_a_broken_plugin(
        family_run, golden_dir, monkeypatch, caplog):
    with caplog.at_level(logging.ERROR):
        unusable = kit.broken_neighbour(monkeypatch)
    assert [u.plugin for u in unusable] == ["broken-neighbour"]        # the neighbour, and nothing of the family
    named = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR and "broken-neighbour" in r.getMessage()]
    assert len(named) == 1                                              # said once

    run = family_run()
    assert kit.validation_errors(run.ctx) == []
    summary = run.run("all", apply=True)
    assert summary.ok, summary.error
    kit.assert_matches(golden_dir, kit.emitted(run.generated, run.meta_state),
                       regenerate_with="just golden-regen docker")
