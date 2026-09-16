# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Characterization tests for the object stage (SmartContext + TemplateResolver).

These are the core protection for Phase 2: they lock in FK-object injection and
`templated_field` method-call rendering, which the new field-kind handlers must
reproduce byte-for-byte.
"""
from dataclasses import dataclass

from cs_image_system.base import registry as _registry
from cs_image_system.base.orchestrator import SmartContext
from cs_image_system.base.helpers.field_helpers import fk_field, templated_field
from cs_image_system.base.constants import VCT, DEFAULT, NO_MODEL_ID


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
    reg = _registry.Registry()
    rt = Runtime("aws")
    reg.register_built_instance(rt)
    w = Widget("w1", runtime="aws")

    ctx = SmartContext(w, {rt.global_id: rt})

    # The FK field name now dereferences to the actual Runtime object in Jinja context.
    assert ctx["runtime"].get_name() == "aws"
    assert ctx["runtime"].get_default_machine_type() == "t2.micro"


def test_templated_field_resolves_via_method_call_on_fk_object(clean_registry):
    tr = clean_registry  # the fixture yields the TemplateResolver singleton (map cleared)
    reg = _registry.Registry()
    rt = Runtime("aws")
    reg.register_built_instance(rt)
    tr.flattened_map[rt.global_id] = rt

    w = Widget("w1", runtime="aws")
    tr.flatten_dataclass(w)
    tr.resolve_all()

    # machine_type started at DEFAULT; the replace template calls a method on the
    # resolved FK object and fills the concrete value.
    assert w.machine_type == "t2.micro"
