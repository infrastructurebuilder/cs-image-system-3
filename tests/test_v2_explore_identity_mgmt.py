# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""EXPLORE "User and Group Management": per-item ``managed`` on users,
declarable provider ``attributes`` on users and groups, their validation,
the attributes plan, the read-only probe and the (disabled) apply.

Nothing here talks to Okta or OPA: the OPA client is driven through a fake
transport.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, copy_config, plain

from cs_image_system.base import identity_attributes as ia
from cs_image_system.base.lifecycles import Lifecycle


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def overlay(root: Path, *, user_attrs=None, group_attrs=None, managed_user=None, bad=False) -> None:
    def users(d):
        for u in d["users"]:
            if plain(u["name"]) == "avery.alpha":       # the fixture's rosters are encrypted (stage 33)
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


def _run(tmp_path, monkeypatch, **kw) -> V2Run:
    root = copy_config(tmp_path)
    overlay(root, **kw)
    return V2Run(tmp_path, monkeypatch, config_root=root)


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


def test_valid_declarations_pass_and_plan_is_written(declared):
    ctx = declared.ctx
    assert ia.validate_identity_items(ctx, [Lifecycle.IDENTITY]) == []
    summary = declared.run("identity", apply=False)
    assert summary.ok, summary.error
    plan = json.loads(ia.plan_path(ctx).read_text())
    assert plan["desired"]["groups"] == {"secofs": {"unix_gid": 180044}}
    assert plan["desired"]["users"]["avery.alpha"]["unix_uid"] == 150006
    # the runner script carries the read-only probe / apply preview step
    script = ctx.runner_script_path(Lifecycle.IDENTITY).read_text()
    assert "identity-attributes --probe --dry-run-apply" in script


def test_plain_configuration_writes_no_plan_and_no_runner_step(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        summary = run.run("identity", apply=False)
        assert summary.ok, summary.error
        assert not ia.plan_path(run.ctx).exists()
        assert "identity-attributes" not in run.ctx.runner_script_path(Lifecycle.IDENTITY).read_text()
    finally:
        run.restore_cwd()


def test_unknown_and_mistyped_attributes_are_hard_errors(tmp_path, monkeypatch):
    run = _run(tmp_path, monkeypatch, user_attrs={"shell": "/bin/zsh", "unix_uid": "150006"},
               group_attrs={"unix_gid": 12})
    try:
        errors = ia.validate_identity_items(run.ctx, [Lifecycle.IDENTITY])
        text = "\n".join(errors)
        assert "unknown OPA attribute 'shell'" in text
        assert "'unix_uid' must be int" in text
        assert "'unix_gid' = 12 is below the reserved range" in text
        summary = run.run("identity", apply=False)
        assert not summary.ok and any("unix_gid" in e for e in summary.validation_errors)
    finally:
        run.restore_cwd()


def test_read_only_builder_refuses_managed_true(tmp_path, monkeypatch):
    run = _run(tmp_path, monkeypatch, managed_user=True)
    try:
        errors = ia.validate_identity_items(run.ctx, [Lifecycle.IDENTITY])
        assert len(errors) == 1 and "okta-tf-ro" in errors[0] and "cannot" in errors[0]
    finally:
        run.restore_cwd()


def test_managed_default_follows_the_builder_type(tmp_path, monkeypatch):
    from cs_image_system.okta_opa_plugin.okta_opa_tf_user_builder import OktaTfUserBuilder
    from cs_image_system.okta_opa_plugin.okta_opa_tf_user_ro_builder import OktaTfUserRoBuilder
    assert OktaTfUserBuilder.default_managed() is True
    assert OktaTfUserRoBuilder.default_managed() is False
    run = V2Run(tmp_path, monkeypatch)
    try:
        summary = run.run("identity", apply=False)
        assert summary.ok, summary.error
        users_tf = list((run.generated / "identity").rglob("*users*.tf"))
        texts = "\n".join(p.read_text() for p in users_tf)
        assert 'data "okta_user"' in texts and 'resource "okta_user"' not in texts   # RO: lookups only
    finally:
        run.restore_cwd()


class FakeOpa:
    """Transport for OpaGidResolver: canned answers, records every call."""

    def __init__(self, groups: dict[str, dict], users: dict[str, dict], conflicts=()):
        self.groups, self.users, self.conflicts = groups, users, list(conflicts)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        assert method in ("GET", "POST"), "the probe must never write"
        if url.endswith("/service_token"):
            return {"bearer_token": "t"}
        if url.endswith("/attributes/conflicts"):
            return {"list": self.conflicts}
        for kind, table in (("groups", self.groups), ("users", self.users)):
            marker = f"/{kind}/"
            if marker in url and url.endswith("/attributes"):
                name = url.split(marker)[1].rsplit("/attributes", 1)[0]
                rec = table.get(name)
                if rec is None:
                    raise RuntimeError("404")
                return {"attributes": {k: {"attribute_name": k, "attribute_value": v, "managed": False}
                                       for k, v in rec.items()}}
        raise RuntimeError(f"unexpected {url}")


@pytest.fixture
def opa(monkeypatch):
    from cs_image_system.okta_opa_plugin import opa_gids
    fake = FakeOpa(groups={"secofs_user": {"unix_gid": 180044, "unix_group_name": "sft_secofs_user"}},
                   users={"avery.alpha": {"unix_uid": 150099, "unix_user_name": "avery.alpha"}})
    monkeypatch.setattr(opa_gids, "_urllib_transport", fake)
    return fake


def test_probe_reads_only_and_computes_changes(declared, opa):
    ctx = declared.ctx
    probed = ia.probe(ctx, ia.attributes_plan(ctx))
    assert probed["unavailable"] == []
    assert probed["current"]["groups"]["secofs"]["unix_gid"] == 180044
    assert probed["changes"] == [{"kind": "user", "name": "avery.alpha", "attribute": "unix_uid",
                                  "from": 150099, "to": 150006}]
    assert probed["conflicts"] == []
    assert all(m == "GET" or u.endswith("/service_token") for m, u in opa.calls)


def test_apply_previews_but_never_writes(declared, opa):
    ctx = declared.ctx
    probed = ia.probe(ctx, ia.attributes_plan(ctx))
    assert ia.apply(ctx, probed, dry_run=True) == ["user avery.alpha: unix_uid 150099 -> 150006"]
    calls_before = len(opa.calls)
    with pytest.raises(ia.AttributeApplyDisabled):
        ia.apply(ctx, probed, dry_run=False)
    assert len(opa.calls) == calls_before
    probed["conflicts"] = [{"attribute_name": "unix_uid", "value": 150006}]
    with pytest.raises(ValueError):
        ia.apply(ctx, probed, dry_run=True)


def test_unavailable_provider_is_reported(declared, monkeypatch):
    from cs_image_system.okta_opa_plugin import opa_gids

    def down(method, url, headers, body):
        raise RuntimeError("no route to host")
    monkeypatch.setattr(opa_gids, "_urllib_transport", down)
    probed = ia.probe(declared.ctx, ia.attributes_plan(declared.ctx))
    assert probed["changes"] == [] and probed["current"] == {"groups": {}, "users": {}}
    assert any(u.startswith("groups/secofs") for u in probed["unavailable"])
    assert any(u.startswith("users/avery.alpha") for u in probed["unavailable"])


def test_hooks_are_registered():
    from cs_image_system.base.commands import run_lifecycles as rl
    assert ia.validate_identity_items in rl._VALIDATORS
