# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 124: the run context and the registry are identity objects. A model
copy shares them; it never clones the run.

Found on this stage's first acceptance run (2026-11-05): a builder's
``get_executable_copy`` deep-copies the executable, the executable holds the
registry, the registry holds the builders, and since stage 124 a builder holds
its bound context -- so the copy cloned the whole run, for hours and tens of
gigabytes. The two ``__deepcopy__`` hooks below are what stop that; this test
is their guard."""

import copy
import time

from v2_support import FIXTURE_CONFIG, load_context, stub_environment


def test_a_deep_copy_of_the_context_is_the_context(monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(FIXTURE_CONFIG)
    assert copy.deepcopy(ctx) is ctx
    assert copy.copy(ctx) is ctx
    assert copy.deepcopy(ctx.reg) is ctx.reg
    assert copy.copy(ctx.reg) is ctx.reg


def test_a_builders_executable_copy_shares_the_run(monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(FIXTURE_CONFIG)
    builders = [b for b in ctx.all_sorted_builders if b.model.get_executable() is not None]
    assert builders, "the fixture has builders with an executable"
    for builder in builders:
        started = time.monotonic()
        exe = builder.get_executable_copy()
        assert time.monotonic() - started < 2.0, f"{builder.name}: the copy walked the run"
        assert exe is not ctx.executables[builder.model.get_executable()]
        assert getattr(exe, "_reg") is ctx.reg
