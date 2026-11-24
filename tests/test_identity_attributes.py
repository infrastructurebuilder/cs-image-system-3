# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Identity attributes: per-item ``managed`` on users, declarable provider
``attributes`` on users and groups, their validation, the attributes plan,
the read-only probe and the (disabled) apply.

Nothing here talks to a provider. The core's path -- declared, validated,
planned, probed, previewed and refused -- is proved over the posix group
pxgroup, its provider a test-local stub at the hook seam. (A provider's own
attribute rules, probe and transport are that provider's tests: the Okta
plugin's live in its own repository.)

History: EXPLORE "User and Group Management", stage 63 low-hanging item 8.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cs_image_system.contract.lifecycles import Lifecycle
from cs_image_system.engine import identity_attributes as ia
from tests.harness import FixtureRun, copy_config, plain


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def overlay(root: Path, *, user_attrs=None, group_attrs=None, managed_user=None, bad=False) -> None:
    def users(d):
        for u in d["users"]:
            if plain(u["name"]) == "avery.alpha":       # the fixture's rosters are encrypted
                if user_attrs is not None:
                    u["attributes"] = user_attrs
                if managed_user is not None:
                    u["managed"] = managed_user
    _edit(root / "groups" / "users.yaml", users)

    def groups(d):
        for g in d["groups"]:
            if g["name"] == "secofs" and group_attrs is not None:
                g["attributes"] = group_attrs
    _edit(root / "groups" / "group-secofs.yaml", groups)


def _run(tmp_path, monkeypatch, **kw) -> FixtureRun:
    root = copy_config(tmp_path)
    overlay(root, **kw)
    return FixtureRun(tmp_path, monkeypatch, config_root=root)


@pytest.fixture
def declared(tmp_path, monkeypatch):
    run = _run(tmp_path, monkeypatch, user_attrs={"unix_uid": 150006, "unix_user_name": "avery.alpha"},
               group_attrs={"unix_gid": 180044})
    try:
        yield run
    finally:
        run.restore_cwd()


def test_models_carry_managed_and_attributes(declared):
    ctx = declared.ctx
    user = next(u for u in ctx.users if u.get_name() == "avery.alpha")
    group = next(g for g in ctx.groups if g.get_name() == "secofs")
    assert user.managed is None and user.attributes == {"unix_uid": 150006, "unix_user_name": "avery.alpha"}
    assert group.attributes == {"unix_gid": 180044}
    assert ia.declared_attributes(ctx) == {
        "groups": {"secofs": {"unix_gid": 180044}},
        "users": {"avery.alpha": {"unix_uid": 150006, "unix_user_name": "avery.alpha"}},
    }


def test_plain_configuration_writes_no_plan_and_no_runner_step(tmp_path, monkeypatch):
    run = FixtureRun(tmp_path, monkeypatch)
    try:
        summary = run.run("identity", apply=False)
        assert summary.ok, summary.error
        assert not ia.plan_path(run.ctx).exists()
        script = run.ctx.runner_script_path(Lifecycle.IDENTITY)   # a POSIX-only tree writes no identity runner
        assert not script.exists() or "identity-attributes" not in script.read_text()
    finally:
        run.restore_cwd()


def test_hooks_are_registered():
    from cs_image_system.engine.commands import run_lifecycles as rl
    assert ia.validate_identity_items in rl._VALIDATORS


# ====================================== the core's path, through a stub provider
# The declare / validate / plan / probe / (disabled) apply path is the core's
# (engine/identity_attributes.py); a plugin only answers its hooks. The posix
# plugin itself refuses attributes (its ids are `gid:` and `uid:`), so here
# its two builders are made to answer as a provider that keeps attributes
# would: a test-local stub at the hook seam, its "provider" a dict.

PX_GROUP, PX_USER = "pxgroup", "taylor_tango"
GROUP_ATTRS = {"login_gid": int, "login_group_name": str}
USER_ATTRS = {"login_uid": int, "login_user_name": str}


class StubProvider:
    """What the provider holds, and every question it was asked."""

    def __init__(self) -> None:
        self.groups: dict[str, dict] = {PX_GROUP: {"login_gid": 180044, "login_group_name": "px_login"}}
        self.users: dict[str, dict] = {PX_USER: {"login_uid": 150099, "login_user_name": PX_USER}}
        self.conflicts: list[dict] = []
        self.down: str | None = None
        self.asked: list[tuple[str, str]] = []

    def answer(self, kind: str, name: str) -> dict | None:
        self.asked.append((kind, name))
        if self.down:
            raise RuntimeError(self.down)
        return dict((self.groups if kind == "group" else self.users).get(name) or {}) or None


def _rules(item: str, attributes: dict, known: dict[str, type]) -> list[str]:
    errors = [f"{item}: {k!r} is not an attribute this provider keeps" for k in attributes if k not in known]
    errors += [f"{item}: {k!r} must be {known[k].__name__}, not {v!r}" for k, v in attributes.items()
               if k in known and not isinstance(v, known[k])]
    errors += [f"{item}: {k!r} = {v} is below 1024" for k, v in attributes.items()
               if known.get(k) is int and isinstance(v, int) and v < 1024]
    return errors


@pytest.fixture
def provider(monkeypatch) -> StubProvider:
    from cs_image_system.posix_identity_plugin.posix_builders import PosixGroupBuilder, PosixUserBuilder
    stub = StubProvider()
    monkeypatch.setattr(PosixGroupBuilder, "validate_attributes",
                        lambda self, g, a: _rules(f"group '{g.get_name()}'", a, GROUP_ATTRS))
    monkeypatch.setattr(PosixUserBuilder, "validate_attributes",
                        lambda self, u, a: _rules(f"user '{u.get_name()}'", a, USER_ATTRS))
    monkeypatch.setattr(PosixGroupBuilder, "query_attributes", lambda self, g: stub.answer("group", g.get_name()))
    monkeypatch.setattr(PosixUserBuilder, "query_attributes", lambda self, u: stub.answer("user", u.get_name()))

    def conflicts(self):
        stub.asked.append(("conflicts", self.get_name()))
        if stub.down:
            raise RuntimeError(stub.down)
        return list(stub.conflicts)
    monkeypatch.setattr(PosixGroupBuilder, "attribute_conflicts", conflicts)
    return stub


def _px_overlay(root: Path, *, group_attrs=None, user_attrs=None) -> None:
    if group_attrs is not None:
        _edit(root / "groups" / "group-pxgroup.yaml",
              lambda d: next(g for g in d["groups"] if g["name"] == PX_GROUP).update({"attributes": group_attrs}))
    if user_attrs is not None:
        _edit(root / "groups" / "users.yaml",
              lambda d: next(u for u in d["users"] if plain(u["name"]) == PX_USER).update({"attributes": user_attrs}))


def _px_run(tmp_path, monkeypatch, **kw) -> FixtureRun:
    root = copy_config(tmp_path)
    _px_overlay(root, **kw)
    return FixtureRun(tmp_path, monkeypatch, config_root=root)


@pytest.fixture
def px_declared(tmp_path, monkeypatch, provider):
    from cs_image_system.posix_identity_plugin.posix_builders import PosixGroupBuilder
    run = _px_run(tmp_path, monkeypatch, group_attrs={"login_gid": 180044},
                  user_attrs={"login_uid": 150006, "login_user_name": PX_USER})

    def no_conflict_report() -> None:
        raise NotImplementedError("not the provider under test")
    for gb in run.ctx.group_builders.values():      # the probe asks every group builder for conflicts:
        if not isinstance(gb, PosixGroupBuilder):   # only the stub answers, and nothing reaches a network
            monkeypatch.setattr(gb, "attribute_conflicts", no_conflict_report)
    try:
        yield run
    finally:
        run.restore_cwd()


def test_a_providers_declared_attributes_are_carried_validated_and_planned(px_declared, provider):
    ctx = px_declared.ctx
    assert ia.declared_attributes(ctx) == {"groups": {PX_GROUP: {"login_gid": 180044}},
                                           "users": {PX_USER: {"login_uid": 150006, "login_user_name": PX_USER}}}
    assert ia.validate_identity_items(ctx, [Lifecycle.IDENTITY]) == []
    summary = px_declared.run("identity", apply=False)
    assert summary.ok, summary.error
    plan = json.loads(ia.plan_path(ctx).read_text())
    assert plan["desired"]["groups"] == {PX_GROUP: {"login_gid": 180044}}
    assert plan["desired"]["users"][PX_USER]["login_uid"] == 150006
    assert provider.asked == [], "planning asks the provider nothing"


def test_a_providers_complaints_about_its_attributes_are_hard_errors(tmp_path, monkeypatch, provider):
    run = _px_run(tmp_path, monkeypatch, user_attrs={"shell": "/bin/zsh", "login_uid": "150006"},
                  group_attrs={"login_gid": 12})
    try:
        text = "\n".join(ia.validate_identity_items(run.ctx, [Lifecycle.IDENTITY]))
        assert "'shell'" in text
        assert "'login_uid'" in text and "int" in text
        assert "'login_gid'" in text and "12" in text
        summary = run.run("identity", apply=False)
        assert not summary.ok and any("login_gid" in e for e in summary.validation_errors)
        assert not ia.plan_path(run.ctx).exists(), "a refused run plans nothing"
    finally:
        run.restore_cwd()


def test_the_probe_only_asks_and_computes_the_changes(px_declared, provider):
    ctx = px_declared.ctx
    probed = ia.probe(ctx, ia.attributes_plan(ctx))
    assert probed["unavailable"] == []
    assert probed["current"]["groups"][PX_GROUP]["login_gid"] == 180044
    assert probed["changes"] == [{"kind": "user", "name": PX_USER, "attribute": "login_uid",
                                  "from": 150099, "to": 150006}]
    assert probed["conflicts"] == []
    assert sorted(provider.asked) == sorted([("group", PX_GROUP), ("user", PX_USER), ("conflicts", "posix-local")])


def test_apply_previews_the_changes_but_never_writes(px_declared, provider):
    ctx = px_declared.ctx
    probed = ia.probe(ctx, ia.attributes_plan(ctx))
    assert ia.apply(ctx, probed, dry_run=True) == [f"user {PX_USER}: login_uid 150099 -> 150006"]
    asked_before = len(provider.asked)
    with pytest.raises(ia.AttributeApplyDisabled):
        ia.apply(ctx, probed, dry_run=False)
    assert len(provider.asked) == asked_before, "the refused apply did not reach the provider"
    probed["conflicts"] = [{"attribute_name": "login_uid", "value": 150006}]
    with pytest.raises(ValueError, match="conflicts"):
        ia.apply(ctx, probed, dry_run=True)


def test_a_provider_that_cannot_answer_is_reported_unavailable(px_declared, provider):
    provider.down = "no route to host"
    probed = ia.probe(px_declared.ctx, ia.attributes_plan(px_declared.ctx))
    assert probed["changes"] == [] and probed["current"] == {"groups": {}, "users": {}}
    assert any(u.startswith(f"groups/{PX_GROUP}") and "no route to host" in u for u in probed["unavailable"])
    assert any(u.startswith(f"users/{PX_USER}") for u in probed["unavailable"])
    assert any(u.startswith("conflicts/posix-local") for u in probed["unavailable"])
    # a provider with no record of the item says so, in its own line
    provider.down = None
    provider.users = {}
    probed = ia.probe(px_declared.ctx, ia.attributes_plan(px_declared.ctx))
    assert f"users/{PX_USER}: no provider record" in probed["unavailable"]
