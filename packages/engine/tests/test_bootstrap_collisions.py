# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A plugin's setup section that cannot be used is skipped and named, and
two plugins never share a section name or a provider declaration silently.

Held on entry points the test supplies: a section entry point that fails is
skipped and the interview still has the others; a section name two plugins
claim is neither's; a plugin that claims the system's own section is
skipped alone; and two sections that declare one provider differently
refuse the generated root, naming both.
"""
from __future__ import annotations

import logging
import types
from typing import Any

import pytest

from cs_image_system.contract.bootstrap import Refused, Rendered, Section
from cs_image_system.engine.bootstrap import hcl, sections


def _section(name: str) -> Section:
    return Section(name=name, title=name, questions=(), render=lambda answers: Rendered())


def _point(name: str, answer: Any) -> Any:
    def load() -> Any:
        if isinstance(answer, Exception):
            raise answer
        return lambda: answer
    return types.SimpleNamespace(name=name, dist=types.SimpleNamespace(name=f"cs-image-system-{name}-plugin"), load=load)


def _discover(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, *points: Any):
    monkeypatch.setattr(sections, "entry_points", lambda group: list(points))
    with caplog.at_level(logging.ERROR, logger=sections.__name__):
        found = sections.discover()
    return [s.name for s in found], [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]


def test_a_section_entry_point_that_fails_is_skipped_named_and_the_others_are_offered(monkeypatch, caplog):
    found, lines = _discover(monkeypatch, caplog, _point("broken", ImportError("gone")),
                             _point("stranger", "not a section"), _point("sound", _section("sound")))
    assert found == ["github", "sound"]
    assert len(lines) == 2
    assert "broken (cs-image-system-broken-plugin)" in lines[0] and "gone" in lines[0]
    assert "stranger (cs-image-system-stranger-plugin)" in lines[1]


def test_a_section_name_two_plugins_claim_is_neithers_whichever_was_found_first(monkeypatch, caplog):
    pair = [_point("alpha", _section("cloud")), _point("beta", _section("cloud"))]
    for points in (pair, list(reversed(pair))):
        caplog.clear()
        found, lines = _discover(monkeypatch, caplog, *points, _point("sound", _section("sound")))
        assert found == ["github", "sound"]
        assert len(lines) == 1 and "alpha" in lines[0] and "beta" in lines[0] and "bootstrap section 'cloud'" in lines[0]


def test_a_plugin_that_claims_the_systems_own_section_is_skipped_alone(monkeypatch, caplog):
    found, lines = _discover(monkeypatch, caplog, _point("grabby", _section("github")))
    assert found == ["github"]
    assert len(lines) == 1 and "grabby" in lines[0] and "bootstrap section 'github'" in lines[0]


def _root(**rendered: Rendered) -> dict[str, str]:
    return hcl.render_root(dict(rendered), module_source=lambda module: f"./{module}", repository=None, secrets_dir=None)


def test_two_sections_declaring_one_provider_the_same_way_share_it():
    spec = {"source": "vendor/thing", "version": ">= 1.0"}
    files = _root(a=Rendered(required_providers={"thing": dict(spec)}), b=Rendered(required_providers={"thing": dict(spec)}))
    assert files["providers.tf"].count('source  = "vendor/thing"') == 1


def test_two_sections_declaring_one_provider_differently_are_refused_and_both_named():
    with pytest.raises(Refused) as refused:
        _root(a=Rendered(required_providers={"thing": {"source": "vendor/thing", "version": ">= 1.0"}}),
              b=Rendered(required_providers={"thing": {"source": "vendor/thing", "version": ">= 2.0"}}))
    said = str(refused.value)
    assert "'thing'" in said and "sections a and b" in said and ">= 1.0" in said and ">= 2.0" in said
