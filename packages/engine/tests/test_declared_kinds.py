# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A plugin declares its enrollment kinds and field kinds; the system
registers them for a plugin it accepts, and for no other.

Held on entry points the test supplies, each case run in every order of
discovery (discovery reads by name, so the names are permuted): the same
plugins are accepted, the same are skipped and named, and the same kinds
are registered, whichever plugin is found first. A skipped plugin's kinds
are never registered, so nothing is taken back; two plugins declaring one
kind differently are both skipped; an equal declaration is one
registration; a system field-kind name is never a plugin's.
"""
from __future__ import annotations

import itertools
import logging
import types
from collections.abc import Callable
from typing import Any, cast

import pytest

from cs_image_system.contract import enrollment, field_kinds
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.enrollment import EnrollmentKind
from cs_image_system.contract.field_kinds import FieldKindHandler
from cs_image_system.contract.metadata import PluginMetadata
from cs_image_system.engine import loader


class _Checker:
    """A version checker: a class no protocol holds, so a plugin made of it
    needs only its name and its classification."""

    @classmethod
    def csis_name(cls) -> str:
        return "checker"

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.VERSION_CHECKER


class _Model:
    pass


class _BuilderOne:
    pass


class _BuilderTwo:
    pass


def _render(word: str) -> Callable[[dict[str, Any]], list[str]]:
    def lines(params: dict[str, Any]) -> list[str]:
        return [word]
    return lines


def _no_tasks(params: dict[str, Any]) -> list[dict[str, Any]]:
    return []


def _enrollment(name: str, word: str = "") -> EnrollmentKind:
    return EnrollmentKind(name, _render(word or name), _no_tasks)


#: a library's enrollment kind: one object, which every plugin that uses the library declares
SHARED = _enrollment("shared-kind", "from the library")


def _plugin(name: str, *, enrollments: tuple[EnrollmentKind, ...] = (), fields: dict[str, Any] | None = None,
            builder: type | None = None, breaks: bool = False) -> Any:
    md = PluginMetadata(services={name: [cast(Any, type(f"Checker_{name}", (_Checker,), {
                            "csis_name": classmethod(lambda cls: name)}))]},
                        builders_for_models={cast(Any, _Model): cast(Any, builder)} if builder else {},
                        namespace=name, enrollment_kinds=enrollments, field_kinds=fields or {})

    def load() -> Any:
        if breaks:
            raise ImportError(f"{name}'s module is broken")
        return lambda: md
    return types.SimpleNamespace(name=name, value=f"{__name__}:{name}",
                                 dist=types.SimpleNamespace(name=f"cs-image-system-{name}-plugin"), load=load)


@pytest.fixture
def kinds(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """The two kind registries, the test's own: no enrollment kind, the
    system's own field kinds."""
    monkeypatch.setattr(enrollment, "_KINDS", {})
    monkeypatch.setattr(field_kinds, "_HANDLERS", {k: v for k, v in field_kinds._HANDLERS.items()
                                                   if k in field_kinds.SYSTEM_FIELD_KINDS})
    return types.SimpleNamespace(enrollment=enrollment, field_kinds=field_kinds)


def _load(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, *points: Any):
    """Discover ``points`` and register the declared kinds of the usable
    ones, as a process does once: the usable names, the skipped names and
    the ERROR lines."""
    monkeypatch.setattr(loader, "entry_points", lambda group: list(points) if group.endswith(".other") else [])
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger=loader.__name__):
        found, unusable = loader.discover()
        loader.register_declared_kinds(found)
    lines = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    return sorted(d.name for d in found), sorted(u.plugin for u in unusable), lines


def _in_every_order(monkeypatch, caplog, kinds, roles: dict[str, Callable[[str], Any]]):
    """Run discovery once per order of the ``roles`` (each makes a plugin
    under the name it is given), and return the one outcome every order
    gave, in the roles' words: (usable roles, skipped roles, registered
    enrollment kinds, registered plugin field kinds)."""
    names = [f"p{i}" for i in range(len(roles))]               # discovery reads these in this order
    outcomes = set()
    for order in itertools.permutations(roles):
        kinds.enrollment._KINDS.clear()
        for name in list(kinds.field_kinds._HANDLERS):
            if name not in field_kinds.SYSTEM_FIELD_KINDS:
                del kinds.field_kinds._HANDLERS[name]
        role_of = dict(zip(names, order, strict=True))
        usable, skipped, lines = _load(monkeypatch, caplog, *(roles[role](name) for name, role in role_of.items()))
        outcomes.add((tuple(sorted(role_of[n] for n in usable)), tuple(sorted(role_of[n] for n in skipped)),
                      tuple(kinds.enrollment.registered_kinds()),
                      tuple(sorted(n for n in kinds.field_kinds._HANDLERS if n not in field_kinds.SYSTEM_FIELD_KINDS))))
    assert len(outcomes) == 1, f"the outcome depends on the order: {sorted(outcomes)}"
    return outcomes.pop()


# ------------------------------------------------------------ a declared kind is registered (Story 1)

def test_an_accepted_plugins_declared_kinds_are_registered_and_found(monkeypatch, caplog, kinds):
    handler = FieldKindHandler()
    usable, skipped, lines = _load(monkeypatch, caplog, _plugin("alpha", enrollments=(_enrollment("alpha-kind"),),
                                                                  fields={"alpha-field": handler}))
    assert usable == ["alpha"] and skipped == [] and lines == []
    assert enrollment.registered_kinds() == ["alpha-kind"]
    found = enrollment.enrollment_kind_for({"enrollment": {"enrollment": "alpha-kind"}})
    assert found is not None and found.script_lines({}) == ["alpha-kind"]
    assert field_kinds.get_field_kind_handler("alpha-field") is handler


def test_a_plugin_that_declares_no_kind_changes_neither_registry(monkeypatch, caplog, kinds):
    before = dict(field_kinds._HANDLERS)
    _load(monkeypatch, caplog, _plugin("plain"))
    assert enrollment.registered_kinds() == [] and field_kinds._HANDLERS == before


def test_a_second_discovery_in_the_process_registers_the_same_kinds(monkeypatch, caplog, kinds):
    point = _plugin("alpha", enrollments=(_enrollment("alpha-kind"),))
    _load(monkeypatch, caplog, point)
    first = enrollment.registered_kinds()
    _load(monkeypatch, caplog, point)
    assert enrollment.registered_kinds() == first == ["alpha-kind"]


# ------------------------------------------------------------ nothing of a skipped plugin (Story 2)

def test_a_plugin_that_fails_to_load_registers_none_of_its_kinds(monkeypatch, caplog, kinds):
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "broken": lambda n: _plugin(n, enrollments=(_enrollment("lost"),), breaks=True),
        "sound": lambda n: _plugin(n, enrollments=(_enrollment("kept"),)),
    })
    assert outcome == (("sound",), ("broken",), ("kept",), ())


def test_a_plugin_skipped_for_a_collision_registers_none_of_its_kinds(monkeypatch, caplog, kinds):
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "one": lambda n: _plugin(n, enrollments=(_enrollment("one-kind"),), builder=_BuilderOne),
        "two": lambda n: _plugin(n, fields={"two-field": FieldKindHandler()}, builder=_BuilderTwo),
        "bystander": lambda n: _plugin(n, enrollments=(_enrollment("bystander-kind"),)),
    })
    assert outcome == (("bystander",), ("one", "two"), ("bystander-kind",), ())


def test_a_usable_plugin_keeps_a_librarys_kind_another_skipped_plugin_also_declares(monkeypatch, caplog, kinds):
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "user": lambda n: _plugin(n, enrollments=(SHARED,), builder=_BuilderOne),
        "rival": lambda n: _plugin(n, builder=_BuilderTwo),
        "keeper": lambda n: _plugin(n, enrollments=(SHARED,)),
    })
    assert outcome == (("keeper",), ("rival", "user"), ("shared-kind",), ())


# ------------------------------------------------------------ a collision over a kind (Story 3)

@pytest.mark.parametrize("declare", [
    lambda word: {"enrollments": (_enrollment("disputed", word),)},
    lambda word: {"fields": {"disputed": FieldKindHandler()}},
], ids=["enrollment kind", "field kind"])
def test_two_plugins_declaring_one_kind_differently_are_both_skipped_and_named(monkeypatch, caplog, kinds, declare):
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "alpha": lambda n: _plugin(n, **declare("alpha")),
        "beta": lambda n: _plugin(n, **declare("beta")),
    })
    assert outcome == ((), ("alpha", "beta"), (), ())
    _usable, _skipped, lines = _load(monkeypatch, caplog, _plugin("alpha", **declare("alpha")),
                                     _plugin("beta", **declare("beta")))
    assert len(lines) == 1 and "alpha" in lines[0] and "beta" in lines[0] and "'disputed'" in lines[0]


def test_two_plugins_declaring_an_equal_kind_both_load_and_it_is_registered_once(monkeypatch, caplog, kinds):
    handler = FieldKindHandler()
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "alpha": lambda n: _plugin(n, enrollments=(SHARED,), fields={"shared-field": handler}),
        "beta": lambda n: _plugin(n, enrollments=(SHARED,), fields={"shared-field": handler}),
    })
    assert outcome == (("alpha", "beta"), (), ("shared-kind",), ("shared-field",))


def test_three_claimants_two_alike_are_all_skipped_and_every_line_names_two_that_differ(monkeypatch, caplog, kinds):
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "alike-one": lambda n: _plugin(n, enrollments=(SHARED,)),
        "alike-two": lambda n: _plugin(n, enrollments=(SHARED,)),
        "different": lambda n: _plugin(n, enrollments=(_enrollment("shared-kind", "other"),)),
    })
    assert outcome == ((), ("alike-one", "alike-two", "different"), (), ())
    _u, _s, lines = _load(monkeypatch, caplog, _plugin("a", enrollments=(SHARED,)), _plugin("b", enrollments=(SHARED,)),
                          _plugin("c", enrollments=(_enrollment("shared-kind", "other"),)))
    assert lines and all("(cs-image-system-c-plugin)" in line for line in lines)       # c is the one that differs


def test_a_plugin_declaring_one_of_the_systems_field_kinds_is_skipped_alone(monkeypatch, caplog, kinds):
    own = field_kinds._HANDLERS.get(field_kinds.FK)
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "grabby": lambda n: _plugin(n, fields={field_kinds.FK: FieldKindHandler()}),
        "sound": lambda n: _plugin(n),
    })
    assert outcome == (("sound",), ("grabby",), (), ())
    assert field_kinds._HANDLERS.get(field_kinds.FK) is own


def test_a_plugin_declaring_one_kind_twice_is_refused_naming_it(monkeypatch, caplog, kinds):
    usable, skipped, lines = _load(monkeypatch, caplog, _plugin("twice", enrollments=(_enrollment("k", "a"),
                                                                                      _enrollment("k", "b"))))
    assert usable == [] and skipped == ["twice"] and len(lines) == 1 and "'k'" in lines[0]


# ------------------------------------------------------------ the four cases spec 001 recorded (FR-010)

def test_case_one_a_plugin_that_fails_beside_a_usable_plugin_declaring_its_kind(monkeypatch, caplog, kinds):
    """Spec 001, T140: a failed plugin no longer leaves a kind that makes a usable one collide."""
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "failed": lambda n: _plugin(n, enrollments=(SHARED,), breaks=True),
        "usable": lambda n: _plugin(n, enrollments=(_enrollment("shared-kind", "its own"),)),
    })
    assert outcome == (("usable",), ("failed",), ("shared-kind",), ())


def test_case_two_a_third_plugin_colliding_with_one_side_of_a_kind_collision(monkeypatch, caplog, kinds):
    """Spec 001, T141: every plugin is a candidate, so the third's fate does not depend on order."""
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "kind-a": lambda n: _plugin(n, enrollments=(_enrollment("k", "a"),), builder=_BuilderOne),
        "kind-b": lambda n: _plugin(n, enrollments=(_enrollment("k", "b"),)),
        "builder": lambda n: _plugin(n, builder=_BuilderTwo),
    })
    assert outcome == ((), ("builder", "kind-a", "kind-b"), (), ())


def test_case_three_two_entry_points_of_one_package_one_skipped(monkeypatch, caplog, kinds):
    """Spec 001, T142: the usable entry point keeps the kind it declares."""
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "skipped": lambda n: _plugin(n, enrollments=(SHARED,), builder=_BuilderOne),
        "rival": lambda n: _plugin(n, builder=_BuilderTwo),
        "kept": lambda n: _plugin(n, enrollments=(SHARED,)),
    })
    assert outcome == (("kept",), ("rival", "skipped"), ("shared-kind",), ())


def test_case_four_two_plugins_sharing_a_librarys_kind_and_a_third_declaring_it_differently(monkeypatch, caplog, kinds):
    """Spec 001, T143: every plugin in the dispute is named and skipped, in every order."""
    outcome = _in_every_order(monkeypatch, caplog, kinds, {
        "library-one": lambda n: _plugin(n, enrollments=(SHARED,)),
        "library-two": lambda n: _plugin(n, enrollments=(SHARED,)),
        "its-own": lambda n: _plugin(n, enrollments=(_enrollment("shared-kind", "its own"),)),
    })
    assert outcome == ((), ("its-own", "library-one", "library-two"), (), ())


def test_a_field_of_a_declared_field_kind_is_resolved_by_its_handler(monkeypatch, caplog, kinds, clean_registry):
    """The resolver reaches a declared field kind exactly as it reached a
    registered one (the pattern of test_field_kinds.py, declared)."""
    import dataclasses
    from dataclasses import dataclass

    from cs_image_system.contract.constants import FIELD_KIND, NO_MODEL_ID

    class Shout(FieldKindHandler):
        def resolve(self, resolver, obj, field, context, reg):
            value = getattr(obj, field.name)
            if isinstance(value, str) and value.islower():
                setattr(obj, field.name, value.upper())
                return True
            return False

    _load(monkeypatch, caplog, _plugin("loud", fields={"shout": Shout()}))

    @dataclass
    class Gadget:
        name: str
        word: str = dataclasses.field(default="hi", metadata={FIELD_KIND: "shout"})
        def get_name(self): return self.name
        def get_type(self): return "gadget"
        def get_description(self): return None
        def get_aliases(self): return set()
        def get_classification(self): return VCT.IMAGE_BUILDER_MODEL
        @property
        def global_id(self): return f"{self.get_classification()}::{NO_MODEL_ID}::{self.name}"

    gadget = Gadget("g1")
    clean_registry.flatten_dataclass(gadget)
    clean_registry.resolve_all()
    assert gadget.word == "HI"
