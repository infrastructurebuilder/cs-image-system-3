# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 30: the plugin contract is a package of protocols.

The contract (``cs_image_system.contract``) imports nothing from the core
and its kind modules import only what they declare; the core's base classes
and every built-in plugin's models and builders conform to the protocols,
member by member and signature by signature; the mapper dispatches on the
contract's surface rather than a table of the core's classes; a plugin's
``version`` is its own; and the terraform collector pulls the declared
state backends from the registry.
"""
from __future__ import annotations

import ast
from importlib.metadata import version as dist_version
from pathlib import Path

import pytest

from cs_image_system.contract import core, group, image, instance, modification, operating_system, runtime, state, storage, user
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.metadata import PluginMetadata
from cs_image_system.contract.testing import assert_conforms, conformance_problems

from v2_support import FIXTURE_CONFIG, REPO, load_context, reset_singletons

CONTRACT = REPO / "packages/contract/src/cs_image_system/contract"
LEAVES = {"constants", "model_config", "fields", "field_kinds", "lifecycle", "lifecycles", "assets", "executables",
          "names", "hcl"}
# what each non-leaf module may import from the package, beside the leaves
ALLOWED = {
    "core": set(),
    "metadata": {"core"},
    "testing": set(),
    "state": {"core"},
    "runtime": {"core", "image"},          # the provider-specific image's enums
    "operating_system": {"core"},
    "storage": {"core"},
    "image": {"core"},
    "instance": {"core"},
    "modification": {"core"},
    "group": {"core"},
    "user": {"core"},
}


def _imports(path: Path) -> list[tuple[str, int]]:
    """(module, level) for every import in the file."""
    out: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            out += [(a.name, 0) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.append((node.module, node.level))
            else:                                   # `from . import x`: the names are the modules
                out += [(a.name, node.level) for a in node.names]
    return out


def test_the_contract_imports_nothing_from_the_core():
    """The direction: base depends on the contract, never the reverse. Every
    source under the package, every import, at any depth."""
    for source in sorted(CONTRACT.rglob("*.py")):
        for module, level in _imports(source):
            assert not (level == 0 and module.startswith(("cs_image_system.base", "cs_image_system.system",
                                                            "cs_image_system.hashicorp_utils"))), \
                f"{source.relative_to(REPO)} imports {module}"


def test_a_kind_module_imports_only_the_kinds_it_declares():
    """One module per kind over a shared core: a kind module reaches ``core``
    and the leaves, and another kind only when ALLOWED says so."""
    modules = {p.stem for p in CONTRACT.glob("*.py")} - {"__init__"}
    assert modules == LEAVES | set(ALLOWED), modules ^ (LEAVES | set(ALLOWED))
    for name, allowed in ALLOWED.items():
        reached = set()
        for module, level in _imports(CONTRACT / f"{name}.py"):
            if level == 1:
                reached.add(module.split(".")[0])
            elif module.startswith("cs_image_system.contract."):
                reached.add(module.split(".")[2])
        extra = reached - LEAVES - allowed
        assert not extra, f"contract.{name} imports {sorted(extra)}"
    for leaf in LEAVES:
        for module, level in _imports(CONTRACT / f"{leaf}.py"):
            if level == 1 or module.startswith("cs_image_system.contract."):
                target = module.split(".")[0] if level == 1 else module.split(".")[2]
                assert target in LEAVES, f"a leaf, contract.{leaf}, imports contract.{target}"


# ------------------------------------------------------------------ conformance

MODEL = {"csis_name"}                       # a kind's base model names no type: the dispatch rule
ROOT = {"csis_name", "csis_classifier"}     # the builder model itself classifies nothing either


def _core_pairs() -> list[tuple[type, type, set[str]]]:
    from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
    from cs_image_system.base.basic.builder_base import BuilderBase
    from cs_image_system.base.basic.builder_base_group import GroupBuilderBase
    from cs_image_system.base.basic.builder_base_image import ImageBuilderBase
    from cs_image_system.base.basic.builder_base_instance import InstanceBuilderBase
    from cs_image_system.base.basic.builder_base_mod import ModBuilderBase
    from cs_image_system.base.basic.builder_base_os import OsBuilderBase
    from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
    from cs_image_system.base.basic.builder_base_state import StateBuilderBase
    from cs_image_system.base.basic.builder_base_storage import StorageBuilderBase
    from cs_image_system.base.basic.builder_base_user import UserBuilderBase
    from cs_image_system.base.models.builder_model import BuilderModel, NameTyped, RuntimeEnabledBuilderModel
    from cs_image_system.base.models.cloud_builder import CloudBuilderModel
    from cs_image_system.base.models.executable import ExecutableModel
    from cs_image_system.base.models.group import Group
    from cs_image_system.base.models.group_builder import GroupBuilderModel
    from cs_image_system.base.models.image import Image
    from cs_image_system.base.models.image_builder_model import ImageBuilderModel
    from cs_image_system.base.models.instance import Instance, StorageMapping
    from cs_image_system.base.models.instance_builder import InstanceBuilderModel
    from cs_image_system.base.models.mixins import ParentPropertyHolding, SelfInjectedName, SubItemOverride
    from cs_image_system.base.models.mod_builder import ModBuilderModel
    from cs_image_system.base.models.os_builder_model import OsBuilderModel
    from cs_image_system.base.models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
    from cs_image_system.base.models.provider_specific_image import ProviderSpecificImage
    from cs_image_system.base.models.runtime import RuntimeBuilderModel
    from cs_image_system.base.models.state_builder import StateBuilderModel
    from cs_image_system.base.models.storage_builder import StorageBuilderModel
    from cs_image_system.base.models.user import User
    from cs_image_system.base.models.user_builder import UserBuilderModel
    return [
        (NameTyped, core.NameTypedProtocol, set()),
        (BuilderModel, core.BuilderModelProtocol, ROOT),
        (RuntimeEnabledBuilderModel, core.RuntimeEnabledBuilderModelProtocol, ROOT),
        (BuilderBase, core.BuilderProtocol, set()),
        (ExecutableModel, core.NameTypedProtocol, set()),
        (ProviderSpecificImage, core.NameTypedProtocol, set()),     # the accidental structural implementer, now deliberate
        (AbstractPluginMetadata, core.PluginMetadataProtocol, set()),
        (PluginMetadata, core.PluginMetadataProtocol, set()),
        (SelfInjectedName, core.SelfInjectedNameProtocol, set()),
        (SubItemOverride, core.SubItemOverrideProtocol, set()),
        (ParentPropertyHolding, core.ParentPropertyHoldingProtocol, set()),
        (User, core.ParentPropertyHoldingProtocol, set()), (Group, core.ParentPropertyHoldingProtocol, set()),
        (StorageMapping, core.ParentPropertyHoldingProtocol, set()),
        (OSBuilderBaseImageBuilderSubconfig, core.ParentPropertyHoldingProtocol, set()),
        (Image, core.SelfInjectedNameProtocol, set()), (Instance, core.SubItemOverrideProtocol, set()),
        (RuntimeBuilderModel, runtime.RuntimeBuilderModelProtocol, MODEL),
        (CloudBuilderModel, runtime.CloudBuilderModelProtocol, MODEL),
        (RuntimeBuilderBase, runtime.RuntimeBuilderProtocol, set()),
        (OsBuilderModel, operating_system.OsBuilderModelProtocol, MODEL),
        (OsBuilderBase, operating_system.OsBuilderProtocol, set()),
        (StorageBuilderModel, storage.StorageBuilderModelProtocol, MODEL),
        (StorageBuilderBase, storage.StorageBuilderProtocol, set()),
        (ImageBuilderModel, image.ImageBuilderModelProtocol, MODEL), (ImageBuilderBase, image.ImageBuilderProtocol, set()),
        (InstanceBuilderModel, instance.InstanceBuilderModelProtocol, MODEL),
        (InstanceBuilderBase, instance.InstanceBuilderProtocol, set()),
        (ModBuilderModel, modification.ModBuilderModelProtocol, MODEL),
        (ModBuilderBase, modification.ModBuilderProtocol, set()),
        (GroupBuilderModel, group.GroupBuilderModelProtocol, MODEL), (GroupBuilderBase, group.GroupBuilderProtocol, set()),
        (UserBuilderModel, user.UserBuilderModelProtocol, MODEL), (UserBuilderBase, user.UserBuilderProtocol, set()),
        (StateBuilderModel, state.StateBackendModelProtocol, MODEL), (StateBuilderBase, state.StateBuilderProtocol, set()),
    ]


@pytest.mark.parametrize("triple", _core_pairs(), ids=lambda p: f"{p[0].__name__}:{p[1].__name__}")
def test_every_base_class_conforms_to_its_protocol(triple):
    cls, protocol, abstract = triple
    assert_conforms(cls, protocol, abstract=abstract)


def test_a_protocol_listed_as_a_base_is_a_question_not_an_answer():
    """A class that names its protocol as a base and implements nothing
    conforms to nothing: the protocol's own stubs never count."""
    class Hollow(core.NameTypedProtocol):
        pass
    problems = conformance_problems(Hollow, core.NameTypedProtocol)
    assert {p.split(":")[0] for p in problems} == {"get_name", "get_type", "get_description", "get_aliases",
                                                    "get_classification", "global_id"}, problems


KIND_PROTOCOLS: dict[VCT, tuple[type, type]] = {
    VCT.RUNTIME_BUILDER_MODEL: (runtime.RuntimeBuilderModelProtocol, runtime.RuntimeBuilderProtocol),
    VCT.OS_BUILDER_MODEL: (operating_system.OsBuilderModelProtocol, operating_system.OsBuilderProtocol),
    VCT.STORAGE_BUILDER_MODEL: (storage.StorageBuilderModelProtocol, storage.StorageBuilderProtocol),
    VCT.IMAGE_BUILDER_MODEL: (image.ImageBuilderModelProtocol, image.ImageBuilderProtocol),
    VCT.INSTANCE_BUILDER_MODEL: (instance.InstanceBuilderModelProtocol, instance.InstanceBuilderProtocol),
    VCT.MOD_BUILDER_MODEL: (modification.ModBuilderModelProtocol, modification.ModBuilderProtocol),
    VCT.GROUP_BUILDER_MODEL: (group.GroupBuilderModelProtocol, group.GroupBuilderProtocol),
    VCT.USER_BUILDER_MODEL: (user.UserBuilderModelProtocol, user.UserBuilderProtocol),
    VCT.STATE_BACKEND_MODEL: (state.StateBackendModelProtocol, state.StateBuilderProtocol),
}


def test_every_built_in_plugin_conforms_to_its_kind():
    """Every built-in plugin's registered model and builder classes conform
    to the protocols of their kind; every shortfall is named at once."""
    from cs_image_system.base.registry import Registry, sanitize_classifier
    reset_singletons()
    reg = Registry()
    checked = 0
    problems: list[str] = []
    for model_cls, builder_cls in reg.builders.items():
        vct = sanitize_classifier(model_cls.csis_classifier())  # type: ignore[attr-defined]
        if vct not in KIND_PROTOCOLS:
            continue
        model_proto, builder_proto = KIND_PROTOCOLS[vct]
        for cls, proto in ((model_cls, model_proto), (builder_cls, builder_proto)):
            checked += 1
            problems += [f"{cls.__name__} vs {proto.__name__}: {p}" for p in conformance_problems(cls, proto)]
    assert checked >= 2 * 14, "fewer registered pairs than the fourteen plugins declare"
    assert not problems, "\n".join(problems)


def test_assert_conforms_names_every_shortfall():
    """The check is signature-level: a missing member, a missing parameter,
    a lost default, a property where a method is declared, each named."""
    class Short:
        def get_name(self) -> str:
            return "x"
        def get_type(self, extra) -> str:           # a required parameter the protocol lacks
            return "y"
        global_id = "not-a-property"                # a plain attribute stands for a read-only property

    problems = conformance_problems(Short, core.NameTypedProtocol)
    assert any(p.startswith("get_aliases: missing") for p in problems)
    assert any("get_type: adds the required parameter 'extra'" in p for p in problems)
    assert not any(p.startswith("global_id") for p in problems)
    with pytest.raises(AssertionError, match="does not conform to NameTypedProtocol"):
        assert_conforms(Short, core.NameTypedProtocol)

    class Whole(Short):
        def get_type(self) -> str:
            return "y"
        def get_description(self) -> str | None:
            return None
        def get_aliases(self) -> set[str]:
            return set()
        def get_classification(self) -> VCT:
            return VCT.UNCLASSIFIED
    assert conformance_problems(Whole, core.NameTypedProtocol) == []


# ------------------------------------------------------------------ the mapper's dispatch rule

def test_the_mapper_dispatches_on_the_contracts_surface_not_a_table():
    """A builder-model class that classifies itself and names no type of its
    own is a dispatch point (the nine kind bases); a concrete model, an item
    model (its `type` is a foreign key) and the configuration itself are
    structured as themselves."""
    from cs_image_system.base.models.base_image import BaseImage
    from cs_image_system.base.models.builder_model import BuilderModel, RuntimeEnabledBuilderModel
    from cs_image_system.base.models.executable import ExecutableModel
    from cs_image_system.base.models.group import Group
    from cs_image_system.base.models.group_builder import GroupBuilderModel
    from cs_image_system.base.models.ia_config import IAConfig
    from cs_image_system.base.models.image import Image
    from cs_image_system.base.models.image_builder_model import ImageBuilderModel
    from cs_image_system.base.models.instance import Instance
    from cs_image_system.base.models.instance_builder import InstanceBuilderModel
    from cs_image_system.base.models.mod_builder import ModBuilderModel
    from cs_image_system.base.models.os_builder_model import OsBuilderModel
    from cs_image_system.base.models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
    from cs_image_system.base.models.runtime import RuntimeBuilderModel
    from cs_image_system.base.models.state_builder import StateBuilderModel
    from cs_image_system.base.models.storage import Storage
    from cs_image_system.base.models.storage_builder import StorageBuilderModel
    from cs_image_system.base.models.user import User
    from cs_image_system.base.models.user_builder import UserBuilderModel
    from cs_image_system.base.orchestrator import Orchestrator
    from cs_image_system.local_state_plugin.local_state_models import LocalStateBuilderModel
    reset_singletons()
    conv = Orchestrator().get_converter()
    assert not hasattr(conv, "_base_vcts")
    from cs_image_system.base.models.cloud_builder import CloudBuilderModel
    from cs_image_system.base.models.container_builder import ContainerBuilderModel
    expected = {
        RuntimeBuilderModel: VCT.RUNTIME_BUILDER_MODEL, OsBuilderModel: VCT.OS_BUILDER_MODEL,
        # the two runtime kinds classify under their own value and dispatch under the runtime's (sanitised)
        CloudBuilderModel: VCT.RUNTIME_BUILDER_MODEL, ContainerBuilderModel: VCT.RUNTIME_BUILDER_MODEL,
        StorageBuilderModel: VCT.STORAGE_BUILDER_MODEL, ImageBuilderModel: VCT.IMAGE_BUILDER_MODEL,
        InstanceBuilderModel: VCT.INSTANCE_BUILDER_MODEL, ModBuilderModel: VCT.MOD_BUILDER_MODEL,
        GroupBuilderModel: VCT.GROUP_BUILDER_MODEL, UserBuilderModel: VCT.USER_BUILDER_MODEL,
        StateBuilderModel: VCT.STATE_BACKEND_MODEL,
    }
    for cls, vct in expected.items():
        assert conv._dispatch_vct(cls) == vct, cls
    for cls in (BuilderModel, RuntimeEnabledBuilderModel, LocalStateBuilderModel, Image, BaseImage, Instance, Group,
                User, Storage, ExecutableModel, OSBuilderBaseImageBuilderSubconfig, IAConfig, dict):
        assert conv._dispatch_vct(cls) is None, cls


# ------------------------------------------------------------------ the metadata's version

def test_a_plugins_version_is_its_own():
    """``AbstractPluginMetadata.version`` returned the metadata version
    (``"1"``) for every plugin; it is the version given, else the version of
    the distribution that ships the subclass."""
    from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
    from cs_image_system.local_state_plugin.main import LocalStateTypes
    md = LocalStateTypes()
    assert md.plugin_metadata_version == "1"
    assert md.version == dist_version("cs-image-system-local-state-plugin") != "1"
    assert str(md.requires_python) == ">=3.13"

    class Explicit(AbstractPluginMetadata):
        def __init__(self) -> None:
            super().__init__("1", ">=3.13", _version="7.7.7")
    assert Explicit().version == "7.7.7"
    record = PluginMetadata(version="2.0")
    assert record.version == "2.0" and str(record.requires_python) == ">=3.13"
    assert isinstance(record, core.PluginMetadataProtocol)


# ------------------------------------------------------------------ the state seam

def test_the_collector_pulls_the_declared_backends_from_the_registry(tmp_path, monkeypatch):
    """A state plugin's model no longer pushes its registration into the
    collector from ``finalize``; once the state backends are loaded the core
    hands every model's ``to_backend_registration()`` to the collector, so
    the three state plugins import nothing from hashicorp-utils, and a
    collector reset after the load leaves nothing behind (the builder
    tests that reset it rely on that)."""
    from cs_image_system.hashicorp_utils.collector import TerraformCollector
    from v2_support import copy_config, stub_environment
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", str(FIXTURE_CONFIG / ".age-identity"))
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    load_context(root)
    col = TerraformCollector()
    declared = {b.type for b in col._backends.values()}
    assert {"s3", "local", "gcs"} <= declared, declared
    default = col.resolve_backend(None)
    assert default is not None and default.is_default
    col.reset()
    assert col.resolve_backend(None) is None, "a reset collector pulls nothing on its own"
    for name in ("local-state-plugin", "tf-s3-state-plugin", "gcs-state-plugin"):
        for source in (REPO / "packages" / name / "src").rglob("*.py"):
            assert "hashicorp_utils" not in source.read_text(), source.relative_to(REPO)
