# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 63, the low-hanging items: each one function, one test, found by the
documentation stage reading the code against its README and left as it was
until now. Every test here failed before its fix.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tests.v2_support import FIXTURE_CONFIG, V2Run, copy_config, load_context, reset_singletons, stub_environment


# ---------------------------------------------------- 1. the dummy builders

def test_the_dummy_builders_return_an_asset_set_and_a_declared_dummy_builder_runs(tmp_path: Path, monkeypatch):
    from cs_image_system.base.basic.asset import AssetSet
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.dummy_plugin.dummy_builders import DummyGroupBuilder, DummyUserBuilder
    for cls in (DummyGroupBuilder, DummyUserBuilder):
        out = cls.generate_items_during(SimpleNamespace(), ExecutionLifecyclePhase.GROUP_GENERATION)  # type: ignore[arg-type]
        assert isinstance(out, AssetSet) and len(out) == 0, cls.__name__
    # the reproduction of 2026-09-23: a declared `type: dummy` group builder and a group on it
    root = copy_config(tmp_path)
    gb = root / "cfg" / "group-builders.yml"
    data = yaml.safe_load(gb.read_text())
    data["group_builders"].append({"name": "dummy-groups", "type": "dummy", "org": "example", "team": "example"})
    gb.write_text(yaml.safe_dump(data, sort_keys=False))
    groups = root / "groups" / "group-dummy.yaml"
    groups.write_text(yaml.safe_dump({"groups": [{"name": "dummygroup", "type": "dummy-groups",
                                                  "description": "a group on the template builder"}]}))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["identity"], apply=False)
        assert summary.ok, summary.error
    finally:
        run.restore_cwd()


# ------------------------------------------------------------- 2. mask

def _mask(monkeypatch, identity: str | None):
    from typer.testing import CliRunner
    from cs_image_system.system import cli as climod
    if identity is None:
        monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    else:
        monkeypatch.setenv("CSIS_CONFIG_IDENTITY", identity)
    return CliRunner().invoke(climod.app, ["--root-dir", str(FIXTURE_CONFIG), "mask"])


def test_mask_refuses_loudly_when_it_cannot_open_a_marker_and_masks_when_it_can(monkeypatch):
    without = _mask(monkeypatch, None)
    assert without.exit_code == 1, without.output
    assert "mask: FAILED" in without.output and "nothing is masked" in without.output
    assert "::add-mask::" not in without.output
    with_identity = _mask(monkeypatch, str(FIXTURE_CONFIG / ".age-identity"))
    assert with_identity.exit_code == 0, with_identity.output
    assert with_identity.output.count("::add-mask::") > 0


# ------------------------------------------- 3. a packer string default

def test_a_packer_string_default_is_quoted_and_the_version_variable_says_what_it_emits():
    import hcl2
    from cs_image_system.hashicorp_utils.hashicorp import FO, Builder, packer_variable

    def render(**kw) -> str:
        return hcl2.dumps(packer_variable(Builder(), **kw).build(), formatter_options=FO)
    text = render(name="x", type="string", default="1.0.0")
    assert 'default = "1.0.0"' in text, text
    text = render(name="y", type="bool", default=True)
    assert "default = true" in text, text
    text = render(name="z", type="string", default=None, env_var="Z")
    assert 'default = env("Z")' in text, text
    from cs_image_system.packer_plugin import packer_builder
    src = Path(packer_builder.__file__).read_text()
    assert 'name="base_image_version"' in src and 'default="1.0.0"' not in src, "the env variable is what is emitted; no promise of 1.0.0"


# ----------------------------------------- 5. a registry collision named

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
    assert "collide on the registry key" in message and "rename one" in message, message
    assert "TofuS3StateBuilderModel(" not in message and "bucket=" not in message, "no repr, no field values"
    reset_singletons()
