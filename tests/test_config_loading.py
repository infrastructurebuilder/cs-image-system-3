# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Loading a configuration: what the loader refuses, reads and builds.

* a registry collision is named without the models' repr; a Python tag in
  the configuration is refused, not constructed (the reader is
  ``yaml.safe_load``);
* preflight finds a runtime declared in any cfg file, because the loaded
  configuration reads every cfg file alike;
* a load without a root is refused before any plugin loads, and the root
  is the working directory whatever ``working_directory`` names; a verbose
  load writes its rendered document under the root's ``_private/``, not
  into the directory it was started from;
* ``dateformat`` has one default and it is the one the run uses; an
  executable builds its command once.

History: stage 63 low-hanging items 5, 11 and 13, dead-code item 11; hygiene XXVI items 1 and 4.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml
from harness import copy_config, load_context, stub_environment


def test_a_registry_collision_is_named_without_the_models_repr(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    sb = root / "cfg" / "state-backends-2.yml"
    data = yaml.safe_load(sb.read_text())
    twin = dict(data["state_backends"][0])
    twin["name"] = twin["name"].upper()          # normalises to the same registry key
    twin.pop("is_default", None)
    data["state_backends"].append(twin)
    sb.write_text(yaml.safe_dump(data, sort_keys=False))
    stub_environment(monkeypatch)
    with pytest.raises(ValueError) as exc:
        load_context(root)
    message = str(exc.value)
    assert "collide" in message, message
    assert "TofuS3StateBuilderModel(" not in message and "bucket=" not in message, "no repr, no field values"


def test_a_python_tag_in_the_configuration_is_refused_not_constructed(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    (root / "cfg" / "zz-tag.yml").write_text("evil: !!python/object/apply:os.system ['echo pwned']\n")
    stub_environment(monkeypatch)
    with pytest.raises(Exception) as exc:
        load_context(root)
    assert "python/object" in str(exc.value) or "could not determine a constructor" in str(exc.value), str(exc.value)
    from cs_image_system.base import config_loader  # the reader lives in the loader
    src = Path(config_loader.__file__).read_text()
    assert "yaml.unsafe_load(stream)" not in src and "yaml.safe_load(stream)" in src


def test_preflight_finds_a_runtime_declared_in_any_cfg_file(tmp_path: Path, monkeypatch):
    """The sessions are read over the loaded configuration, which
    reads every cfg file alike; a session that is absent never stops the load."""
    from cs_image_system.base.commands.preflight import session_infos
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    src = root / "cfg" / "runtime-builders.yml"
    before = {i.runtime for i in session_infos(load_context(root))}
    assert before, "the fixture's runtimes are preflighted from their own file"
    (root / "cfg" / "clouds.yaml").write_text(src.read_text())      # the same declarations, another file name
    src.unlink()
    after = {i.runtime for i in session_infos(load_context(root))}
    assert after == before, f"{after} != {before}: a runtime declared in another cfg file is preflighted too"


# ----------------------------------------------------- the root

def test_a_load_without_a_root_is_refused_before_any_plugin_loads(monkeypatch):
    from cs_image_system.base import config_loader
    loaded: list[Any] = []
    catalogs: list[Any] = []
    monkeypatch.setattr(config_loader, "load_plugins", loaded.append)
    monkeypatch.setattr(config_loader, "ImageSourceCatalog", catalogs.append)
    typer_cntx = SimpleNamespace(obj={"invoked_cwd": "kept"})
    with pytest.raises(ValueError, match="Root directory"):
        config_loader.read_config_and_transform(cast(Any, typer_cntx), cast(Any, None))
    assert loaded == [] and catalogs == []
    assert typer_cntx.obj == {"invoked_cwd": "kept"}


def test_the_root_is_the_working_directory_whatever_the_configuration_names(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    cfg = root / "cfg" / "_config.yml"
    cfg.write_text(cfg.read_text() + "working_directory: ./elsewhere\n")
    stub_environment(monkeypatch)
    monkeypatch.chdir(tmp_path)
    ctx = load_context(root)
    assert ctx.working_path == root.resolve()
    assert Path.cwd() == root.resolve()
    assert not (root / "elsewhere").exists() and not (tmp_path / "elsewhere").exists()


def test_a_verbose_load_dumps_the_rendered_document_under_the_roots_private_directory(tmp_path: Path, monkeypatch):
    from cs_image_system.base import config_loader
    from cs_image_system.base.materialize import PRIVATE_DIRNAME
    root = copy_config(tmp_path)
    invoking = tmp_path / "invoking"
    invoking.mkdir()
    assert not (root / PRIVATE_DIRNAME).exists()
    stub_environment(monkeypatch)
    monkeypatch.chdir(invoking)
    config_loader.read_config_and_transform(cast(Any, SimpleNamespace(obj={})), root, True,
                                            dry_run=True, overlays=[], undeclare=[])
    dump = yaml.safe_load((root / PRIVATE_DIRNAME / config_loader.VERBOSE_DUMP).read_text())
    assert dump["id"] == yaml.safe_load((root / "cfg" / "_config.yml").read_text())["id"]
    assert list(invoking.iterdir()) == [], "the invoking directory is left alone"
    assert not (root / config_loader.VERBOSE_DUMP).exists()


# ----------------------------------------------------- the base models

def test_dateformat_has_one_default_and_it_is_the_one_the_run_uses():
    from cs_image_system.base.models.ia_config import DEFAULT_DATEFORMAT, IAConfig
    assert DEFAULT_DATEFORMAT == "%Y%m%d_%H%M%S"
    assert IAConfig.__dataclass_fields__["dateformat"].default == DEFAULT_DATEFORMAT
    assert "last_updated" not in IAConfig.__dataclass_fields__


def test_an_executable_builds_its_command_once(monkeypatch, tmp_path: Path):
    import subprocess

    from cs_image_system.base.models.executable import ExecutableModel
    seen: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0, "", ""))
    e = ExecutableModel(name="tool", type_="executable", binary="/bin/echo")
    e.prepended_arguments = ["-n"]
    e.args = ["a"]
    e.execute("b")
    assert seen == [["/bin/echo", "-n", "a", "b"]], seen

