# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 30, branch 2: the proof of the contract.

``packages/contract-example-plugin`` is a state backend plugin (OpenTofu's
``inmem``) written against ``cs_image_system.contract`` alone: its sources
import nothing from the core, its manifest depends on the contract and
pydantic, its model and builder subclass none of the core's base classes.
It is loaded by entry point, its model structures from YAML, and it takes
part in a dry ``run --all`` over a copy of the frozen fixture with its
backend emitted for every root that names it. Without this the contract
is a claim.
"""
from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import yaml

from cs_image_system.contract import core, state
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.names import super_safe_name
from cs_image_system.contract.testing import assert_conforms
from cs_image_system.contract_example_plugin.builder import InmemStateBuilder
from cs_image_system.contract_example_plugin.main import initialize
from cs_image_system.contract_example_plugin.models import INMEM, InmemBackendKind, InmemStateBackendModel

from v2_support import FIXTURE_CONFIG, REPO, V2Run, copy_config, reset_singletons

PACKAGE = REPO / "packages/contract-example-plugin"
FORBIDDEN = ("cs_image_system.base", "cs_image_system.system", "cs_image_system.hashicorp_utils")


def test_the_sources_import_nothing_from_the_core():
    for source in sorted((PACKAGE / "src").rglob("*.py")):
        for node in ast.walk(ast.parse(source.read_text(), filename=str(source))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
            for name in names:
                assert not name.startswith(FORBIDDEN), f"{source.relative_to(REPO)} imports {name}"
        text = source.read_text()
        for forbidden in FORBIDDEN:
            assert forbidden not in text, f"{source.relative_to(REPO)} names {forbidden}"


def test_the_manifest_depends_on_the_contract_and_pydantic_alone():
    project = tomllib.loads((PACKAGE / "pyproject.toml").read_text())["project"]
    names = sorted(d.split(">=")[0].split("==")[0] for d in project["dependencies"])
    assert names == ["cs-image-system-contract", "pydantic"], names
    assert project["entry-points"]["cs_image_system.plugins.state"] == {
        "contract_example_plugin": "cs_image_system.contract_example_plugin.main:initialize"}


def test_nothing_of_the_core_is_a_base_of_the_model_or_the_builder():
    for cls in (InmemStateBackendModel, InmemStateBuilder):
        for base in cls.__mro__[1:]:
            assert not base.__module__.startswith(FORBIDDEN), f"{cls.__name__} inherits {base.__module__}.{base.__name__}"


def test_the_model_and_the_builder_conform_to_the_kinds_protocols():
    assert_conforms(InmemStateBackendModel, state.StateBackendModelProtocol)
    assert_conforms(InmemStateBuilder, state.StateBuilderProtocol)
    assert_conforms(InmemBackendKind, state.BackendKindProtocol)
    # the checks the loader, the registry and the orchestrator make at runtime, name-only
    model = InmemStateBackendModel(name="Scratch Memory", aliases={"mem", "scratch_memory"}, lock_id="l1")
    assert isinstance(model, core.NameTypedProtocol) and isinstance(model, core.BuilderModelProtocol)
    assert isinstance(InmemStateBuilder(model), core.NameTypedProtocol)
    assert isinstance(initialize(), core.PluginMetadataProtocol)
    # the name rules the core's models apply, applied by hand
    assert model.name == "scratch_memory" and model.get_display_name() == "Scratch Memory"
    assert model.aliases == {"mem"}
    assert model.global_id == f"{VCT.STATE_BACKEND_MODEL}::__NoParentModel__::scratch_memory"
    registration = model.to_backend_registration()
    assert registration.type == INMEM and registration.aliases == ("mem",) and registration.settings == {"lock_id": "l1"}
    assert str(registration.state_location("my-ws")) == "inmem://memory/my_ws.tfstate"
    assert registration.backend_settings("my-ws") == {"lock_id": "l1"} and registration.remote_state_settings("my-ws") == {}


def test_the_plugin_loads_by_entry_point_and_the_registry_holds_its_classes():
    from cs_image_system.base.registry import Registry
    reset_singletons()
    reg = Registry()
    assert reg.get_model(VCT.STATE_BACKEND_MODEL, INMEM) is InmemStateBackendModel
    assert reg.builders[InmemStateBackendModel] is InmemStateBuilder
    assert reg.get_builder_for_model(INMEM, VCT.STATE_BACKEND) is InmemStateBuilder


def _bind_the_storage_roots_to_inmem(root: Path) -> None:
    """A fourth state-backends file declares the entry; the two storage roots
    bind to it instead of the fixture's second S3 bucket."""
    (root / "cfg" / "state-backends-4.yml").write_text(yaml.safe_dump({"state_backends": [
        {"name": "scratch", "type": "inmem", "description": "the proof's backend", "aliases": ["mem"]}]}, sort_keys=False))
    p = root / "cfg" / "storage-builders.yml"
    text = p.read_text()
    assert "state_configuration: s3-east1" in text, "the fixture's storage roots moved; re-aim the proof"
    p.write_text(text.replace("state_configuration: s3-east1", "state_configuration: scratch"))


def test_the_entry_structures_from_yaml_and_reaches_the_collector(tmp_path, monkeypatch):
    from cs_image_system.hashicorp_utils.collector import TerraformCollector
    root = copy_config(tmp_path)
    _bind_the_storage_roots_to_inmem(root)
    v2 = V2Run(tmp_path, monkeypatch, config_root=root)
    backends = v2.ctx.state_backends
    assert isinstance(backends["scratch"], InmemStateBuilder)
    assert isinstance(backends["scratch"].model, InmemStateBackendModel)
    registration = TerraformCollector().resolve_backend("mem")
    assert registration is not None and registration.name == "scratch" and registration.type == INMEM


def test_a_dry_run_emits_the_backend_for_every_root_that_names_it(tmp_path, monkeypatch):
    from cs_image_system.hashicorp_utils.collector import TerraformCollector
    root = copy_config(tmp_path)
    _bind_the_storage_roots_to_inmem(root)
    v2 = V2Run(tmp_path, monkeypatch, config_root=root)
    v2.run("all")
    storage = v2.generated / "storage"
    backend_files = sorted(storage.rglob("*.tfbackend.hcl"))
    assert len(backend_files) >= 2, [str(p.relative_to(v2.generated)) for p in storage.rglob("*")]
    for backend_file in backend_files:
        assert "Backend 'scratch' (inmem)" in backend_file.read_text()
        roots = [p for p in backend_file.parent.glob("*.tf") if 'backend "inmem" {' in p.read_text()]
        assert roots, f"no root beside {backend_file.name} carries backend \"inmem\""
    consumers = [p for p in (v2.generated / "instance-image").rglob("*.tf") if 'backend = "inmem"' in p.read_text()]
    assert consumers, "no instance root reads the storage state through an inmem remote-state data source"
    locations = TerraformCollector().state_locations()
    inmem = {ws: str(loc) for ws, loc in locations.items() if loc.type == INMEM}
    assert len(inmem) == len(backend_files), (inmem, backend_files)
    assert all(loc == f"inmem://memory/{super_safe_name(ws)}.tfstate" for ws, loc in inmem.items()), inmem
    assert (FIXTURE_CONFIG / "cfg" / "state-backends-4.yml").exists() is False, "the frozen fixture itself must not change"
