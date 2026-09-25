# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 63, the second chain (22 then 23): the bake user is decided in one
place, in the operator's order (decided 2026-09-25), the three dead fields
(`config_username`, `default_config_username`, `default_owners`) are read,
and a GCE chain bakes and provisions as one user. Every test here failed
before its fix, except the ones marked as pinning what already held.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tests.v2_support import V2Run, copy_config, load_context, reset_singletons, stub_environment


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
    from cs_image_system.base.bake_user import resolve_bake_user, resolve_for_entry, entry_for_runtime
    if image_name in ctx.os_builders:
        osb = ctx.os_builders[image_name]
        return resolve_for_entry(ctx, osb, entry_for_runtime(ctx, osb, runtime), runtime)
    return resolve_bake_user(ctx, ctx.images_map[image_name], runtime)


# ------------------------------------------------ the order, as it stands

def test_the_fixture_resolves_as_it_always_baked(tmp_path: Path, monkeypatch):
    """Pins what held: the golden did not move, and these are its users."""
    ctx = _ctx(copy_config(tmp_path), monkeypatch)
    try:
        assert _resolve(ctx, "basic-rhel-9", "aws-east2-runtime") == "ec2-user"   # family default
        assert _resolve(ctx, "my-deb-11", "aws-east2-runtime") == "admin"
        assert _resolve(ctx, "basic-rh-10", "gcloud-east1") == "packer"           # the entry
        assert _resolve(ctx, "imgfile-basic-dask", "gcloud-east1") == "packer"    # via its root
        assert _resolve(ctx, "imgfile-data-science", "aws-east2-runtime") == "admin"
    finally:
        reset_singletons()


# ------------------------------- 22. the two config_username fields live

def test_config_username_is_read_and_beats_the_runtimes_ssh_username(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "os-builders.yml", lambda d: _osb(d, "basic-rhel-9").update(config_username="cloud-user"))
    _edit(root / "cfg" / "runtime-builders.yml",
          lambda d: _runtime(d, "aws-east2-runtime").update(ssh_username="runtime-user"))
    ctx = _ctx(root, monkeypatch)
    try:
        assert _resolve(ctx, "basic-rhel-9", "aws-east2-runtime") == "cloud-user"
        # an OS builder without config_username falls to the runtime's user
        assert _resolve(ctx, "basic-rh-10", "aws-east2-runtime") == "runtime-user"
    finally:
        reset_singletons()


def test_default_config_username_is_the_runtimes_fallback(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "runtime-builders.yml",
          lambda d: _runtime(d, "aws-east2-runtime").update(default_config_username="rocky"))
    ctx = _ctx(root, monkeypatch)
    try:
        assert _resolve(ctx, "basic-rhel-9", "aws-east2-runtime") == "rocky"
        assert _resolve(ctx, "my-deb-11", "aws-east2-runtime") == "rocky"
    finally:
        reset_singletons()


def test_a_runtimes_default_owners_join_the_entrys_owners(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "runtime-builders.yml",
          lambda d: _runtime(d, "aws-east2-runtime").update(default_owners=["111122223333"]))
    ctx = _ctx(root, monkeypatch)
    try:
        osb = ctx.os_builders["basic-rhel-9"]
        entry = next(e for e in osb.get_configs_for_image_builders().values()
                     if e.get_image_builder() == "pckr-ebs-ans")
        owners = list(entry.get_owners())
        assert "111122223333" in owners and len(owners) == len(set(owners)), owners
    finally:
        reset_singletons()


def test_nothing_to_name_a_user_is_refused_at_validate(tmp_path: Path, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.base.commands.validate import check_bake_users
    monkeypatch.setattr(AwsCloudBuilder, "default_bake_user", lambda self, family: None)
    ctx = _ctx(copy_config(tmp_path), monkeypatch)
    try:
        errors = [str(e) for e in check_bake_users(ctx)]
        assert any("the ssh user for OS builder basic-rhel-9 on runtime aws-east2-runtime could not be "
                   "inferred" in e and "config_username" in e for e in errors), errors
    finally:
        reset_singletons()


# ------------------------------------ 23. the entry wins; one user per chain

def test_the_entry_beats_the_runtimes_ssh_username(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "runtime-builders.yml",
          lambda d: _runtime(d, "gcloud-east1").update(ssh_username="runtime-user"))
    ctx = _ctx(root, monkeypatch)
    try:
        # the GCE entry declares `packer`; the runtime's value used to override it
        assert _resolve(ctx, "basic-rh-10", "gcloud-east1") == "packer"
    finally:
        reset_singletons()


def test_the_gce_provisioner_connects_as_the_user_the_source_bakes_as(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _edit(root / "cfg" / "os-builders.yml",
          lambda d: _entry(_osb(d, "basic-rh-10"), "pckr-gce-ans").update(ssh_username="builder"))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert run.run(["base-image", "instance-image"], apply=False).ok
        gce = "".join(p.read_text() for p in run.generated.rglob("*.pkr.hcl") if "pckr-gce-ans" in str(p))
        assert 'ssh_username = "builder"' in gce, "the source bakes as the entry's user"
        assert 'user = "builder"' in gce and 'user = "packer"' not in gce, \
            "the ansible provisioner connects as the same user (it said packer)"
    finally:
        run.restore_cwd()


def test_a_gce_image_naming_another_user_than_its_root_is_refused(tmp_path: Path, monkeypatch):
    from cs_image_system.base.commands.validate import check_bake_users
    root = copy_config(tmp_path)

    def edit(d):
        dask = next(i for i in d["images"] if i["name"] == "imgfile-basic-dask")
        next(r for r in dask["runtimes"] if r["image_builder"] == "pckr-gce-ans")["ssh_username"] = "other"
    _edit(root / "images" / "image1.yaml", edit)
    ctx = _ctx(root, monkeypatch)
    try:
        errors = [str(e) for e in check_bake_users(ctx)]
        assert any("image 'imgfile-basic-dask' bakes as 'other' on runtime gcloud-east1" in e
                   and "'basic-rh-10' bakes as 'packer'" in e for e in errors), errors
        # the same pair on AWS is allowed: AWS needs no one-user chain
        assert not any("aws-east2-runtime" in e for e in errors), errors
    finally:
        reset_singletons()


def test_the_fixture_has_no_bake_user_finding(tmp_path: Path, monkeypatch):
    from cs_image_system.base.commands.validate import check_bake_users
    ctx = _ctx(copy_config(tmp_path), monkeypatch)
    try:
        assert check_bake_users(ctx) == []
    finally:
        reset_singletons()


def test_an_aws_image_entry_user_is_the_most_specific(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)

    def edit(d):
        dask = next(i for i in d["images"] if i["name"] == "imgfile-basic-dask")
        next(r for r in dask["runtimes"] if r["image_builder"] == "pckr-ebs-ans")["ssh_username"] = "dask-user"
    _edit(root / "images" / "image1.yaml", edit)
    ctx = _ctx(root, monkeypatch)
    try:
        assert _resolve(ctx, "imgfile-basic-dask", "aws-east2-runtime") == "dask-user"
    finally:
        reset_singletons()


def test_the_resolver_is_what_both_sources_emit(tmp_path: Path, monkeypatch):
    """The two packer sources no longer carry their own fallbacks."""
    import inspect
    from cs_image_system.aws_runtime import aws_packer_source
    from cs_image_system.gcloud_runtime import gcp_packer_source
    for mod in (aws_packer_source, gcp_packer_source):
        src = inspect.getsource(mod)
        assert "resolve_bake_user(" in src and "model.ssh_username" not in src, mod.__name__
