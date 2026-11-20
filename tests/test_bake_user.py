# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The bake user is decided in one place, in the operator's order.

The three fields (``config_username``, ``default_config_username``,
``default_owners``) are read; the entry beats the runtime's
``ssh_username``; an AWS image entry's user is the most specific; nothing
to name a user is refused at validate; the packer source emits what the
resolver answers.

History: stage 63 items 22 and 23 (decided 2026-09-25).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tests.harness import copy_config, load_context, stub_environment


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _osb(data: dict, name: str) -> dict:
    return next(o for o in data["os_builders"] if o["name"] == name)


def _entry(osb: dict, image_builder: str) -> dict:
    return next(e for e in osb["runtimes"] if e.get("image_builder") == image_builder)


def _runtime(data: dict, name: str) -> dict:
    return next(r for r in data["runtime_builders"] if r["name"] == name)


def _ctx(root: Path, monkeypatch) -> Any:
    stub_environment(monkeypatch)
    return load_context(root)


def _resolve(ctx: Any, image_name: str, runtime: str) -> str:
    from cs_image_system.base.bake_user import entry_for_runtime, resolve_bake_user, resolve_for_entry
    if image_name in ctx.os_builders:
        osb = ctx.os_builders[image_name]
        return resolve_for_entry(ctx, osb, entry_for_runtime(ctx, osb, runtime), runtime)
    return resolve_bake_user(ctx, ctx.images_map[image_name], runtime)


# ------------------------------------------------ the order, as it stands

def test_the_fixture_resolves_as_it_always_baked(tmp_path: Path, monkeypatch):
    """Pins what held: the golden did not move, and these are its users."""
    ctx = _ctx(copy_config(tmp_path), monkeypatch)
    assert _resolve(ctx, "basic-rhel-9", "aws-east2-runtime") == "ec2-user"   # family default
    assert _resolve(ctx, "my-deb-12", "aws-east2-runtime") == "admin"
    assert _resolve(ctx, "imgfile-data-science", "aws-east2-runtime") == "admin"


# ------------------------------- 22. the two config_username fields live

def test_config_username_is_read_and_beats_the_runtimes_ssh_username(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "os-builders.yml", lambda d: _osb(d, "basic-rhel-9").update(config_username="cloud-user"))
    _edit(root / "cfg" / "runtime-builders.yml",
          lambda d: _runtime(d, "aws-east2-runtime").update(ssh_username="runtime-user"))
    ctx = _ctx(root, monkeypatch)
    assert _resolve(ctx, "basic-rhel-9", "aws-east2-runtime") == "cloud-user"
    # an OS builder without config_username falls to the runtime's user
    assert _resolve(ctx, "basic-rh-10", "aws-east2-runtime") == "runtime-user"


def test_default_config_username_is_the_runtimes_fallback(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "runtime-builders.yml",
          lambda d: _runtime(d, "aws-east2-runtime").update(default_config_username="rocky"))
    ctx = _ctx(root, monkeypatch)
    assert _resolve(ctx, "basic-rhel-9", "aws-east2-runtime") == "rocky"
    assert _resolve(ctx, "my-deb-12", "aws-east2-runtime") == "rocky"


def test_a_runtimes_default_owners_join_the_entrys_owners(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "runtime-builders.yml",
          lambda d: _runtime(d, "aws-east2-runtime").update(default_owners=["111122223333"]))
    ctx = _ctx(root, monkeypatch)
    osb = ctx.os_builders["basic-rhel-9"]
    entry = next(e for e in osb.get_configs_for_image_builders().values()
                 if e.get_image_builder() == "pckr-ebs-ans")
    owners = list(entry.get_owners())
    assert "111122223333" in owners and len(owners) == len(set(owners)), owners


def test_nothing_to_name_a_user_is_refused_at_validate(tmp_path: Path, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.engine.commands.validate import check_bake_users
    monkeypatch.setattr(AwsCloudBuilder, "default_bake_user", lambda self, family: None)
    ctx = _ctx(copy_config(tmp_path), monkeypatch)
    errors = [str(e) for e in check_bake_users(ctx)]
    assert any("basic-rhel-9" in e and "aws-east2-runtime" in e and "config_username" in e for e in errors), errors


# ------------------------------------------------------ 23. the entry wins

def test_the_fixture_has_no_bake_user_finding(tmp_path: Path, monkeypatch):
    from cs_image_system.engine.commands.validate import check_bake_users
    ctx = _ctx(copy_config(tmp_path), monkeypatch)
    assert check_bake_users(ctx) == []


def test_an_aws_image_entry_user_is_the_most_specific(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)

    def edit(d):
        dask = next(i for i in d["images"] if i["name"] == "imgfile-basic-dask")
        next(r for r in dask["runtimes"] if r["image_builder"] == "pckr-ebs-ans")["ssh_username"] = "dask-user"
    _edit(root / "images" / "image1.yaml", edit)
    ctx = _ctx(root, monkeypatch)
    assert _resolve(ctx, "imgfile-basic-dask", "aws-east2-runtime") == "dask-user"


def test_the_resolver_is_what_the_source_emits(tmp_path: Path, monkeypatch):
    """The packer source no longer carries its own fallback."""
    import inspect

    from cs_image_system.aws_runtime import aws_packer_source
    src = inspect.getsource(aws_packer_source)
    assert "resolve_bake_user(" in src and "model.ssh_username" not in src, aws_packer_source.__name__
