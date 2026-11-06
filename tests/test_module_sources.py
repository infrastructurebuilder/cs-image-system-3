# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The terraform modules ship inside their plugin's package.

Each plugin declares its modules directory through the contract's
``cs_image_system.modules`` entry point; the core lists them, writes them
into a tree with a stamp per copy, refreshes only unmodified copies and
refuses an edited one by name; ``config: module_sources`` names a source
for one module at a time and keeps an edit past a refresh.
"""
from __future__ import annotations

from importlib.metadata import entry_points
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from cs_image_system.base import modules as m
from cs_image_system.base.utils import module_source, module_source_overrides
from cs_image_system.contract.modules import MODULES_ENTRY_POINT_GROUP
from cs_image_system.system.cli import app

EXPECTED = {
    "aws-runtime": {"aws_instance", "aws_storage_ebs", "aws_storage_efs", "aws_storage_s3", "bootstrap_aws"},
    "gcloud-runtime": {"gce_instance", "gcp_storage_filestore", "gcp_storage_gcs", "gcp_storage_pd", "bootstrap_gcp"},
    "docker-runtime": {"docker_container", "docker_volume"},
    "okta-opa": {"okta_opa_module"},
    "base": {"bootstrap_github"},
}


# ------------------------------------------------------------ the declaration

def test_every_plugin_ships_its_modules_under_its_namespace():
    installed = m.installed_modules()
    by_namespace: dict[str, set[str]] = {}
    for name, source in installed.items():
        by_namespace.setdefault(source.namespace, set()).add(name)
        assert source.name == name and source.path.is_dir() and any(source.path.glob("*.tf")), name
        assert source.version and source.distribution.startswith("cs-image-system")
    assert by_namespace == EXPECTED
    assert list(installed) == sorted(installed), "deterministic, sorted by name"


def test_every_entry_point_value_resolves_to_an_existing_directory():
    eps = list(entry_points(group=MODULES_ENTRY_POINT_GROUP))
    assert len(eps) == len(EXPECTED), [e.value for e in eps]
    for ep in eps:
        package, sep, dirname = ep.value.partition(":")
        assert sep and dirname == "tfmodules", ep.value
        from importlib.resources import files
        assert Path(str(files(package) / dirname)).is_dir(), ep.value


def test_a_module_two_distributions_ship_is_refused_naming_both(tmp_path: Path, monkeypatch):
    (tmp_path / "pkg_a" / "mods" / "shared").mkdir(parents=True)
    (tmp_path / "pkg_a" / "mods" / "shared" / "main.tf").write_text("a\n")
    (tmp_path / "pkg_b" / "mods" / "shared").mkdir(parents=True)
    (tmp_path / "pkg_b" / "mods" / "shared" / "main.tf").write_text("b\n")

    def fake(group):
        assert group == MODULES_ENTRY_POINT_GROUP
        return [SimpleNamespace(name="modules", value="pkg_a:mods", dist=SimpleNamespace(name="cs-image-system-a-plugin", version="1")),
                SimpleNamespace(name="modules", value="pkg_b:mods", dist=SimpleNamespace(name="cs-image-system-b-plugin", version="1"))]
    monkeypatch.setattr(m, "entry_points", fake)
    monkeypatch.setattr(m, "files", lambda package: tmp_path / package)
    with pytest.raises(ValueError, match="cs-image-system-a-plugin.*cs-image-system-b-plugin"):
        m.installed_modules()


# ------------------------------------------------------------ the resolver

def _ctx(tmp_path: Path, **config) -> Any:
    """A stand-in for the run context: ``module_source`` reads ``config``,
    ``working_path`` and ``generation_path`` and nothing else."""
    root = tmp_path / "cfg-root"
    (root / "generated").mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(config={"module_source_base": "../tfmodules", **config},
                           working_path=root, generation_path=root / "generated")


WS = Path("aws-ebs/storage-generation")


def test_an_override_resolves_for_one_module_and_the_base_for_the_rest(tmp_path: Path):
    ctx = _ctx(tmp_path, module_sources={"aws_instance": "../my-modules/aws_instance"})
    # relative: relative to the configuration root, rewritten for the workspace's depth, nothing appended
    assert module_source(ctx, "aws_instance", WS) == "../../../../my-modules/aws_instance"
    assert module_source(ctx, "aws_storage_ebs", WS) == "../../../../tfmodules/aws_storage_ebs"
    assert module_source(ctx, "aws_instance") == "../my-modules/aws_instance"           # no workspace: as declared


def test_an_absolute_or_remote_override_passes_through_as_the_module(tmp_path: Path):
    ctx = _ctx(tmp_path, module_sources={"aws_instance": "/opt/modules/instance/",
                                         "okta_opa_module": "git::https://example.com/modules.git//okta?ref=v3"})
    assert module_source(ctx, "aws_instance", WS) == "/opt/modules/instance"
    assert module_source(ctx, "okta_opa_module", WS) == "git::https://example.com/modules.git//okta?ref=v3"
    assert module_source(ctx, "docker_volume", WS) == "../../../../tfmodules/docker_volume"


def test_a_bad_module_sources_value_is_refused_by_key(tmp_path: Path):
    with pytest.raises(ValueError, match="module_sources must be a mapping"):
        module_source_overrides(_ctx(tmp_path, module_sources="../mods"))
    with pytest.raises(ValueError, match="'gce_instance' must be a path or URL"):
        module_source(_ctx(tmp_path, module_sources={"gce_instance": ["a"]}), "aws_instance", WS)
    with pytest.raises(ValueError, match="'gce_instance' must be a path or URL"):
        module_source_overrides(_ctx(tmp_path, module_sources={"gce_instance": ""}))
    assert module_source_overrides(_ctx(tmp_path)) == {}


def test_validation_names_a_bad_module_sources_value(tmp_path: Path):
    from cs_image_system.base.v2_validation import validate_module_sources
    assert validate_module_sources(_ctx(tmp_path, module_sources=[1]), []) == [
        "config: module_sources must be a mapping of module name to path or URL, not list"]
    assert validate_module_sources(_ctx(tmp_path, module_sources={"x": "../x"}), []) == []


def test_declared_overrides_reads_the_raw_yaml(tmp_path: Path):
    assert m.declared_overrides(tmp_path) == []
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "_config.yml").write_text("config:\n  module_source_base: tfmodules\n")
    assert m.declared_overrides(tmp_path) == []
    (tmp_path / "cfg" / "_config.yml").write_text(
        "config:\n  module_sources:\n    aws_instance: ../mine/aws_instance\n    okta_opa_module: git::x\n")
    assert m.declared_overrides(tmp_path) == ["aws_instance", "okta_opa_module"]
    (tmp_path / "cfg" / "_config.yml").write_text("config:\n  module_sources: nope\n")
    with pytest.raises(ValueError, match="module_sources must be a mapping"):
        m.declared_overrides(tmp_path)


# ------------------------------------------------------------ the materialisation

def _stamp(copy: Path) -> m.Stamp:
    stamp = m.Stamp.read(copy / m.STAMP_FILE)
    assert stamp is not None, copy
    return stamp


def test_materialise_writes_and_stamps_every_module(tmp_path: Path):
    dest = tmp_path / "tfmodules"
    report = m.materialise_modules(dest)
    assert report.ok and sorted(report.written) == sorted(m.installed_modules()) and not report.kept
    for name, source in m.installed_modules().items():
        stamp = _stamp(dest / name)
        assert stamp == m.Stamp(plugin=source.namespace, release=source.version, hash=m.content_hash(source.path))
        assert m.content_hash(dest / name) == stamp.hash
        assert {p.name for p in (dest / name).iterdir()} == {p.name for p in source.path.iterdir()
                                                                if p.name not in (".DS_Store", "__pycache__")} | {m.STAMP_FILE}
    assert (dest / "aws_instance" / m.STAMP_FILE).read_text().splitlines()[0] == "plugin: aws-runtime"
    assert report.lines()[0].startswith("modules: 14 written, 0 refreshed")
    assert "modules: aws_instance: written from the release" in report.lines()


def test_a_second_materialise_keeps_everything(tmp_path: Path):
    dest = tmp_path / "tfmodules"
    m.materialise_modules(dest)
    again = m.materialise_modules(dest)
    assert again.ok and sorted(again.kept) == sorted(m.installed_modules()) and not again.written and not again.notes


def test_an_unmodified_copy_of_an_older_release_is_refreshed(tmp_path: Path):
    dest = tmp_path / "tfmodules"
    m.materialise_modules(dest)
    copy = dest / "docker_volume"
    (copy / "main.tf").write_text("# an older release's content\n")
    m.Stamp(plugin="docker-runtime", release="0.0.1", hash=m.content_hash(copy)).write(copy / m.STAMP_FILE)
    report = m.materialise_modules(dest)
    assert report.ok and report.refreshed == ["docker_volume"]
    assert (copy / "main.tf").read_bytes() == (m.installed_modules()["docker_volume"].path / "main.tf").read_bytes()
    assert _stamp(copy).hash == m.content_hash(copy)


def test_an_edited_copy_survives_a_refresh_and_is_named_even_with_force(tmp_path: Path):
    dest = tmp_path / "tfmodules"
    m.materialise_modules(dest)
    copy = dest / "aws_instance"
    (copy / "main.tf").write_text("# the team's edit\n")
    for force in (False, True):
        report = m.materialise_modules(dest, force=force)
        assert not report.ok and report.refused == ["aws_instance"]
        assert (copy / "main.tf").read_text() == "# the team's edit\n"
        line = next(x for x in report.lines() if x.startswith("modules: REFUSED aws_instance"))
        assert "config: module_sources (aws_instance: <path or URL>)" in line and "delete the copy" in line
    assert len(report.kept) == 13


def test_an_unstamped_identical_copy_is_adopted(tmp_path: Path):
    dest = tmp_path / "tfmodules"
    m.materialise_modules(dest)
    (dest / "gce_instance" / m.STAMP_FILE).unlink()
    report = m.materialise_modules(dest)
    assert report.ok and report.adopted == ["gce_instance"] and _stamp(dest / "gce_instance").plugin == "gcloud-runtime"


def test_an_unstamped_different_copy_is_refused_without_force_and_replaced_with_it(tmp_path: Path):
    dest = tmp_path / "tfmodules"
    m.materialise_modules(dest)
    copy = dest / "okta_opa_module"
    (copy / m.STAMP_FILE).unlink()
    (copy / "main.tf").write_text("# from before the stamps\n")
    report = m.materialise_modules(dest)
    assert not report.ok and report.refused == ["okta_opa_module"]
    assert "--force overwrites it" in next(x for x in report.lines() if "REFUSED okta_opa_module" in x)
    forced = m.materialise_modules(dest, force=True)
    assert forced.ok and forced.written == ["okta_opa_module"] and any("--force" in n for n in forced.notes)
    assert (copy / "main.tf").read_bytes() == (m.installed_modules()["okta_opa_module"].path / "main.tf").read_bytes()
    assert _stamp(copy).hash == m.content_hash(copy)


def test_an_overridden_module_is_skipped_and_only_narrows(tmp_path: Path):
    dest = tmp_path / "tfmodules"
    report = m.materialise_modules(dest, overrides=["aws_instance"], only=["aws_instance", "docker_volume"])
    assert report.ok and report.skipped == ["aws_instance"] and report.written == ["docker_volume"]
    assert not (dest / "aws_instance").exists() and (dest / "docker_volume" / "main.tf").is_file()
    (dest / "aws_instance").mkdir()
    (dest / "aws_instance" / "main.tf").write_text("# the team's own module\n")
    again = m.materialise_modules(dest, overrides=m.declared_overrides(tmp_path) + ["aws_instance"], force=True)
    assert again.ok and again.skipped == ["aws_instance"]
    assert (dest / "aws_instance" / "main.tf").read_text() == "# the team's own module\n"


def test_content_hash_ignores_the_stamp_and_follows_the_files(tmp_path: Path):
    d = tmp_path / "mod"
    d.mkdir()
    (d / "main.tf").write_text("resource {}\n")
    before = m.content_hash(d)
    assert before.startswith("sha256:")
    m.Stamp(plugin="p", release="r", hash=before).write(d / m.STAMP_FILE)
    (d / ".DS_Store").write_bytes(b"junk")
    (d / "__pycache__").mkdir()
    (d / "__pycache__" / "x.pyc").write_bytes(b"junk")
    assert m.content_hash(d) == before
    (d / "variables.tf").write_text("variable \"x\" {}\n")
    assert m.content_hash(d) != before
    assert m.Stamp.read(d / "main.tf") is None and m.Stamp.read(d / "absent") is None


# ------------------------------------------------------------ the command

def test_the_command_lists_and_writes(tmp_path: Path):
    listed = CliRunner().invoke(app, ["modules"])
    assert listed.exit_code == 0, listed.output
    lines = listed.output.strip().splitlines()
    assert len(lines) == 14 and lines[0].startswith("aws_instance  aws-runtime ")
    assert all(Path(line.split("  ")[-1]).is_dir() for line in lines)
    dest = tmp_path / "tfmodules"
    written = CliRunner().invoke(app, ["modules", "--write", str(dest)])
    assert written.exit_code == 0, written.output
    assert "modules: 14 written" in written.output and (dest / "bootstrap_github" / m.STAMP_FILE).is_file()
    (dest / "bootstrap_github" / "main.tf").write_text("# edited\n")
    refused = CliRunner().invoke(app, ["modules", "--write", str(dest), "--force"])
    assert refused.exit_code == 1 and "REFUSED bootstrap_github" in refused.output


# ------------------------------------------------------------ the dry run's copy

def test_a_relative_override_outside_the_tree_is_copied_beside_the_dry_run_copy(tmp_path: Path):
    from cs_image_system.base.commands.emission import copy_tree_for_a_dry_run
    site = tmp_path / "site"
    root = site / "cfg-repo"
    (root / "cfg").mkdir(parents=True)
    (site / "mine" / "aws_instance").mkdir(parents=True)
    (site / "mine" / "aws_instance" / "main.tf").write_text("mine\n")
    (root / "tfmodules" / "docker_volume").mkdir(parents=True)
    (root / "tfmodules" / "docker_volume" / "main.tf").write_text("inside\n")
    (root / "cfg" / "_config.yml").write_text(
        "config:\n  module_source_base: tfmodules\n  module_sources:\n    aws_instance: ../mine/aws_instance\n"
        "    okta_opa_module: git::https://example.com/m.git//okta\n")
    copy = copy_tree_for_a_dry_run(root, tmp_path / "work")
    assert (copy / "tfmodules" / "docker_volume" / "main.tf").read_text() == "inside\n"
    assert (copy / "../mine/aws_instance/main.tf").resolve().read_text() == "mine\n"
