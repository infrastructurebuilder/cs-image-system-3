# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Characterization tests for the string stage's tree renderer.

These lock in the behavior of ``template_utils.interpolate_tree`` /
``scope_named_key`` (scope-aware ``this`` / ``this.parent`` + path-preserving
passthrough) so later refactors that de-duplicate the rendering primitives
cannot silently change it. The string stage walks the ONE parsed document:
nothing here dumps YAML text or parses it again. Where a case came from the
days the stage rendered serialized text, the document is still built from
the same YAML so the escaping the dumper would produce is on record.
"""
import copy
import logging

import yaml

from cs_image_system.base import template_utils as tu


# --------------------------------------------------------------------------
# interpolate_tree: value-based rendering, never the serialized text
# --------------------------------------------------------------------------

def test_interpolate_resolves_env_bracket_subscript(monkeypatch):
    monkeypatch.setenv("USER", "testuser")
    # A single-quoted YAML scalar with a bracket+quote subscript -- this used to
    # raise Jinja TemplateSyntaxError when the *serialized text* was templated.
    doc = yaml.safe_load(yaml.dump({"config": {"x": "{{ ENV['USER'] }} and more"}}))
    out = tu.interpolate_tree(doc, include_ENV=True)
    assert out["config"]["x"] == "testuser and more"


def test_interpolate_resolves_env_dot_access(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    out = tu.interpolate_tree({"systemuser": "{{ ENV.USER }}"}, include_ENV=True)
    assert out["systemuser"] == "alice"


def test_interpolate_backslash_wrapped_script_does_not_raise():
    # A long double-quoted scalar PyYAML wraps with line-continuation backslashes
    # inside a {{ }} -- previously "unexpected char '\\'".
    long = "echo \"" + ("x" * 120) + " {{ config.setting }}\"\n./run.sh\n"
    doc = yaml.safe_load(yaml.dump({"config": {"setting": "VAL"}, "script": long}))
    # Must not raise TemplateSyntaxError, and the tag resolves against top-level config.
    out = tu.interpolate_tree(doc, include_ENV=True)
    assert "VAL" in out["script"] and "{{" not in out["script"]


def test_interpolate_no_tags_returns_the_same_tree():
    doc = {"a": 1, "b": "two", "c": {"d": [1, "e"]}}
    assert tu.interpolate_tree(doc) is doc


def test_interpolate_rendered_leaf_stays_a_string():
    """A template renders to TEXT, and the text stays a string whatever it
    looks like: ``"{{ config.port }}"`` over ``port: 22`` is ``'22'``, not 22,
    and a rendered boolean is ``'True'``. (The former dump/parse round trip
    gave the same answer, because the YAML dumper quotes a string that
    would read back as another scalar; the leaf's declared field, if any,
    coerces it when the document is structured.) Untouched leaves keep
    their parsed types."""
    doc = {"config": {"port": 22, "flag": True, "when": "2026-01-01"},
           "port": "{{ config.port }}", "flag": "{{ config.flag }}",
           "when": "{{ config.when }}", "n": 7, "f": 1.5, "none": None}
    out = tu.interpolate_tree(doc, include_ENV=True)
    assert out["port"] == "22" and isinstance(out["port"], str)
    assert out["flag"] == "True" and isinstance(out["flag"], str)
    assert out["when"] == "2026-01-01" and isinstance(out["when"], str)
    assert out["n"] == 7 and isinstance(out["n"], int)
    assert out["f"] == 1.5 and out["none"] is None
    assert out["config"] == {"port": 22, "flag": True, "when": "2026-01-01"}


def test_interpolate_converges_across_cycles_and_leaves_the_input_alone():
    # b needs a, c needs b: three cycles, and the caller's tree is not mutated
    doc = {"a": "A", "b": "{{ a }}-b", "c": "{{ b }}-c"}
    before = copy.deepcopy(doc)
    out = tu.interpolate_tree(doc, cycles=5)
    assert out == {"a": "A", "b": "A-b", "c": "A-b-c"}
    assert doc == before


def test_interpolate_warns_when_max_cycles_do_not_converge(caplog):
    # a value whose rendering never settles: each cycle makes a longer string
    doc = {"a": "x", "b": "{{ b }}{{ a }}"}
    with caplog.at_level(logging.WARNING, logger="cs_image_system.base.template_utils"):
        out = tu.interpolate_tree(doc, cycles=3)
    assert any("max cycles (3)" in r.getMessage() for r in caplog.records)
    assert out["b"].endswith("xxx")


def test_interpolate_passes_an_unresolvable_tag_through():
    out = tu.interpolate_tree({"a": "{{ nothing.here }}"})
    assert out["a"] == "{{ nothing.here }}"


def test_sort_mappings_orders_every_mapping_and_nothing_else():
    """The loader presents the document with its mappings' keys sorted, the
    order the former YAML dump gave the emission; lists keep their order,
    leaves their types, and the caller's tree is not touched."""
    doc = {"zeta": [{"b": 1, "a": {"y": "Y", "x": "X"}}, "s"], "alpha": "A", "Mid": 2}
    before = copy.deepcopy(doc)
    out = tu.sort_mappings(doc)
    assert list(out) == ["Mid", "alpha", "zeta"]                 # ASCII order, as the dumper sorts
    assert out["zeta"] == [{"a": {"x": "X", "y": "Y"}, "b": 1}, "s"]
    assert list(out["zeta"][0]) == ["a", "b"] and list(out["zeta"][0]["a"]) == ["x", "y"]
    assert doc == before and list(doc) == ["zeta", "alpha", "Mid"]
    # keys that do not compare keep their order, as the dumper left them
    assert list(tu.sort_mappings({1: "a", "b": 2})) == [1, "b"]


# --------------------------------------------------------------------------
# scope_named_key: `this` = nearest dict, `this.parent` = owner, passthrough
# --------------------------------------------------------------------------

def _named(doc, key="os_builders"):
    return tu.scope_named_key(doc, plugin_key=key, include_ENV=True)


def test_named_key_renders_in_place_on_the_given_tree():
    doc = {"os_builders": [{"name": "deb", "out": "{{ this.name }}"}], "other": [{"x": "{{ this.x }}"}]}
    out = _named(doc)
    assert out is doc and doc["os_builders"][0]["out"] == "deb"
    # a key that is not the one scoped is untouched, and a document without
    # the key, or one that is no mapping, is returned as it is
    assert doc["other"] == [{"x": "{{ this.x }}"}]
    assert _named({"a": 1}) == {"a": 1} and _named(["x"]) == ["x"]


def test_named_key_this_is_nearest_item():
    doc = {"os_builders": [{"name": "deb", "family": "debian",
                            "out": "{{ this.name }}-{{ this.family }}"}]}
    assert _named(doc)["os_builders"][0]["out"] == "deb-debian"


def test_named_key_this_parent_is_owner():
    doc = {"os_builders": [{
        "name": "deb", "family": "debian",
        "runtimes": [{"name": "aws-deb", "out": "{{ this.name }}-on-{{ this.parent.name }}-{{ this.parent.family }}"}],
    }]}
    rt = _named(doc)["os_builders"][0]["runtimes"][0]
    assert rt["out"] == "aws-deb-on-deb-debian"


def test_named_key_unresolved_path_preserved_with_full_prefix():
    # `this.os` does not exist on the item -> must stay intact, not degrade to {{ os.family }}
    doc = {"os_builders": [{"name": "deb", "out": "{{ this.os.family }}"}]}
    assert _named(doc)["os_builders"][0]["out"] == "{{ this.os.family }}"


def test_named_key_item_config_shadows_document_config():
    doc = {
        "config": {"shared": "DOC"},
        "os_builders": [{"name": "deb", "config": {"local": "LOCAL"},
                         "out": "{{ config.local }}"}],
    }
    assert _named(doc)["os_builders"][0]["out"] == "LOCAL"


# --------------------------------------------------------------------------
# `this.display_name` synonym: string stage resolves it to the raw name so the
# same template works at both stages (object stage uses the model property).
# --------------------------------------------------------------------------

def test_named_key_this_display_name_resolves_to_name():
    doc = {"os_builders": [{"name": "My-Deb-11", "out": "{{ this.display_name }}"}]}
    assert _named(doc)["os_builders"][0]["out"] == "My-Deb-11"


def test_named_key_this_parent_display_name():
    doc = {"os_builders": [{
        "name": "My-Deb",
        "runtimes": [{"name": "RT", "out": "{{ this.display_name }}-on-{{ this.parent.display_name }}"}],
    }]}
    rt = _named(doc)["os_builders"][0]["runtimes"][0]
    assert rt["out"] == "RT-on-My-Deb"


def test_named_key_display_name_passthrough_when_no_name():
    # A nested dict without a `name` leaves {{ this.x.display_name }} intact.
    doc = {"os_builders": [{"name": "d", "meta": {"k": "v"},
                            "out": "{{ this.meta.display_name }}"}]}
    assert _named(doc)["os_builders"][0]["out"] == "{{ this.meta.display_name }}"
