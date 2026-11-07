# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A plugin's entry-point group names the kind it registers.

The loader walks ``cs_image_system.plugins.<group>`` for every group in
``PLUGIN_TYPES`` and registers every class under the classification the
class itself reports, so the group used to decide load order and nothing
else: a group builder declared under ``runtime`` loaded as a group builder.
Now a plugin found under a group is held to it at discovery: at least one
of its classes carries the group's classification, or the plugin is
refused naming the group it chose, what it registers and the group that
fits. A plugin may register more than its kind; ``base`` and ``other``
name no kind.
"""
from __future__ import annotations

import types
from typing import Any, cast

import pytest

from cs_image_system.base import loader
from cs_image_system.contract.constants import VCT, PLUGIN_TYPES
from cs_image_system.contract.metadata import PluginMetadata


def _registering(*kinds: VCT) -> list[PluginMetadata]:
    """One metadata record whose services carry one class per kind, as
    version checkers do (no protocol to conform to)."""
    classes: list[Any] = [
        type(f"Class{kind.name}", (), {"csis_name": classmethod(lambda cls: "k"),
                                        "csis_classifier": classmethod(lambda cls, k=kind: k)})
        for kind in kinds]
    return [PluginMetadata(services={"k": [cast(Any, c) for c in classes]}, namespace="t")]


def test_every_installed_plugin_registers_its_groups_kind():
    """The shipped plugins pass the check as discovered (the test session
    discovered them already; this reads the cached result)."""
    for found in loader._discovered_plugins():
        loader.check_group(found.name, found.plugin_type, loader._metadata_of(found.initializer))


def test_every_named_group_but_base_and_other_has_a_kind():
    assert set(loader.GROUP_CLASSIFICATIONS) == {g for g, _ in PLUGIN_TYPES} - {"base", "other"}


def test_a_group_builder_under_runtime_is_refused_naming_the_fitting_group():
    with pytest.raises(loader.PluginGroupError) as refused:
        loader.check_group("dummy", "runtime", _registering(VCT.GROUP_BUILDER_MODEL, VCT.USER_BUILDER))
    text = str(refused.value)
    assert "cs_image_system.plugins.runtime" in text and "no runtime class" in text
    assert "group_builder_model" in text and "fits what it registers: group, user" in text


def test_a_plugin_may_register_more_than_its_groups_kind():
    loader.check_group("tf", "instance", _registering(VCT.INSTANCE_BUILDER_MODEL, VCT.STORAGE_BUILDER_MODEL))
    loader.check_group("identity", "group", _registering(VCT.GROUP_BUILDER, VCT.USER_BUILDER))


def test_a_plugin_of_no_named_kind_is_told_to_declare_other():
    with pytest.raises(loader.PluginGroupError, match="declares cs_image_system.plugins.other"):
        loader.check_group("checker", "image", _registering(VCT.VERSION_CHECKER))
    loader.check_group("checker", "other", _registering(VCT.VERSION_CHECKER))
    loader.check_group("core", "base", _registering(VCT.VERSION_CHECKER))


def test_a_runtime_plugin_passes_by_its_cloud_or_container_builder_model():
    loader.check_group("aws", "runtime", _registering(VCT.CLOUD_BUILDER_MODEL, VCT.RUNTIME_BUILDER))
    loader.check_group("docker", "runtime", _registering(VCT.CONTAINER_BUILDER_MODEL))


def test_the_injected_models_count_as_registrations():
    loader.check_group("inj", "user", [PluginMetadata(injected_models={VCT.USER_BUILDER_MODEL: cast(Any, object)},
                                                     namespace="t")])


def test_discovery_refuses_a_mis_grouped_plugin(monkeypatch):
    """The check runs at discovery, after the conformance check, so a
    shipped plugin under the wrong group never loads (a version checker,
    which no protocol holds, filed under ``image``)."""
    class _Points:
        def __init__(self, *points: Any) -> None:
            self._points = {p.name: p for p in points}
        def __len__(self) -> int:
            return len(self._points)
        def __iter__(self):
            return iter(self._points.values())
        def __getitem__(self, name: str) -> Any:
            return self._points[name]
    md = _registering(VCT.VERSION_CHECKER)
    point = types.SimpleNamespace(name="misfiled", dist=None, load=lambda: (lambda: md))
    monkeypatch.setattr(loader, "entry_points", lambda group: _Points(point) if group.endswith(".image") else _Points())
    with pytest.raises(loader.PluginGroupError, match="misfiled"):
        loader._discovered_plugins.__wrapped__()
