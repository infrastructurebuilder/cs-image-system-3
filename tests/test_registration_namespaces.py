# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Registrations carry their plugin's namespace.

Every class-level registry table is keyed by ``RegistrationKey``
(classification, namespace, name). The namespace is derived from the
plugin's distribution name (``cs-image-system-`` and ``-plugin`` dropped)
or named by ``PluginMetadata.namespace``; a plugin with neither is refused
at discovery with the field named. A bare ``type:`` word resolves when one
class answers to it, whatever the namespaces carrying it; different
classes under one word are ambiguous, and the error names every qualified
form (``<namespace>/<name>``), which resolves directly. The same class
under several namespaces is one registration (three terraform roots, one
version checker); a different class under one key is the collision.
"""
from __future__ import annotations

import types
from typing import Any, cast

import pytest

from cs_image_system.base import loader
from cs_image_system.base.registry import AmbiguousTypeError, RegistrationKey, Registry
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.metadata import PluginMetadata

# version checkers: a classification the contract declares no protocol for,
# so a synthetic class needs only csis_name/csis_classifier
WORD = "tofu"


class _CheckerOne:
    @classmethod
    def csis_name(cls) -> str:
        return WORD

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.VERSION_CHECKER


class _CheckerTwo(_CheckerOne):
    pass


def _plugin(namespace: str | None, cls: type) -> PluginMetadata:
    return PluginMetadata(services={WORD: [cast(Any, cls)]}, namespace=namespace)


def _load(reg: Registry, md: PluginMetadata, namespace: str) -> None:
    """What the loader does for one plugin's metadata."""
    reg.register_plugin_metadata(md, namespace=namespace)
    for services in md.services.values():
        for service in services:
            reg.register_service(service, namespace=namespace)


@pytest.fixture
def two_plugins() -> Registry:
    reg = Registry()
    _load(reg, _plugin(None, _CheckerOne), "one")
    _load(reg, _plugin(None, _CheckerTwo), "two")
    return reg


# --------------------------------------------------------------- two plugins, one word

def test_two_plugins_register_one_word_under_one_classification_and_the_load_succeeds(two_plugins: Registry):
    keys = two_plugins.registration_keys(VCT.VERSION_CHECKER)
    assert keys == [RegistrationKey(VCT.VERSION_CHECKER, "one", WORD), RegistrationKey(VCT.VERSION_CHECKER, "two", WORD)]
    assert two_plugins.models[keys[0]] is _CheckerOne and two_plugins.models[keys[1]] is _CheckerTwo
    assert two_plugins.registry[keys[0]] is _CheckerOne and two_plugins.registry[keys[1]] is _CheckerTwo
    # the typed key, never a joined string
    assert all(isinstance(k, RegistrationKey) for k in two_plugins.models) and all(isinstance(k, tuple) for k in two_plugins.registry)
    assert two_plugins.vct_type_registry[VCT.VERSION_CHECKER] == [_CheckerOne, _CheckerTwo]
    assert two_plugins.reverse_registry[_CheckerOne] == [keys[0]]


def test_the_bare_word_is_refused_naming_both_qualified_forms(two_plugins: Registry):
    with pytest.raises(AmbiguousTypeError) as refused:
        two_plugins.get_model(VCT.VERSION_CHECKER, WORD)
    message = str(refused.value)
    assert message == f"type '{WORD}' is ambiguous under version_checker: 2 plugins register it; write one of one/{WORD}, two/{WORD}"
    assert refused.value.keys == two_plugins.registration_keys(VCT.VERSION_CHECKER)
    with pytest.raises(AmbiguousTypeError, match=f"one/{WORD}, two/{WORD}"):
        two_plugins.get_builder_for_model(WORD, VCT.VERSION_CHECKER)
    # the listing by classification shows the qualified forms where the bare word is taken twice
    assert two_plugins.models_under(VCT.VERSION_CHECKER) == {f"one/{WORD}": _CheckerOne, f"two/{WORD}": _CheckerTwo}


def test_each_qualified_form_resolves_to_its_class(two_plugins: Registry):
    assert two_plugins.get_model(VCT.VERSION_CHECKER, f"one/{WORD}") is _CheckerOne
    assert two_plugins.get_model(VCT.VERSION_CHECKER, f"two/{WORD}") is _CheckerTwo
    assert two_plugins.get_builder_for_model(f"one/{WORD}", VCT.VERSION_CHECKER) is _CheckerOne
    assert two_plugins.get_builder_for_model(f"two/{WORD}", VCT.VERSION_CHECKER) is _CheckerTwo
    assert two_plugins.get_model(VCT.VERSION_CHECKER, f"three/{WORD}") is None, "a namespace nobody registered"
    assert two_plugins.get_model(VCT.VERSION_CHECKER, "nobody") is None, "a word nobody registered"
    assert two_plugins.get_model(VCT.INSTANCE_BUILDER_MODEL, WORD) is None, "another classification"


def test_register_service_refuses_a_second_class_under_the_same_key(two_plugins: Registry):
    with pytest.raises(ValueError, match=f"Type Collision: service one/{WORD} under version_checker"):
        two_plugins.register_service(cast(Any, _CheckerTwo), namespace="one")
    # the same class again under the same key is the same registration
    two_plugins.register_service(cast(Any, _CheckerOne), namespace="one")
    assert two_plugins.reverse_registry[_CheckerOne] == [RegistrationKey(VCT.VERSION_CHECKER, "one", WORD)]
    # register_plugin_metadata holds the models table to the same rule
    with pytest.raises(ValueError, match=f"Type Collision: one/{WORD} under version_checker"):
        two_plugins.register_plugin_metadata(_plugin(None, _CheckerTwo), namespace="one")
    # and a service needs its namespace
    with pytest.raises(TypeError):
        two_plugins.register_service(cast(Any, _CheckerOne))  # type: ignore[call-arg]


def test_validate_reports_the_ambiguous_word_as_one_configuration_error(two_plugins: Registry):
    from cs_image_system.base.commands.load_failures import classify_load_failure
    try:
        two_plugins.get_model(VCT.VERSION_CHECKER, WORD)
    except AmbiguousTypeError as e:
        failure = classify_load_failure(e)
    else:  # pragma: no cover
        pytest.fail("not refused")
    assert failure is not None and failure.kind == "configuration" and failure.code == 1
    assert failure.lines == [f" - type '{WORD}' is ambiguous under version_checker: 2 plugins register it; "
                             f"write one of one/{WORD}, two/{WORD}", "Validation failed with 1 error(s)."]


# --------------------------------------------------- the same class under three namespaces

ROOTS = {"tf-ebs-instance": "cs_image_system.tf_ebs_instance_plugin.main",
         "tf-gcp": "cs_image_system.tf_gcp_plugin.main",
         "tf-docker": "cs_image_system.tf_docker_plugin.main"}


def test_the_same_class_under_three_namespaces_is_one_registration():
    """The version checker every terraform-root plugin carries, so a tree
    with roots on one provider alone still has its tool checked: three keys,
    one class, and the bare word resolves to it (not ambiguous)."""
    from cs_image_system.tofu_roots.tofu_instance_builder import TofuVersionChecker
    reg = Registry()
    for namespace, module in ROOTS.items():
        _load(reg, __import__(module, fromlist=["initialize"]).initialize(), namespace)
    keys = [k for k in reg.registration_keys(VCT.VERSION_CHECKER) if k.name == WORD]
    assert [k.namespace for k in keys] == sorted(ROOTS)
    assert reg.get_model(VCT.VERSION_CHECKER, WORD) is TofuVersionChecker
    assert reg.get_builder_for_model(WORD, VCT.VERSION_CHECKER) is TofuVersionChecker
    for namespace in ROOTS:
        assert reg.get_model(VCT.VERSION_CHECKER, f"{namespace}/{WORD}") is TofuVersionChecker
    assert reg.models_under(VCT.VERSION_CHECKER)[WORD] is TofuVersionChecker
    assert reg.vct_type_registry[VCT.VERSION_CHECKER].count(TofuVersionChecker) == 1
    assert sorted(k.namespace for k in reg.reverse_registry[TofuVersionChecker]) == sorted(ROOTS)


def test_the_installed_roots_resolve_the_checker_by_the_bare_word():
    from cs_image_system.base.registry import current_registry
    from cs_image_system.tofu_roots.tofu_instance_builder import TofuVersionChecker
    from v2_support import reset_singletons
    reset_singletons()
    reg = current_registry()
    assert reg.get_model(VCT.VERSION_CHECKER, WORD) is TofuVersionChecker
    assert reg.get_model(VCT.VERSION_CHECKER, f"tf-gcp/{WORD}") is TofuVersionChecker
    # the installed instance-builder word is one root's alone, so bare and qualified agree
    aws_root = reg.get_model(VCT.INSTANCE_BUILDER_MODEL, WORD)
    assert aws_root is not None and reg.get_model(VCT.INSTANCE_BUILDER_MODEL, f"tf-ebs-instance/{WORD}") is aws_root
    # the core's own registrations carry the core's namespace
    assert reg.get_model(VCT.VERSION_CHECKER, "base/executable") is reg.get_model(VCT.VERSION_CHECKER, "executable")


# ------------------------------------------------------------- the namespace's derivation

@pytest.mark.parametrize("dist, namespace", [
    ("cs-image-system-aws-runtime-plugin", "aws-runtime"),
    ("cs-image-system-tf-ebs-instance-plugin", "tf-ebs-instance"),
    ("cs-image-system-okta-opa-plugin", "okta-opa"),
    ("cs-image-system-contract-example-plugin", "contract-example"),
    ("cs-image-system-tofu-roots", "tofu-roots"),
    ("cs-image-system-base", "base"),
    ("somebody-elses-plugin", "somebody-elses"),
    ("acme-roots", "acme-roots"),
    ("CS-Image-System-Thing-Plugin", "thing"),
])
def test_the_namespace_is_derived_from_the_distribution_name(dist: str, namespace: str):
    assert loader.namespace_of_distribution(dist) == namespace


def test_every_installed_plugin_carries_the_namespace_of_its_distribution():
    loader.discover_plugins()
    derived = {d.name: d.derived_namespace for d in loader._discovered_plugins()}
    assert derived["base_plugin"] == "base"
    assert derived["aws_plugin"] == "aws-runtime"
    assert derived["contract_example_plugin"] == "contract-example"
    assert derived["okta_opa_plugin"] == "okta-opa"
    assert derived["tf-ebs-instance-plugin"] == "tf-ebs-instance"
    assert all(ns for ns in derived.values()), derived


def test_the_metadata_field_overrides_the_derivation():
    md = PluginMetadata(namespace="chosen")
    assert loader.namespace_for("p", md, "derived") == "chosen"
    assert loader.namespace_for("p", PluginMetadata(), "derived") == "derived"
    assert Registry.namespace_of(md) == "chosen" and Registry.namespace_of(PluginMetadata(), "derived") == "derived"
    with pytest.raises(loader.PluginNamespaceError, match="may not contain '/'"):
        loader.namespace_for("p", PluginMetadata(namespace="a/b"), None)


class _FakeEntryPoints:
    """What ``entry_points(group=...)`` answers: a sized iterable of entry
    points, each by name."""

    def __init__(self, *points: Any) -> None:
        self._points = {p.name: p for p in points}

    def __len__(self) -> int:
        return len(self._points)

    def __iter__(self):
        return iter(self._points.values())

    def __getitem__(self, name: str) -> Any:
        return self._points[name]


def _with_entry_points(monkeypatch, *points: Any) -> None:
    def fake_entry_points(group: str) -> _FakeEntryPoints:
        return _FakeEntryPoints(*points) if group.endswith(".runtime") else _FakeEntryPoints()
    monkeypatch.setattr(loader, "entry_points", fake_entry_points)


def test_a_plugin_without_a_distribution_and_without_the_field_is_refused_at_load(monkeypatch):
    nameless = types.SimpleNamespace(name="nameless", dist=None, load=lambda: (lambda: PluginMetadata()))
    _with_entry_points(monkeypatch, nameless)
    with pytest.raises(loader.PluginNamespaceError) as refused:
        loader._discovered_plugins.__wrapped__()
    assert str(refused.value) == ("Plugin nameless is refused: its entry point has no distribution to derive a namespace "
                                  "from, and its metadata names none; set PluginMetadata.namespace")


def test_a_plugin_without_a_distribution_loads_when_its_metadata_names_the_namespace(monkeypatch):
    named = types.SimpleNamespace(name="named", dist=None, load=lambda: (lambda: PluginMetadata(namespace="mine")))
    _with_entry_points(monkeypatch, named)
    found = loader._discovered_plugins.__wrapped__()
    assert [(d.plugin_type, d.name, d.derived_namespace) for d in found] == [("runtime", "named", None)]
    assert loader.namespace_for("named", found[0].initializer(), found[0].derived_namespace) == "mine"


def test_a_plugin_with_a_distribution_takes_its_namespace_from_it(monkeypatch):
    dist = types.SimpleNamespace(name="cs-image-system-stand-in-plugin")
    shipped = types.SimpleNamespace(name="shipped", dist=dist, load=lambda: (lambda: PluginMetadata()))
    _with_entry_points(monkeypatch, shipped)
    found = loader._discovered_plugins.__wrapped__()
    assert found[0].derived_namespace == "stand-in"


# ------------------------------------------------------------------ what is recorded

def test_a_bare_word_stays_bare_and_a_qualified_word_keeps_its_namespace():
    """The orchestrator canonicalises an alias but never rewrites a bare
    word to its qualified form (the mod fingerprint hashes the type word)
    nor a qualified one to the bare word."""
    from cs_image_system.base.registry import bare_name, split_qualified
    assert split_qualified(WORD) == (None, WORD)
    assert split_qualified(f"tf-gcp/{WORD}") == ("tf-gcp", WORD)
    assert bare_name(f"tf-gcp/{WORD}") == WORD == bare_name(WORD)
    assert RegistrationKey(VCT.VERSION_CHECKER, "tf-gcp", WORD).qualified == f"tf-gcp/{WORD}"


def test_the_default_word_keeps_its_meaning(two_plugins: Registry):
    two_plugins.set_default_for(VCT.VERSION_CHECKER, f"one/{WORD}")
    assert two_plugins.get_default_for(VCT.VERSION_CHECKER) == f"one/{WORD}"
    assert two_plugins.get_model(VCT.VERSION_CHECKER, two_plugins.get_default_for(VCT.VERSION_CHECKER) or "") is _CheckerOne
