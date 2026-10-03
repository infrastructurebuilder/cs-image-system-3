# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 76: the words of OOPS_DEFAULTS -- ``default``, ``self``, ``none``, the
empty string and null -- mean "not set" wherever a value is read, so nothing
may be NAMED after one. Held three ways: where each configuration file is
read (the file, the entry and the word named), by every model class when it
is built (the backstop for objects made in code), and at the two kinds of
reference that would otherwise have read a written ``none`` as "use the
default" (a foreign key, a state backend). The fields that give ``none`` a
meaning of their own test for it by name and are held here too.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.v2_support import FIXTURE_CONFIG, copy_config, load_context, reset_singletons, stub_environment

from cs_image_system.base.constants import NONE, OOPS_DEFAULTS
from cs_image_system.base.reserved_names import (
    ReservedNameError,
    is_reserved,
    refuse_reserved_names,
    reserved_name_problems,
)


def _variants(word: str | None) -> list[str | None]:
    if word is None:
        return [None]
    if word == "":
        return ["", "   "]
    return [word, word.upper(), word.capitalize(), f"  {word} "]


VARIANTS = [v for w in OOPS_DEFAULTS for v in _variants(w)]
WORDS = [w for w in OOPS_DEFAULTS if w]          # the non-empty words, for the slow tests


def _edit_yaml(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


# ------------------------------------------------------------- (e) the list itself

def test_the_reserved_words_are_all_still_there():
    """Losing a word would make it nameable again, silently."""
    assert {"default", "self", "none", "", None} <= set(OOPS_DEFAULTS)
    assert NONE == "none"


# ------------------------------------------------------- the read-time refusal, unit

@pytest.mark.parametrize("value", VARIANTS, ids=repr)
def test_a_reserved_name_is_found_at_any_depth_and_named_with_its_place(value):
    doc = {"images": [{"name": "fine", "runtimes": [{"name": value}]}]}
    assert is_reserved(value)
    problems = reserved_name_problems(doc, "images/x.yaml")
    assert problems == [f"images/x.yaml: images[0].runtimes[0].name: a name may not be "
                        f"{'empty (null)' if value is None else 'empty' if not value.strip() else repr(value)}"]


@pytest.mark.parametrize("value", VARIANTS, ids=repr)
def test_a_reserved_alias_is_refused_in_a_list_and_alone(value):
    listed = reserved_name_problems({"groups": [{"name": "g", "aliases": ["ok", value]}]}, "f")
    assert len(listed) == 1 and listed[0].startswith("f: groups[0].aliases[1]: an alias may not be")
    if isinstance(value, str):
        alone = reserved_name_problems({"groups": [{"name": "g", "aliases": value}]}, "f")
        assert len(alone) == 1 and "groups[0].aliases[0]" in alone[0]


def test_ordinary_names_numbers_and_words_inside_a_name_pass():
    doc = {"x": [{"name": "nonesuch"}, {"name": "default-vpc"}, {"name": "my-self"}, {"name": 5},
                 {"name": "ok", "aliases": ["none-of-these", "selfish"]}]}
    assert reserved_name_problems(doc, "f") == []
    refuse_reserved_names(doc, "f")                     # raises nothing


def test_every_problem_in_a_file_is_reported_at_once_with_the_reason():
    doc = {"storages": [{"name": "none"}, {"name": "ok", "aliases": ["self"]}, {"name": None}]}
    with pytest.raises(ReservedNameError) as e:
        refuse_reserved_names(doc, "storages/s.yaml")
    text = str(e.value)
    assert "storages[0].name: a name may not be 'none'" in text
    assert "storages[1].aliases[0]: an alias may not be 'self'" in text
    assert "storages[2].name: a name may not be empty (null)" in text
    assert 'mean "not set" wherever a value is read' in text


def test_no_tree_the_system_ships_or_tests_names_anything_after_a_reserved_word():
    """The frozen fixture and the three starters: the rule changes nothing that loads today."""
    roots = [FIXTURE_CONFIG, *sorted((FIXTURE_CONFIG.parents[2] / "docs" / "examples").iterdir())]
    seen = 0
    for root in roots:
        for sub in ("cfg", "groups", "storages", "images", "instances"):
            for f in sorted((root / sub).glob("*.y*ml")) if (root / sub).is_dir() else []:
                assert reserved_name_problems(yaml.safe_load(f.read_text()), str(f)) == []
                seen += 1
    assert seen > 40


# ------------------------------------------- (b) the read-time refusal, through a load

# one declaration of every kind: (file under the tree, its list)
KINDS = [
    ("cfg/executables.yml", "executables"),
    ("cfg/group-builders.yml", "group_builders"),
    ("cfg/group-builders.yml", "user_builders"),
    ("cfg/image-builders.yml", "image_builders"),
    ("cfg/instance-builders.yml", "instance_builders"),
    ("cfg/mod-builders.yml", "mod_builders"),
    ("cfg/os-builders.yml", "os_builders"),
    ("cfg/runtime-builders.yml", "runtime_builders"),
    ("cfg/state-backends.yml", "state_backends"),
    ("cfg/storage-builders.yml", "storage_builders"),
    ("groups/group-tcmet.yaml", "groups"),
    ("groups/users.yaml", "users"),
    ("storages/storage0.yaml", "storages"),
    ("images/image1.yaml", "images"),
    ("instances/instances.yaml", "instances"),
]


def _load_refused(root: Path, monkeypatch) -> str:
    stub_environment(monkeypatch)
    try:
        with pytest.raises(ReservedNameError) as e:
            load_context(root)
        return str(e.value)
    finally:
        reset_singletons()


@pytest.mark.parametrize("rel,key", KINDS, ids=[k for _, k in KINDS])
def test_an_item_of_any_kind_named_none_is_refused_where_its_file_is_read(rel, key, tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    _edit_yaml(root / rel, lambda d: d[key][0].__setitem__("name", "none"))
    text = _load_refused(root, monkeypatch)
    assert rel.split("/")[-1] in text and f"{key}[0].name: a name may not be 'none'" in text, text


@pytest.mark.parametrize("word", WORDS)
def test_every_word_is_refused_as_a_name_and_as_an_alias_through_a_load(word, tmp_path, monkeypatch):
    root = copy_config(tmp_path / "name")
    _edit_yaml(root / "storages" / "storage0.yaml", lambda d: d["storages"][0].__setitem__("name", word.upper()))
    assert f"storages[0].name: a name may not be '{word.upper()}'" in _load_refused(root, monkeypatch)
    root = copy_config(tmp_path / "alias")
    _edit_yaml(root / "groups" / "group-tcmet.yaml", lambda d: d["groups"][0].__setitem__("aliases", [word]))
    assert f"groups[0].aliases[0]: an alias may not be '{word}'" in _load_refused(root, monkeypatch)


def test_an_overlay_naming_an_item_none_is_refused(tmp_path, monkeypatch):
    from cs_image_system.base.global_context import load_overlay
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(yaml.safe_dump({"instances": [{"name": "none", "image": "x"}]}))
    with pytest.raises(ReservedNameError, match=r"instances\[0\]\.name: a name may not be 'none'"):
        load_overlay(overlay)


# ---------------------------------------- (a) every model class, the backstop in code

def _loaded_models() -> dict[type, Any]:
    from cs_image_system.base.registry import Registry
    seen: dict[type, Any] = {}
    for instances in Registry().instances.values():
        for inst in instances.values():
            model = getattr(inst, "model", inst)
            if dataclasses.is_dataclass(model) and hasattr(model, "name"):
                seen.setdefault(type(model), model)
    return seen


def test_every_named_model_class_refuses_every_word_as_a_name_and_an_alias(monkeypatch):
    """The classes are the ones the frozen fixture loads, taken from the
    registry, so a new model the fixture declares is covered without editing
    this test. A class whose name is DERIVED when left at its default (an
    image's per-runtime subconfig takes its image builder's name) passes if
    the name it ends with is not reserved."""
    stub_environment(monkeypatch)
    try:
        load_context(FIXTURE_CONFIG)
        models = _loaded_models()
        names = {cls.__name__ for cls in models}
        assert {"Group", "User", "Storage", "Image", "Instance"} <= names, names
        assert len(models) >= 30, names                     # 31 on 2026-10-03
        accepted: list[str] = []
        for cls, model in models.items():
            for value in VARIANTS:
                try:
                    built = dataclasses.replace(model, name=value)
                except Exception:
                    pass                                     # refused
                else:
                    if is_reserved(built.name):
                        accepted.append(f"{cls.__name__} name={value!r} -> {built.name!r}")
                if not isinstance(value, str):
                    continue
                try:
                    built = dataclasses.replace(model, aliases={value})
                except Exception:
                    pass
                else:
                    accepted.append(f"{cls.__name__} alias={value!r}")
        assert accepted == []
    finally:
        reset_singletons()


# --------------------- (c) a reference written `none` names nothing, and is refused

def _validation_errors(root: Path, monkeypatch) -> list[str]:
    from cs_image_system.base.commands.validate import collect_validation_errors
    stub_environment(monkeypatch)
    try:
        return [str(e) for e in collect_validation_errors(load_context(root))]
    finally:
        reset_singletons()


def test_a_foreign_key_written_none_is_refused_and_default_still_resolves(tmp_path, monkeypatch):
    """A foreign key resolves its default by equality with the field's own, so
    `none` was never the default; with the word in OOPS_DEFAULTS it must still
    be recorded as naming nothing rather than slip through as unset."""
    for word in ("none", "default"):
        root = copy_config(tmp_path / word)
        _edit_yaml(root / "instances" / "instances.yaml", lambda d: d["instances"][0].__setitem__("image", word))
        errors = [e for e in _validation_errors(root, monkeypatch) if "field 'image'" in e]
        if word == "none":
            assert len(errors) == 1 and "names 'none'" in errors[0], errors
            assert "leave the field out (or write `default`) for the default" in errors[0]
        else:
            assert errors == []


def test_a_state_backend_written_none_is_refused_not_put_on_the_default(tmp_path, monkeypatch):
    """`none` would read as unset in the backend chain, which would put the
    root's state on the DEFAULT backend -- the opposite of what it says."""
    root = copy_config(tmp_path)
    _edit_yaml(root / "cfg" / "group-builders.yml",
               lambda d: d["group_builders"][0].__setitem__("state_configuration", "none"))
    errors = [e for e in _validation_errors(root, monkeypatch) if "state backend 'none'" in e]
    assert len(errors) == 1 and "there is no 'no state backend'" in errors[0] and "`local`" in errors[0], errors


# ------------------------- (d) the fields that give `none` a meaning keep it, by name

@pytest.mark.parametrize("family", ["dnf", "apt"])
def test_the_update_policy_none_means_no_updates_by_name(family):
    """`update: {policy: none}` is a policy, read by name -- not "unset",
    which would be a different policy (`full` under `auto_update`)."""
    import types
    from cs_image_system.base.models.update_policy import POLICY_NONE, UpdatePolicy
    from cs_image_system.default_os_plugin.apt_type import AptOsBuilderModel
    from cs_image_system.default_os_plugin.dnf_type import DnfOsBuilderModel
    none = UpdatePolicy.from_config({"policy": "none"}, auto_update=True)
    assert none.policy == POLICY_NONE == NONE and none.validate("x") == []
    model = {"dnf": DnfOsBuilderModel, "apt": AptOsBuilderModel}[family]
    stub = types.SimpleNamespace(repo_setup_commands=lambda: [])
    assert model.commands_for_policy(stub, none) == []                                  # type: ignore[arg-type]
    assert model.commands_for_policy(stub, UpdatePolicy.from_config({"policy": "full"})) != []  # type: ignore[arg-type]


def test_only_none_is_an_explicitly_empty_bake_surface(tmp_path, monkeypatch):
    """`--only none` means "bake nothing", read by name -- not "no filter",
    which would bake everything that is due."""
    from tests.v2_support import V2Run
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["instance-image"], apply=False, only=["none"]).ok
        assert run.ctx.only_images == set()
    finally:
        run.restore_cwd()
        reset_singletons()

# ------------------- step 6: the `config:` key guard, switched on as written

def test_every_word_of_the_guard_is_refused_as_a_document_config_key():
    from cs_image_system.base.constants import INVALID_CONFIG_KEYS
    from cs_image_system.base.reserved_names import invalid_config_key_problems
    for word in INVALID_CONFIG_KEYS:
        for key in {word, word.upper(), f" {word} "}:
            problems = invalid_config_key_problems({"config": {key: 1, "ordinary": 2}}, "cfg/_config.yml")
            assert problems == [f"cfg/_config.yml: config.{key}: '{key}' may not be a `config:` key"], (key, problems)
    assert invalid_config_key_problems({"config": {"module_source_base": "x", "selfish": 1}}, "f") == []
    assert invalid_config_key_problems({"runtime_builders": []}, "f") == []           # no config: nothing to check
    assert invalid_config_key_problems({"config": ["a"]}, "f") == ["f: config: must be a mapping, got list"]


def test_a_config_key_from_the_guard_is_refused_where_its_file_is_read(tmp_path, monkeypatch):
    from cs_image_system.base.reserved_names import InvalidConfigKeyError
    root = copy_config(tmp_path)
    _edit_yaml(root / "cfg" / "_config.yml", lambda d: d["config"].__setitem__("runtime", "x"))
    stub_environment(monkeypatch)
    try:
        with pytest.raises(InvalidConfigKeyError, match=r"_config\.yml: config\.runtime: 'runtime' may not be"):
            load_context(root)
    finally:
        reset_singletons()


def test_an_overlay_config_key_from_the_guard_is_refused(tmp_path):
    from cs_image_system.base.global_context import load_overlay
    from cs_image_system.base.reserved_names import InvalidConfigKeyError
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(yaml.safe_dump({"config": {"self": 1}}))
    with pytest.raises(InvalidConfigKeyError, match=r"config\.self"):
        load_overlay(overlay)


def test_no_tree_the_system_ships_or_tests_uses_a_guarded_config_key():
    from cs_image_system.base.reserved_names import invalid_config_key_problems
    roots = [FIXTURE_CONFIG, *sorted((FIXTURE_CONFIG.parents[2] / "docs" / "examples").iterdir())]
    for root in roots:
        for f in sorted((root / "cfg").glob("*.y*ml")):
            assert invalid_config_key_problems(yaml.safe_load(f.read_text()), str(f)) == []
