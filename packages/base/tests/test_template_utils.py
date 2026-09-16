# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Characterization tests for the string-stage value-based renderer.

These lock in the behavior of ``template_utils.cycle_yaml`` / ``cycle_named_key``
(scope-aware ``this`` / ``this.parent`` + path-preserving passthrough) so later
refactors that de-duplicate the rendering primitives cannot silently change it.
"""
import yaml

from cs_image_system.base import template_utils as tu


# --------------------------------------------------------------------------
# cycle_yaml: value-based rendering must survive YAML quote/backslash escaping
# --------------------------------------------------------------------------

def test_cycle_yaml_resolves_env_bracket_subscript(monkeypatch):
    monkeypatch.setenv("USER", "testuser")
    # A single-quoted YAML scalar with a bracket+quote subscript -- this used to
    # raise Jinja TemplateSyntaxError when the *serialized text* was templated.
    src = yaml.dump({"config": {"x": "{{ ENV['USER'] }} and more"}})
    out = yaml.safe_load(tu.cycle_yaml(src, include_ENV=True))
    assert out["config"]["x"] == "testuser and more"


def test_cycle_yaml_resolves_env_dot_access(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    src = yaml.dump({"systemuser": "{{ ENV.USER }}"})
    out = yaml.safe_load(tu.cycle_yaml(src, include_ENV=True))
    assert out["systemuser"] == "alice"


def test_cycle_yaml_backslash_wrapped_script_does_not_raise():
    # A long double-quoted scalar PyYAML wraps with line-continuation backslashes
    # inside a {{ }} -- previously "unexpected char '\\'".
    long = "echo \"" + ("x" * 120) + " {{ config.setting }}\"\n./run.sh\n"
    src = yaml.dump({"config": {"setting": "VAL"}, "script": long})
    # Must not raise TemplateSyntaxError, and the tag resolves against top-level config.
    out = yaml.safe_load(tu.cycle_yaml(src, include_ENV=True))
    assert "VAL" in out["script"] and "{{" not in out["script"]


def test_cycle_yaml_no_tags_returned_verbatim():
    src = "a: 1\nb: two\n"
    assert tu.cycle_yaml(src) == src


# --------------------------------------------------------------------------
# cycle_named_key: `this` = nearest dict, `this.parent` = owner, passthrough
# --------------------------------------------------------------------------

def _named(doc, key="os_builders"):
    return yaml.safe_load(tu.cycle_named_key(yaml.dump(doc), plugin_key=key, include_ENV=True))


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
