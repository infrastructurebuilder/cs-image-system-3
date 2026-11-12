# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Loading a configuration: what the loader refuses, reads and builds.

* a registry collision is named without the models' repr; a Python tag in
  the configuration is refused, not constructed (the reader is
  ``yaml.safe_load``);
* preflight finds a runtime declared in any cfg file, because the loaded
  configuration reads every cfg file alike;
* ``dateformat`` has one default and it is the one the run uses; an
  executable builds its command once.

History: stage 63 low-hanging items 5, 11 and 13, dead-code item 11.
"""
from __future__ import annotations

from pathlib import Path

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

