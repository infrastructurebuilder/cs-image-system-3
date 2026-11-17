# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An installed plugin that cannot be used changes nothing for a
configuration that does not use it, and is named to one that might.

The core's own fixture, with a plugin that fails to import installed
beside it: the configuration loads, validates and emits exactly the core's
golden. The same configuration with a ``type:`` word nothing usable
registers fails as a configuration error, and the lines say that a plugin
is installed and could not be used, and why.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.engine.commands.load_failures import classify_load_failure
from cs_image_system.system import testing as kit
from cs_image_system.system.testing import double, neighbours

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
GOLDEN = HERE / "golden"


def test_the_core_fixture_loads_validates_and_emits_its_golden_beside_a_broken_plugin(tmp_path, monkeypatch):
    [unusable] = kit.broken_neighbour(monkeypatch)
    assert unusable.plugin == neighbours.NEIGHBOUR
    run = kit.Run(tmp_path, monkeypatch, fixture=FIXTURE, stubs=(double.stub,))
    try:
        assert kit.validation_errors(run.ctx) == []
        summary = run.run("all", apply=True)
        assert summary.ok, summary.error
        kit.assert_matches(GOLDEN, kit.emitted(run.generated, run.meta_state), regenerate_with="just golden-regen core")
    finally:
        run.restore_cwd()


def test_a_configuration_that_names_a_word_nothing_usable_registers_is_told_of_the_broken_plugin(
        tmp_path, monkeypatch):
    kit.broken_neighbour(monkeypatch, error="its module is gone")
    kit.stub_core(monkeypatch, FIXTURE / kit.IDENTITY_FILE, (double.stub,))
    root = kit.copy_fixture(FIXTURE, tmp_path)
    declared = root / "cfg" / "runtime-builders.yml"
    declared.write_text(declared.read_text().replace("type: test-double", "type: a-word-of-the-broken-plugin"))
    monkeypatch.chdir(root)
    with pytest.raises(Exception) as failed:
        kit.load_context(root)
    failure = classify_load_failure(failed.value)
    assert failure is not None and failure.kind == "configuration" and failure.code == 1
    said = "\n".join(failure.lines)
    assert "a-word-of-the-broken-plugin" in said
    assert f"{neighbours.NEIGHBOUR} ({neighbours.NEIGHBOUR_DISTRIBUTION})" in said
    assert "its module is gone" in said


def test_the_neighbour_is_gone_when_the_test_that_asked_for_it_ends():
    from cs_image_system.engine import loader
    assert loader.unusable_plugins() == ()
