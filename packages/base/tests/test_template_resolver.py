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
from cs_image_system.contract.fields import fk_field, templated_field


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
