# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A tree whose identity is this plugin's alone (stage 128, item 6): the
`dummy` group builder and the `dummy` user builder, one group on them and
nothing of the fixture's Okta or posix identity. It loads, validates and
runs the identity lifecycle dry: the group builder writes nothing, the user
builder one comment-only file under its own root -- the template's
documented shape (CONFIGURATION.md 9.2)."""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from harness import V2Run, copy_config

GROUPS = "dummy-groups"
USERS = "dummy-users"
GROUP = "dummygroup"


def _write(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def dummy_only_identity(root: Path) -> None:
    """Prune a copy of the frozen fixture to the template builders and one
    group: the images, instances and storages that belong to the fixture's
    groups go with those groups (a base image needs no group)."""
    _write(root / "cfg" / "group-builders.yml", {
        "group_builders": [{"name": GROUPS, "type": "dummy", "is_default": True, "org": "example", "team": "example"}],
        "user_builders": [{"name": USERS, "type": "dummy", "is_default": True, "org": "example", "team": "example"}]})
    for p in (root / "groups").iterdir():
        p.unlink()
    _write(root / "groups" / "group-dummy.yaml", {"groups": [
        {"name": GROUP, "type": GROUPS, "is_root": True, "description": "the one group, on the template builder"}]})
    _write(root / "groups" / "users.yaml", {"users": []})
    for sub in ("images", "instances", "storages"):
        shutil.rmtree(root / sub)
        (root / sub).mkdir()
    # a base declares the identity types its images may carry: here the template's alone
    def dummy_identity(d):
        for base in d["os_builders"]:
            base["identity_types"] = ["dummy"]
    data = yaml.safe_load((root / "cfg" / "os-builders.yml").read_text())
    dummy_identity(data)
    _write(root / "cfg" / "os-builders.yml", data)


def test_the_template_builders_load_validate_and_run_the_identity_lifecycle_dry(tmp_path, monkeypatch):
    from cs_image_system.base.commands.validate import collect_validation_errors
    from cs_image_system.dummy_plugin.dummy_builders import DummyGroupBuilder, DummyUserBuilder
    root = copy_config(tmp_path)
    dummy_only_identity(root)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert set(run.ctx.group_builders) == {GROUPS} and set(run.ctx.user_builders) == {USERS}
        assert isinstance(run.ctx.group_builders[GROUPS], DummyGroupBuilder)
        assert isinstance(run.ctx.user_builders[USERS], DummyUserBuilder)
        assert [g.get_name() for g in run.ctx.groups] == [GROUP]
        problems = collect_validation_errors(run.ctx)
        assert problems == [], problems
        summary = run.run(["identity"], apply=False)
        assert summary.ok, summary.error
        written = sorted(p.relative_to(run.generated) for p in run.generated.rglob("*.tf"))
        assert written == [Path("identity") / USERS / "user-generation" / f"{USERS}-user-generation-users.tf"], written
        text = (run.generated / written[0]).read_text()
        assert text.strip() and all(line.startswith("#") or not line.strip() for line in text.splitlines()), text
        assert not (run.generated / "identity" / GROUPS).exists() or \
            not any(p.is_file() for p in (run.generated / "identity" / GROUPS).rglob("*")), "the group builder wrote"
    finally:
        run.restore_cwd()
