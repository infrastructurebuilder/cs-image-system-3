# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Which installed runtime is the local stand-in is declared and, when
there is a choice, named: never settled by a type's name or by order.

A runtime declares itself a stand-in by returning a target factory from
``local_test_target()``. One such runtime installed is the stand-in. Two or
more need one named. None means there is none.
"""
from __future__ import annotations

import pytest

from cs_image_system.base.image_sources import StandInChoiceError, stand_in_runtime_type, stand_in_types


def _runtime(name: str, offers: bool) -> type:
    return type(f"Runtime_{name}", (), {
        "csis_name": classmethod(lambda cls: name),
        "local_test_target": classmethod(lambda cls: (lambda image, executables=None: None) if offers else None),
    })


ALPHA, BETA, PLAIN = _runtime("alpha", True), _runtime("beta", True), _runtime("plain", False)


def test_a_runtime_is_a_stand_in_only_when_it_returns_a_target_factory():
    assert stand_in_types({"alpha": ALPHA, "plain": PLAIN}) == ["alpha"]
    assert stand_in_types({"plain": PLAIN}) == []


def test_with_no_stand_in_installed_there_is_none():
    assert stand_in_runtime_type({"plain": PLAIN}) is None
    assert stand_in_runtime_type({}) is None


def test_the_only_stand_in_installed_is_the_one_used():
    assert stand_in_runtime_type({"beta": BETA, "plain": PLAIN}) == "beta"


def test_two_stand_ins_and_none_named_is_refused_naming_both():
    with pytest.raises(StandInChoiceError) as e:
        stand_in_runtime_type({"beta": BETA, "alpha": ALPHA})
    assert "alpha" in str(e.value) and "beta" in str(e.value) and "--stand-in" in str(e.value)


@pytest.mark.parametrize("named", ["alpha", "beta"])
def test_two_stand_ins_and_one_named_is_the_one_named_whatever_the_order(named: str):
    assert stand_in_runtime_type({"alpha": ALPHA, "beta": BETA}, named) == named
    assert stand_in_runtime_type({"beta": BETA, "alpha": ALPHA}, named) == named


@pytest.mark.parametrize("classes", [{"alpha": ALPHA}, {"alpha": ALPHA, "beta": BETA}, {}])
def test_a_name_that_cannot_serve_is_refused(classes):
    with pytest.raises(StandInChoiceError):
        stand_in_runtime_type({**classes, "plain": PLAIN}, "plain")
