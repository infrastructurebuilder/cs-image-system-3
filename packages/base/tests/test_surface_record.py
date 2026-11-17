# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The version rule, as the comparison with a baseline applies it.

Held on records the test writes: an entry added to the surface passes; an
entry removed or changed while the middle number stands still is named,
with both forms of a change; a middle number above the baseline's asks for
the baseline to be re-recorded; and a baseline is not rewritten over a
broken rule.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.base.surface import record

LIB = "cs_image_system.base"
WAS = {"m:Thing": "class ()", "m:Thing.run": "method (self, a: 'int') -> 'str'", "m:Thing#size": "field int required",
       "m:LIMIT": "constant int 3", "m:Thing._hook": "hook method (self) -> 'None'"}


@pytest.fixture
def baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "surface-baseline.txt"
    path.write_text(record.render(LIB, 2, WAS))
    now = {"middle": 2, "entries": dict(WAS)}
    monkeypatch.setattr(record, "middle_of", lambda library: now["middle"])
    monkeypatch.setattr(record, "entries", lambda library: dict(now["entries"]))
    return path, now


def test_an_unchanged_surface_and_an_addition_both_keep_the_rule(baseline):
    path, now = baseline
    assert record.read(path) == (2, WAS)
    assert record.problems(LIB, path) == []
    now["entries"]["m:Thing.more"] = "method (self) -> 'None'"
    assert record.problems(LIB, path) == []


def test_a_removed_entry_is_named(baseline):
    path, now = baseline
    del now["entries"]["m:LIMIT"]
    broken = record.problems(LIB, path)
    assert len(broken) == 1 and "m:LIMIT" in broken[0] and "removed" in broken[0]


@pytest.mark.parametrize("key, new", [
    ("m:Thing.run", "method (self, a: 'int', b: 'int') -> 'str'"),       # a parameter
    ("m:Thing.run", "method (self, a: 'int' = 1) -> 'str'"),             # a default
    ("m:Thing.run", "method (self, a: 'int') -> 'bytes'"),               # an annotation
    ("m:Thing#size", "field int optional"),                              # a model's field
    ("m:LIMIT", "constant int 4"),                                       # a constant's value
    ("m:Thing._hook", "hook method (self, more) -> 'None'"),             # a declared hook
])
def test_a_changed_entry_is_named_with_both_forms(baseline, key: str, new: str):
    path, now = baseline
    now["entries"][key] = new
    broken = record.problems(LIB, path)
    assert len(broken) == 1 and key in broken[0] and WAS[key] in broken[0] and new in broken[0]


def test_a_higher_middle_number_asks_for_the_baseline_to_be_re_recorded(baseline):
    path, now = baseline
    now["middle"] = 3
    del now["entries"]["m:LIMIT"]                    # allowed now: the line is new
    broken = record.problems(LIB, path)
    assert len(broken) == 1 and "surface-record" in broken[0]
    assert record.write(LIB, path) == [] and record.read(path) == (3, now["entries"])
    assert record.problems(LIB, path) == []


def test_a_baseline_is_not_rewritten_over_a_broken_rule(baseline):
    path, now = baseline
    before = path.read_text()
    del now["entries"]["m:LIMIT"]
    assert record.write(LIB, path) != [] and path.read_text() == before


def test_a_missing_baseline_is_a_problem_not_a_pass(tmp_path: Path):
    assert record.problems(LIB, tmp_path / "none.txt") != []
