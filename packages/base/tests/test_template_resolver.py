# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Characterization tests for the object stage (SmartContext + TemplateResolver).

These are the core protection for Phase 2: they lock in FK-object injection and
`templated_field` method-call rendering, which the new field-kind handlers must
reproduce byte-for-byte.
"""
import logging
from dataclasses import dataclass

import jinja2
import pytest

from cs_image_system.base import orchestrator
from cs_image_system.base.orchestrator import SmartContext
from cs_image_system.contract.constants import DEFAULT, NO_MODEL_ID, VCT
from cs_image_system.contract.fields import deferred_list_field, fk_field, lookup_dataclass_field, templated_field


@dataclass
class Runtime:
    name: str
    machine: str = "t2.micro"
    def get_name(self): return self.name
    def get_type(self): return "runtime"
    def get_description(self): return None
    def get_aliases(self): return set()
    def get_classification(self): return VCT.RUNTIME_BUILDER_MODEL
    @property
    def global_id(self): return f"{self.get_classification()}::{NO_MODEL_ID}::{self.name}"
    def get_default_machine_type(self): return self.machine


@dataclass
class Widget:
    name: str
    runtime: str = fk_field(target=VCT.RUNTIME_BUILDER_MODEL, default=DEFAULT)
    machine_type: str = templated_field(
        replace_value="{{ runtime.get_default_machine_type() }}", default=DEFAULT)
    def get_name(self): return self.name
    def get_type(self): return "widget"
    def get_description(self): return None
    def get_aliases(self): return set()
    def get_classification(self): return VCT.IMAGE_BUILDER_MODEL
    @property
    def global_id(self): return f"{self.get_classification()}::{NO_MODEL_ID}::{self.name}"


def test_smartcontext_resolves_fk_string_to_object(clean_registry):
    reg = clean_registry.reg
    rt = Runtime("aws")
    reg.register_built_instance(rt)
    w = Widget("w1", runtime="aws")

    ctx = SmartContext(w, {rt.global_id: rt}, reg)

    # The FK field name now dereferences to the actual Runtime object in Jinja context.
    assert ctx["runtime"].get_name() == "aws"
    assert ctx["runtime"].get_default_machine_type() == "t2.micro"


def test_templated_field_resolves_via_method_call_on_fk_object(clean_registry):
    tr = clean_registry  # the fixture yields a resolver of the test's own (map empty)
    reg = tr.reg
    rt = Runtime("aws")
    reg.register_built_instance(rt)
    tr.flattened_map[rt.global_id] = rt

    w = Widget("w1", runtime="aws")
    tr.flatten_dataclass(w)
    tr.resolve_all()

    # machine_type started at DEFAULT; the replace template calls a method on the
    # resolved FK object and fills the concrete value.
    assert w.machine_type == "t2.micro"


MACHINE_REPLACE = "{{ runtime.get_default_machine_type() }}"
BROKEN_REPLACE = "{{ runtime.get_default_machine_type( }}"


# a templated field whose declared default is not `default` keeps that default
# while the context is built, so its replace template is rendered by the field
# pass itself (the path the image models' machine_type takes)
@dataclass
class NoneDefaultWidget(Widget):
    machine_type: str = templated_field(replace_value=MACHINE_REPLACE, default=None)


@dataclass
class BrokenWidget(Widget):
    machine_type: str = templated_field(replace_value=BROKEN_REPLACE, default=None)


def _resolver_with_runtime(tr):
    rt = Runtime("aws")
    tr.reg.register_built_instance(rt)
    tr.flattened_map[rt.global_id] = rt
    return tr


def test_a_replace_template_is_compiled_once_per_render(clean_registry, monkeypatch):
    tr = _resolver_with_runtime(clean_registry)
    w = NoneDefaultWidget("w1", runtime="aws")
    tr.flatten_dataclass(w)
    compiled: list[str] = []
    from_string = tr.env.from_string
    monkeypatch.setattr(tr.env, "from_string", lambda source, *a, **k: compiled.append(source) or from_string(source, *a, **k))

    tr.resolve_all()

    assert w.machine_type == "t2.micro"
    assert compiled.count(MACHINE_REPLACE) == 1


def test_a_replace_template_that_does_not_compile_is_logged_and_raised(clean_registry, caplog):
    tr = _resolver_with_runtime(clean_registry)
    w = BrokenWidget("w1", runtime="aws")
    tr.flatten_dataclass(w)

    with caplog.at_level(logging.ERROR, logger=orchestrator.__name__), pytest.raises(jinja2.TemplateSyntaxError):
        tr.resolve_all()

    errors = [r for r in caplog.records if r.levelno == logging.ERROR and r.name == orchestrator.__name__]
    assert len(errors) == 1
    assert "machine_type" in errors[0].getMessage() and BROKEN_REPLACE in errors[0].getMessage()


@dataclass
class Echo:
    """A model whose one templated field renders to a new template every
    pass: it cannot settle, whatever the pass limit."""
    name: str
    text: str = "{{ this.text }}!"


def _unrendered(caplog) -> list[tuple]:
    return [r.args for r in caplog.records
            if r.name == orchestrator.__name__ and r.levelno == logging.WARNING
            and r.msg == orchestrator.UNRENDERED_TEMPLATE_WARNING]


def test_a_field_still_templated_after_the_last_pass_is_named_once(clean_registry, caplog):
    tr = clean_registry
    echo = Echo("e")
    tr.flattened_map["echo"] = echo
    tr.flattened_map["scope"] = {"x": "{{ x }}!", "settled": "plain"}

    with caplog.at_level(logging.WARNING, logger=orchestrator.__name__):
        unresolved = tr.resolve_all()
        tr.resolve_all()                    # the mapping is worked on again; nothing is named twice

    passes = orchestrator.MAX_RESOLVE_PASSES
    assert sorted(_unrendered(caplog)) == [(passes, "echo", "text"), (passes, "scope", "x")]
    # the run goes on: the field keeps what the last pass left (each pass
    # doubles the suffix, so exactly the limit's passes ran)
    assert unresolved == []
    assert echo.text == "{{ this.text }}" + "!" * 2 ** passes


def test_a_template_settled_within_the_passes_is_not_named(clean_registry, caplog):
    tr = _resolver_with_runtime(clean_registry)
    w = Widget("w1", runtime="aws")
    tr.flatten_dataclass(w)
    tr.flattened_map["scope"] = {"a": "{{ b }}", "b": "{{ c }}", "c": "end"}

    with caplog.at_level(logging.WARNING, logger=orchestrator.__name__):
        tr.resolve_all()

    assert w.machine_type == "t2.micro" and tr.flattened_map["scope"]["a"] == "end"
    assert _unrendered(caplog) == []


@dataclass
class Holder:
    """A model with one deferred list of each builder classification the
    resolver treats differently: modifications, and any other."""
    name: str
    storages: list = deferred_list_field(builder_vct=VCT.STORAGE_BUILDER_MODEL, item_vct=VCT.STORAGE_MAPPING_ITEM_MODEL)
    modifications: list = deferred_list_field(builder_vct=VCT.MOD_BUILDER_MODEL, item_vct=VCT.MOD_BUILDER_ITEM_MODEL)


def _upgrade(tr, holder: Holder, field_name: str) -> Holder:
    return tr.upgrade_deferred_list_generated(holder, lookup_dataclass_field(holder, field_name))


@pytest.mark.parametrize("no_name", [None, ""])
def test_an_item_naming_no_builder_stays_as_written_when_no_default_is_named(clean_registry, monkeypatch, caplog, no_name):
    tr = clean_registry
    monkeypatch.setattr(tr.reg, "get_default_for", lambda vct: no_name)
    holder = Holder("h", storages=[{"name": "s1"}])

    with caplog.at_level(logging.DEBUG, logger=orchestrator.__name__):
        _upgrade(tr, holder, "storages")

    assert holder.storages == [{"name": "s1"}]
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


@pytest.mark.parametrize("no_name", [None, ""])
def test_a_modification_naming_no_builder_is_refused_when_no_default_is_named(clean_registry, monkeypatch, no_name):
    tr = clean_registry
    monkeypatch.setattr(tr.reg, "get_default_for", lambda vct: no_name)
    holder = Holder("h", modifications=[{"name": "m1"}])

    with pytest.raises(ValueError, match="'m1'"):
        _upgrade(tr, holder, "modifications")


@dataclass
class UnmappedStorageBuilder:
    """A storage builder model whose type no item model is registered for."""
    name: str
    def get_name(self): return self.name
    def get_type(self): return "unmapped-storage"
    def get_description(self): return None
    def get_aliases(self): return set()
    def get_classification(self): return VCT.STORAGE_BUILDER_MODEL
    @property
    def global_id(self): return f"{self.get_classification()}::{NO_MODEL_ID}::{self.name}"


def test_an_item_with_no_model_of_its_own_takes_the_item_classifications_default_model(clean_registry):
    """The base plugin injects StorageMapping as the default model of the
    storage mapping item classification; a model with no override whose
    storage builder's type has no item model structures its storages
    into that default."""
    from cs_image_system.base.init import BaseInitTypes
    from cs_image_system.base.models.instance import StorageMapping
    tr = clean_registry
    tr.reg.register_plugin_metadata(BaseInitTypes(), namespace="base")
    tr.reg.register_built_instance(UnmappedStorageBuilder("scratch"))
    holder = Holder("h", storages=[{"name": "vol1", "type": "scratch"}])

    _upgrade(tr, holder, "storages")

    assert [type(s) for s in holder.storages] == [StorageMapping]
    assert holder.storages[0].type_ == "scratch"
