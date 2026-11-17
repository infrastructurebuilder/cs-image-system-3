# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An installed plugin that cannot be used is an absence, and two that
collide are two absences: nothing either does can change or break another.

Held on entry points the test supplies. A plugin whose module does not
import, one that is refused, and two plugins that collide are each skipped
with one error line that names them; the plugins beside them load; and
neither side of a collision wins, whichever was found first. The same class
registered by several plugins is one registration and no collision.
"""
from __future__ import annotations

import logging
import types
from typing import Any, cast

import pytest

from cs_image_system.contract.constants import VCT
from cs_image_system.contract.metadata import PluginMetadata
from cs_image_system.engine import loader

WORD = "thing"


class _CheckerOne:
    """A version checker: a classification no protocol holds, so a
    synthetic class needs only its name and its classification."""

    @classmethod
    def csis_name(cls) -> str:
        return WORD

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.VERSION_CHECKER


class _CheckerTwo(_CheckerOne):
    pass


def _point(name: str, cls: type | None = None, *, namespace: str | None = None, dist: str | None = None) -> Any:
    md = PluginMetadata(services={WORD: [cast(Any, cls)]} if cls else {}, namespace=namespace)
    return types.SimpleNamespace(name=name, dist=types.SimpleNamespace(name=dist or f"cs-image-system-{name}-plugin"),
                                 load=lambda: (lambda: md))


def _discover(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, *points: Any):
    monkeypatch.setattr(loader, "entry_points", lambda group: list(points) if group.endswith(".other") else [])
    with caplog.at_level(logging.ERROR, logger=loader.__name__):
        found, unusable = loader.discover()
    return [d.name for d in found], unusable, [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]


def test_two_plugins_with_different_classes_under_one_key_are_both_skipped(monkeypatch, caplog):
    points = [_point("alpha", _CheckerOne, namespace="shared"), _point("beta", _CheckerTwo, namespace="shared"),
              _point("gamma", _CheckerOne, namespace="apart")]
    found, unusable, lines = _discover(monkeypatch, caplog, *points)
    assert found == ["gamma"]                                          # the bystander loads
    assert sorted(u.plugin for u in unusable) == ["alpha", "beta"]
    assert all(u.cause == loader.COLLIDES and f"shared/{WORD}" in u.claim for u in unusable)
    assert len(lines) == 1 and "alpha" in lines[0] and "beta" in lines[0] and f"shared/{WORD}" in lines[0]


def test_neither_side_of_a_collision_wins_whichever_was_found_first(monkeypatch, caplog):
    forward = [_point("alpha", _CheckerOne, namespace="shared"), _point("beta", _CheckerTwo, namespace="shared")]
    assert _discover(monkeypatch, caplog, *forward)[0] == []
    assert _discover(monkeypatch, caplog, *reversed(forward))[0] == []


def test_the_same_class_from_two_plugins_is_one_registration_and_no_collision(monkeypatch, caplog):
    points = [_point("alpha", _CheckerOne, namespace="shared"), _point("beta", _CheckerOne, namespace="shared")]
    found, unusable, lines = _discover(monkeypatch, caplog, *points)
    assert found == ["alpha", "beta"] and unusable == () and lines == []


def test_two_distributions_declaring_one_entry_point_name_are_both_skipped(monkeypatch, caplog):
    points = [_point("same", dist="cs-image-system-first-plugin", namespace="first"),
              _point("same", dist="cs-image-system-second-plugin", namespace="second"),
              _point("other", namespace="other")]
    found, unusable, lines = _discover(monkeypatch, caplog, *points)
    assert found == ["other"]
    assert sorted(u.distribution for u in unusable) == ["cs-image-system-first-plugin", "cs-image-system-second-plugin"]
    assert len(lines) == 1 and "cs-image-system-first-plugin" in lines[0] and "cs-image-system-second-plugin" in lines[0]


def test_a_refused_plugin_keeps_the_words_it_would_have_registered(monkeypatch, caplog):
    """So a configuration that needs one of them can be told the plugin is
    installed and why it could not be used."""
    misfiled = _point("misfiled", _CheckerOne, namespace="mis")        # a checker is not an image plugin
    monkeypatch.setattr(loader, "entry_points", lambda group: [misfiled] if group.endswith(".image") else [])
    found, unusable = loader.discover()
    assert found == ()
    [refused] = unusable
    assert refused.cause == loader.REFUSED and refused.words == (f"{VCT.VERSION_CHECKER.value}:{WORD}",)
    assert refused.distribution == "cs-image-system-misfiled-plugin" and "misfiled" in refused.said()


def test_what_this_process_could_not_use_is_empty_for_the_installed_plugins():
    """The installed plugins of this repository are all usable; the record
    is read from the one discovery every run shares."""
    assert loader.unusable_plugins() == ()


# ------------------------------------------------------------ what a configuration that needs one is told

def _unknown(word: str):
    from cs_image_system.base.registry import UnknownTypeError
    return UnknownTypeError(VCT.RUNTIME_BUILDER_MODEL, word, ["something-else"])


def test_a_word_of_an_unusable_plugin_is_said_to_be_installed_but_unusable_with_the_cause():
    from cs_image_system.engine.commands.load_failures import unknown_type_lines
    refused = loader.Unusable("thing", "cs-image-system-thing-plugin", "runtime", loader.REFUSED,
                              "Plugin thing is refused: it lacks a member", (f"container_builder_model:{WORD}",))
    [line] = unknown_type_lines(_unknown(WORD), (refused,))
    assert "thing (cs-image-system-thing-plugin)" in line          # the plugin is named, with its cause,
    assert "it lacks a member" in line and "install the extra" not in line   # and nobody is told to install it


def test_a_word_nothing_registers_keeps_its_own_line_and_names_plugins_whose_words_are_not_known():
    from cs_image_system.engine.commands.load_failures import unknown_type_lines
    broken = loader.Unusable("broken", "cs-image-system-broken-plugin", "runtime", loader.FAILED_TO_IMPORT,
                             "ImportError: No module named 'x'")
    other = loader.Unusable("other", "cs-image-system-other-plugin", "runtime", loader.REFUSED, "refused", ("x:unrelated",))
    lines = unknown_type_lines(_unknown(WORD), (broken, other))
    assert len(lines) == 2 and WORD in lines[0]
    assert "broken (cs-image-system-broken-plugin)" in lines[1] and "No module named 'x'" in lines[1]
    assert unknown_type_lines(_unknown(WORD), ()) == [lines[0]]            # nothing unusable: the word's own line alone


def test_the_credential_prefixes_asked_are_those_of_the_declared_builders_when_given():
    from cs_image_system.engine.commands import preflight

    class _Mine:
        @classmethod
        def credential_environment_prefixes(cls):
            return ("MINE_",)

    class _Neighbour:
        @classmethod
        def credential_environment_prefixes(cls):
            return ("NEIGHBOUR_",)

    reg = types.SimpleNamespace(runtime_builder_classes=lambda: {"mine": _Mine, "neighbour": _Neighbour},
                                vct_type_registry={})
    env = {"MINE_TOKEN": "", "NEIGHBOUR_TOKEN": ""}
    assert preflight.empty_environment_credentials(reg, env) == ["MINE_TOKEN", "NEIGHBOUR_TOKEN"]      # nothing loaded: all
    assert preflight.empty_environment_credentials(reg, env, declared=[_Mine]) == ["MINE_TOKEN"]        # a loaded tree's own


def test_a_collision_is_said_with_both_plugins_to_a_configuration_that_needs_the_word():
    from cs_image_system.engine.commands.load_failures import unknown_type_lines
    collided = loader.Unusable("alpha", "cs-image-system-alpha-plugin", "runtime", loader.COLLIDES, "x",
                               (f"container_builder_model:{WORD}",), "beta (cs-image-system-beta-plugin)",
                               f"enrollment kind {WORD!r}")
    [line] = unknown_type_lines(_unknown(WORD), (collided,))
    assert "alpha (cs-image-system-alpha-plugin)" in line and "beta (cs-image-system-beta-plugin)" in line
    assert "enrollment kind" in line and "install the extra" not in line


# ------------------------------------------------------------ the ways a single plugin is skipped

def _raising(name: str, error: Exception) -> Any:
    def load() -> Any:
        raise error
    return types.SimpleNamespace(name=name, dist=types.SimpleNamespace(name=f"cs-image-system-{name}-plugin"), load=load)


def test_a_plugin_that_fails_to_import_is_skipped_named_and_the_others_load(monkeypatch, caplog):
    found, unusable, lines = _discover(monkeypatch, caplog, _raising("broken", ImportError("no module named gone")),
                                       _point("sound", _CheckerOne, namespace="sound"))
    assert found == ["sound"]
    [broken] = unusable
    assert broken.cause == loader.FAILED_TO_IMPORT and "no module named gone" in broken.detail
    assert len(lines) == 1 and "broken (cs-image-system-broken-plugin)" in lines[0] and "no module named gone" in lines[0]


def test_a_plugin_with_no_namespace_is_refused_skipped_and_the_others_load(monkeypatch, caplog):
    nameless = _point("nameless", _CheckerOne)
    nameless.dist = None                                   # no distribution to derive one from, and none named
    found, unusable, lines = _discover(monkeypatch, caplog, nameless, _point("sound", _CheckerOne, namespace="sound"))
    assert found == ["sound"]
    [refused] = unusable
    assert refused.cause == loader.REFUSED and "namespace" in refused.detail
    assert len(lines) == 1 and "nameless" in lines[0]


class _NotAGroupBuilder:
    """Filed as a group builder and carrying none of its protocol's members."""

    @classmethod
    def csis_name(cls) -> str:
        return WORD

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.GROUP_BUILDER


def test_a_plugin_whose_class_does_not_conform_is_refused_skipped_and_the_others_load(monkeypatch, caplog):
    found, unusable, lines = _discover(monkeypatch, caplog, _point("short", _NotAGroupBuilder, namespace="short"),
                                       _point("sound", _CheckerOne, namespace="sound"))
    assert found == ["sound"]
    [refused] = unusable
    assert refused.cause == loader.REFUSED and "does not conform" in refused.detail
    assert refused.words == (f"{VCT.GROUP_BUILDER.value}:{WORD}",)
    assert len(lines) == 1 and "short (cs-image-system-short-plugin)" in lines[0]


# ------------------------------------------------------------ kinds a plugin registers by a call of its own

@pytest.fixture
def kinds(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """The contract's two shared registries, the test's own for its length:
    the enrollment kinds empty, the field kinds as the system has them."""
    from cs_image_system.contract import enrollment, field_kinds
    monkeypatch.setattr(enrollment, "_KINDS", {})
    monkeypatch.setattr(field_kinds, "_HANDLERS", dict(field_kinds._HANDLERS))
    return types.SimpleNamespace(enrollment=enrollment, field_kinds=field_kinds)


def _registering(name: str, register) -> Any:
    """A plugin that registers a kind when it loads, as an identity
    plugin's module does at import."""
    md = PluginMetadata(services={WORD: [cast(Any, _CheckerOne)]}, namespace=name)

    def load() -> Any:
        register()
        return lambda: md
    return types.SimpleNamespace(name=name, dist=types.SimpleNamespace(name=f"cs-image-system-{name}-plugin"), load=load)


def _enrolls(kinds, name: str, kind: str = "token") -> Any:
    return _registering(name, lambda: kinds.enrollment.register_enrollment_kind(
        kind, script_lines=lambda params: [name], ansible_tasks=lambda params: []))


def test_two_plugins_registering_one_enrollment_kind_are_both_skipped_and_the_kind_is_neithers(
        monkeypatch, caplog, kinds):
    found, unusable, lines = _discover(monkeypatch, caplog, _enrolls(kinds, "alpha"), _enrolls(kinds, "beta"),
                                       _enrolls(kinds, "gamma", kind="another"))
    assert found == ["gamma"] and kinds.enrollment.registered_kinds() == ["another"]
    assert sorted(u.plugin for u in unusable) == ["alpha", "beta"]
    assert all(u.cause == loader.COLLIDES and u.claim == "enrollment kind 'token'" for u in unusable)
    assert len(lines) == 1 and "alpha" in lines[0] and "beta" in lines[0] and "enrollment kind 'token'" in lines[0]


def test_neither_enrollment_kind_wins_whichever_plugin_was_found_first(monkeypatch, caplog, kinds):
    for first, second in (("alpha", "beta"), ("beta", "alpha")):
        kinds.enrollment._KINDS.clear()
        found, _unusable, _lines = _discover(monkeypatch, caplog, _enrolls(kinds, first), _enrolls(kinds, second))
        assert found == [] and kinds.enrollment.registered_kinds() == []


def test_two_plugins_registering_one_field_kind_are_both_skipped(monkeypatch, caplog, kinds):
    def handles(name: str) -> Any:
        return _registering(name, lambda: kinds.field_kinds.register_field_kind("shiny", kinds.field_kinds.FieldKindHandler()))
    found, unusable, lines = _discover(monkeypatch, caplog, handles("alpha"), handles("beta"),
                                       _point("sound", _CheckerOne, namespace="sound"))
    assert found == ["sound"] and kinds.field_kinds.get_field_kind_handler("shiny") is None
    assert sorted(u.plugin for u in unusable) == ["alpha", "beta"]
    assert len(lines) == 1 and "alpha" in lines[0] and "beta" in lines[0] and "field kind 'shiny'" in lines[0]


def test_a_plugin_that_replaces_one_of_the_systems_own_field_kinds_is_skipped_and_the_kind_put_back(
        monkeypatch, caplog, kinds):
    own = kinds.field_kinds.FieldKindHandler()
    kinds.field_kinds._HANDLERS["own"] = own
    grabby = _registering("grabby", lambda: kinds.field_kinds.register_field_kind("own", kinds.field_kinds.FieldKindHandler()))
    found, unusable, lines = _discover(monkeypatch, caplog, grabby, _point("sound", _CheckerOne, namespace="sound"))
    assert found == ["sound"] and kinds.field_kinds.get_field_kind_handler("own") is own
    [skipped] = unusable
    assert skipped.plugin == "grabby" and skipped.cause == loader.COLLIDES and skipped.claim == "field kind 'own'"
    assert len(lines) == 1 and "grabby" in lines[0] and "field kind 'own'" in lines[0]


def test_what_a_refused_plugin_registered_on_the_way_is_taken_back(monkeypatch, caplog, kinds):
    refused = _enrolls(kinds, "nameless")
    refused.dist = None
    md = PluginMetadata(services={WORD: [cast(Any, _CheckerOne)]})          # and its metadata names no namespace
    refused.load = lambda: (kinds.enrollment.register_enrollment_kind(
        "token", script_lines=lambda p: [], ansible_tasks=lambda p: []), lambda: md)[1]
    found, unusable, _lines = _discover(monkeypatch, caplog, refused)
    assert found == [] and [u.cause for u in unusable] == [loader.REFUSED]
    assert kinds.enrollment.registered_kinds() == []


# ------------------------------------------------------------ an image-source block for another plugin's runtime

def _runtime(name: str, blocks: tuple[str, ...]) -> Any:
    """A plugin that registers the runtime type ``name`` and ships an
    image-source catalog with a block for each of ``blocks``."""
    cls = type(f"Runtime_{name}", (), {
        "csis_name": classmethod(lambda cls: name),
        "csis_classifier": classmethod(lambda cls: VCT.RUNTIME_BUILDER),
        "image_source_entries": classmethod(lambda cls: [{"family": "x", "sources": {b: {"name": name} for b in blocks}}]),
    })
    md = PluginMetadata(services={name: [cast(Any, cls)]}, namespace=name)
    return types.SimpleNamespace(name=name, dist=types.SimpleNamespace(name=f"cs-image-system-{name}-plugin"),
                                 load=lambda: (lambda: md))


def test_a_plugin_shipping_an_image_source_block_for_anothers_runtime_type_skips_both(monkeypatch, caplog):
    monkeypatch.setattr(loader, "check_conformance", lambda pname, md: None)     # the classes here are stand-ins
    found, unusable, lines = _discover(monkeypatch, caplog, _runtime("alpha", ("alpha",)),
                                       _runtime("beta", ("beta", "alpha")), _runtime("gamma", ("gamma", "nobodys")))
    assert found == ["gamma"]                             # a block for a type nobody registers is no collision
    assert sorted(u.plugin for u in unusable) == ["alpha", "beta"]
    assert all(u.cause == loader.COLLIDES and u.claim == "image-source block 'alpha'" for u in unusable)
    assert len(lines) == 1 and "alpha (cs-image-system-alpha-plugin)" in lines[0] \
        and "beta (cs-image-system-beta-plugin)" in lines[0] and "image-source block 'alpha'" in lines[0]


# ------------------------------------------------------------ who is asked about a failed load

def test_a_failed_load_is_classified_only_by_the_classes_the_configuration_declares():
    """A provider installed beside a configuration and not used by it is
    never asked what a failure means: it cannot claim another's failure."""
    from cs_image_system.contract.session import LoadFailureReport
    from cs_image_system.engine.commands import load_failures

    def claiming(word: str) -> type:
        return type(f"Builder_{word}", (), {
            "csis_name": classmethod(lambda cls: word),
            "classify_failure": classmethod(
                lambda cls, exc: LoadFailureReport("environment", [f"{word} claims it"], code=2)),
        })

    reg = cast(Any, types.SimpleNamespace(builders={"m1": claiming("neighbour"), "m2": claiming("mine")}))
    failed = RuntimeError("the daemon did not answer")
    # nothing known of the configuration: every installed class is asked, and the first to claim it answers
    assert cast(Any, load_failures.classify_load_failure(failed, reg)).lines == ["neighbour claims it"]
    # the configuration declares only `mine` (a qualified word names it too): the neighbour is not asked
    for declared in (["mine"], ["ns/mine"]):
        assert cast(Any, load_failures.classify_load_failure(failed, reg, declared_types=declared)).lines == ["mine claims it"]
    # a configuration that declares neither: nobody claims it, and it keeps its traceback
    assert load_failures.classify_load_failure(failed, reg, declared_types=["something-else"]) is None
