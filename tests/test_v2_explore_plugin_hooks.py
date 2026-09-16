# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""EXPLORE "Expanding What Else Plugins Could Do" (branch
v2-explore-plugin-hooks): plugins participate in the runner through an
entry-point group and may register whole lifecycles.

* ``cs_image_system.plugins.hooks`` entry points are discovered once and
  their HookSets installed (the dummy plugin's notifier fires on summary);
* a plugin-registered lifecycle takes its place in the order, gets its own
  directory, runs hooks, and is a no-op at apply time when it defers nothing;
* registration is validated (no clobbering built-ins, unknown anchors).
"""
from __future__ import annotations

import json

import pytest

from v2_support import V2Run


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def test_hook_plugins_are_discovered_and_notifier_fires(v2, tmp_path, monkeypatch):
    notify = tmp_path / "notify.jsonl"
    monkeypatch.setenv("CSIS_NOTIFY_FILE", str(notify))
    from cs_image_system.base.commands import run_lifecycles as rl
    assert rl.load_hook_plugins(force=True) >= 1
    summary = v2.run(["identity"], apply=False)
    assert summary.ok, summary.error
    lines = [json.loads(l) for l in notify.read_text().splitlines()]
    assert lines[-1]["run"] == summary.run_id and lines[-1]["requested"] == ["identity"]


def test_plugin_registered_lifecycle_participates_like_a_builtin(v2, monkeypatch):
    from cs_image_system.base.commands import run_lifecycles as rl
    from cs_image_system.base.lifecycles import all_lifecycles, parse_lifecycles, unregister_lifecycle
    monkeypatch.setenv("CSIS_DUMMY_LIFECYCLE", "1")
    rl.load_hook_plugins(force=True)
    names = [lc.value for lc in all_lifecycles()]
    assert names[:4] == ["identity", "storage", "base-image", "instance-image"]
    assert "notify" in names
    assert [lc.value for lc in parse_lifecycles(["notify", "identity"])] == ["identity", "notify"]
    summary = v2.run(["notify"], apply=True)
    assert summary.ok, summary.error
    assert [r.lifecycle for r in summary.lifecycles] == ["notify"]
    assert (v2.generated / "notify" / ".gitignore").is_file()
    assert summary.apply["notify"] == "no-script"        # no phases -> nothing deferred -> no-op
    assert "notify" in (v2.generated / "final_execution.sh").read_text()
    unregister_lifecycle("notify")
    assert "notify" not in [lc.value for lc in all_lifecycles()]


def test_lifecycle_registration_is_validated():
    from cs_image_system.base.lifecycles import (
        LifecycleSpec, all_lifecycles, register_lifecycle, unregister_lifecycle)
    with pytest.raises(ValueError, match="built in"):
        register_lifecycle(LifecycleSpec(name="identity"))
    with pytest.raises(ValueError, match="unknown lifecycle"):
        register_lifecycle(LifecycleSpec(name="x", after="nope"))
    spec = register_lifecycle(LifecycleSpec(name="qa", after="instance-image"))
    try:
        order = [lc.value for lc in all_lifecycles()]
        assert order.index("qa") == order.index("instance-image") + 1
        assert register_lifecycle(spec) is spec                     # idempotent
        with pytest.raises(ValueError, match="different definition"):
            register_lifecycle(LifecycleSpec(name="qa", after="identity"))
    finally:
        unregister_lifecycle("qa")
    assert "qa" not in [lc.value for lc in all_lifecycles()]
