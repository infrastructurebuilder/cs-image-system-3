# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 84: a new group can be created.

Found walking the daily driver (stage 65, finding F22): the identity root's
gid lookup (`data "external" "group_gids"`, DESIGN N7) ran at PLAN time with
no dependency on the group's module, so for a group that did not exist yet
it found no gid and failed -- and the plan that would create the group could
never succeed. The lookup now depends on every managed group's module
(terraform reads it during the apply that creates a group), and waits,
bounded, for OPA to give a new group its gid.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.v2_support import V2Run, copy_config


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path))
    try:
        yield r
    finally:
        r.restore_cwd()


def test_the_gid_lookup_depends_on_every_managed_groups_module(run):
    assert run.run(["identity"], apply=False).ok
    checked = 0
    for path in sorted((run.generated / "identity").rglob("*outputs.tf")):
        outputs = path.read_text()
        if 'data "external" "group_gids"' not in outputs:
            continue
        block = outputs[outputs.index('data "external" "group_gids"'):outputs.index('output "group_gids"')]
        assert block.index("depends_on") < block.index("program"), block
        listed = set(re.findall(r"module\.group_\w+", block[block.index("depends_on"):block.index("program")]))
        # every managed group of the root: the modules its `groups` output reads
        modules = set(re.findall(r"module\.group_\w+", outputs[outputs.index('output "groups"'):]))
        assert listed and listed == modules, (path.name, listed, modules)
        checked += 1
    assert checked, "the fixture has an identity root with managed okta groups"


class _Resolver:
    """Answers nothing for `late` until it has been asked `after` times."""
    def __init__(self, gids: dict[str, int], late: str | None = None, after: int = 0):
        self.gids, self.late, self.after, self.asked = gids, late, after, []

    def resolve(self, groups: list[str]) -> dict[str, int]:
        self.asked.append(list(groups))
        ready = len(self.asked) > self.after
        return {g: self.gids[g] for g in groups if g in self.gids and (g != self.late or ready)}


class _Time:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_a_group_that_stands_is_answered_at_once():
    from cs_image_system.okta_opa_plugin.opa_gids import resolve_waiting
    r, t = _Resolver({"coops": 180007}), _Time()
    assert resolve_waiting(r, ["coops"], wait_seconds=30, sleep=t.sleep, clock=t.clock) == {"coops": 180007}  # type: ignore[arg-type]
    assert r.asked == [["coops"]] and t.slept == []


def test_a_new_groups_gid_is_asked_for_again_until_opa_has_it():
    from cs_image_system.okta_opa_plugin.opa_gids import resolve_waiting
    r, t = _Resolver({"coops": 180007, "walk_team": 180042}, late="walk_team", after=2), _Time()
    got = resolve_waiting(r, ["coops", "walk_team"], wait_seconds=30, step=5, sleep=t.sleep, clock=t.clock)  # type: ignore[arg-type]
    assert got == {"coops": 180007, "walk_team": 180042}
    assert r.asked == [["coops", "walk_team"], ["walk_team"], ["walk_team"]]     # only the missing one is asked again
    assert t.slept == [5, 5]


def test_the_wait_is_bounded_and_never_invents_a_gid():
    from cs_image_system.okta_opa_plugin.opa_gids import resolve_waiting
    r, t = _Resolver({"coops": 180007}), _Time()
    got = resolve_waiting(r, ["coops", "ghost"], wait_seconds=12, step=5, sleep=t.sleep, clock=t.clock)  # type: ignore[arg-type]
    assert got == {"coops": 180007}                      # still absent: the caller refuses loudly, as before
    assert t.slept == [5, 5, 2] and t.now == 12
    r, t = _Resolver({}), _Time()
    assert resolve_waiting(r, ["ghost"], wait_seconds=0, sleep=t.sleep, clock=t.clock) == {}  # type: ignore[arg-type]
    assert r.asked == [["ghost"]] and t.slept == []      # 0: ask once


def test_the_bound_comes_from_the_environment():
    from cs_image_system.okta_opa_plugin.opa_gids import GID_WAIT_SECONDS, gid_wait_seconds
    assert gid_wait_seconds({}) == GID_WAIT_SECONDS == 30
    assert gid_wait_seconds({"CSIS_GID_WAIT_SECONDS": "0"}) == 0
    assert gid_wait_seconds({"CSIS_GID_WAIT_SECONDS": "90"}) == 90
    assert gid_wait_seconds({"CSIS_GID_WAIT_SECONDS": "-5"}) == 0
    with pytest.raises(ValueError, match="CSIS_GID_WAIT_SECONDS must be a number"):
        gid_wait_seconds({"CSIS_GID_WAIT_SECONDS": "soon"})


def test_the_shim_refuses_loudly_when_the_wait_ends_without_a_gid(monkeypatch):
    """End to end through `export-gids`: what terraform's external program
    gets when a group still has no gid after the bounded wait."""
    from cs_image_system.base.commands.identity_gids import export_gids
    from cs_image_system.okta_opa_plugin import okta_opa_tf_group_builder as mod
    seen: dict[str, object] = {}

    def waiting(resolver, groups, **kw):
        seen["groups"] = list(groups)
        return {"coops": 180007}

    monkeypatch.setenv("TF_VAR_t_key", "k")
    monkeypatch.setenv("TF_VAR_t_secret", "s")
    monkeypatch.setattr(mod, "resolve_waiting", waiting)
    query = {"identity_type": "okta", "team": "t", "api_host": "https://h", "groups": "coops,walk_team"}
    with pytest.raises(ValueError, match=r"reported no gid for groups \['walk_team'\]"):
        export_gids(query)
    assert seen["groups"] == ["coops", "walk_team"]
    assert export_gids({**query, "groups": "coops"}) == {"coops": "180007"}
