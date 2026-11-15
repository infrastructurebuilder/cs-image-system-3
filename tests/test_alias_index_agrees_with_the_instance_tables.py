# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The registry's builder alias index (``aliases``, keyed by the bare
word) and its instance tables (keyed by ``InstanceKey``) cannot disagree:

* after a load of the fixture (whose builders come from several plugins,
  and whose runtimes carry aliases), every word in the alias index names
  its builder there (``get_registered_name_by_name_or_alias``, an alias as
  well as a name) and finds exactly one instance in the same
  classification's instance table: one top-level key holds the word, and
  the instance under it is the builder of that name, whose own name or
  aliases hold the word;
* every builder in an instance table is in the alias index under its own
  name with exactly its name and aliases;
* a word the alias index holds is refused for another builder, and a
  builder of another namespace that takes a loaded builder's alias is
  refused by the instance tables, so neither index can take a word the
  other gives to someone else.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness import copy_config, load_context, stub_environment
from pydantic.dataclasses import dataclass

from cs_image_system.base.models.builder_model import NameTyped
from cs_image_system.base.registry import InstanceCollisionError
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class _Runtime(NameTyped):
    """A runtime builder model of a class no loaded plugin registers."""

    def get_classification(self) -> VCT:
        return VCT.RUNTIME_BUILDER


@pytest.fixture
def reg(tmp_path: Path, monkeypatch) -> Any:
    stub_environment(monkeypatch)
    return load_context(copy_config(tmp_path)).reg


def _words(builder: Any) -> set[str]:
    model = builder.model
    return {model.get_name(), *model.get_aliases()}


def test_every_word_in_the_alias_index_finds_its_one_builder(reg):
    assert {n for words in reg.aliases[VCT.RUNTIME_BUILDER].values() for n in words} - set(
        reg.aliases[VCT.RUNTIME_BUILDER]), "the fixture's runtimes carry aliases"
    assert len({reg.namespace_of_class(type(b)) for b in reg.instances[VCT.RUNTIME_BUILDER].values()}) > 1

    for classification, by_name in reg.aliases.items():
        table = reg.instances[classification]
        for name, words in by_name.items():
            for word in words:
                holders = [key for key in table if key.name == word and not key.ancestry]
                assert len(holders) == 1, (classification, word, holders)
                builder = table[holders[0]]
                assert reg.get_registered_name_by_name_or_alias(classification, word) == name
                assert reg.get_instance(classification, word) is builder
                assert builder.model.get_name() == name and word in _words(builder)


def test_every_builder_in_an_instance_table_is_in_the_alias_index(reg):
    for classification, by_name in reg.aliases.items():
        builders = {id(b): b for b in reg.instances[classification].values()}.values()
        assert {b.model.get_name() for b in builders} == set(by_name), classification
        for builder in builders:
            assert set(by_name[builder.model.get_name()]) == _words(builder)


def test_a_word_the_alias_index_holds_is_refused_for_another_builder(reg):
    held = reg.aliases[VCT.RUNTIME_BUILDER]["aws-east2-runtime"]
    before = {k: list(v) for k, v in reg.aliases[VCT.RUNTIME_BUILDER].items()}
    taken = list(reg.classified_aliases[VCT.RUNTIME_BUILDER])

    with pytest.raises(ValueError, match="already registered"):
        reg.register_aliases(VCT.RUNTIME_BUILDER, "another-runtime", [held[-1]])

    assert reg.aliases[VCT.RUNTIME_BUILDER] == before
    assert reg.classified_aliases[VCT.RUNTIME_BUILDER] == taken
    assert reg.get_registered_name_by_name_or_alias(VCT.RUNTIME_BUILDER, held[-1]) == "aws-east2-runtime"


def test_another_namespaces_builder_under_a_held_alias_is_refused(reg):
    owner = reg.get_instance(VCT.RUNTIME_BUILDER, "amazon")
    other = _Runtime(name="another-runtime", type_="x", aliases={"amazon"})
    assert reg.namespace_of_class(type(other)) != reg.namespace_of_class(type(owner))

    with pytest.raises(InstanceCollisionError, match="alias collision"):
        reg.register_built_instance(other)

    assert reg.get_instance(VCT.RUNTIME_BUILDER, "amazon") is owner
    assert reg.get_instance(VCT.RUNTIME_BUILDER, "another-runtime") is None
