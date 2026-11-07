# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Test files are named for the behaviour they pin, not for the work that
produced them.

A file named after a stage, a hygiene bundle, a gate, a defect list or an
exploration tells a reader when a test was written and nothing about what
it holds, and the name goes stale the day the ledger it points at is
frozen. The rule, held here over ``tests/`` and every ``packages/*/tests``:

- no file name carries a ledger word (``stage``, ``hygiene``, ``gate``
  followed by a digit, ``defects``, ``explore``, ``ledger``, ``bundle``,
  ``increment``, ``finding``), a bare stage number (``_103``, ``_127``) or
  a roman-numeral bundle suffix (``_xii``, ``_vii``);
- no file name carries the retired ``v2_`` prefix (V1 is gone, so the
  prefix distinguishes nothing) -- except the golden's, ``test_v2_golden.py``,
  whose name and fixture directory ``tests/fixtures/v2_golden`` stay as the
  one fixed point every regeneration is diffed against;
- a test module may still RECORD its history in its docstring (a closing
  ``history:`` line naming the bundle items it came from), which is how a
  reader follows a frozen ledger entry to the test that holds it today.

History: stage 128 renamed every such file (the table is in its squash).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GOLDEN = "test_v2_golden.py"

LEDGER_WORDS = re.compile(
    r"(^|_)(stage|hygiene|defects?|explore|ledger|bundle|increment|findings?)(_|\d|$)"
    r"|(^|_)gate\d"
    r"|_\d{2,3}(_|\.py$)"            # a bare stage number: _103_, _127.py
    r"|_(i{1,3}|iv|vi{0,3}|ix|xi{0,3}|xiv|xv|xvi{1,3}|xix|xx|xxi{1,3})(_|\.py$)"  # a roman bundle suffix
)


def named_test_files() -> list[Path]:
    out = sorted((REPO / "tests").glob("test_*.py"))
    out += sorted(REPO.glob("packages/*/tests/test_*.py"))
    return out


def test_no_test_file_is_named_for_a_stage_bundle_gate_or_defect_list():
    offenders = [str(p.relative_to(REPO)) for p in named_test_files() if LEDGER_WORDS.search(p.stem)]
    assert not offenders, "name these for the behaviour they pin, not the work that produced them:\n  " + \
        "\n  ".join(offenders)


def test_the_v2_prefix_is_gone_from_every_test_file_but_the_golden():
    prefixed = [str(p.relative_to(REPO)) for p in named_test_files() if p.name.startswith("test_v2_") and p.name != GOLDEN]
    assert not prefixed, "V1 is retired; the prefix names nothing:\n  " + "\n  ".join(prefixed)
    assert (REPO / "tests" / GOLDEN).is_file(), "the golden keeps its name"
    assert not list((REPO / "tests").glob("v2_*.py")), "the support module lost its prefix too (tests/harness.py)"


def test_the_rule_reads_the_names_it_claims():
    bad = ["test_v2_stage_103.py", "test_hygiene_xii_records.py", "test_gate4_identity.py", "test_defects_dead.py",
           "test_explore_gcp.py", "test_gcp_increment3.py", "test_stage93_ownership.py", "test_hygiene_vii.py"]
    good = ["test_state_query.py", "test_gates_of_the_runner.py", "test_six_of_them.py", "test_v2_golden.py",
            "test_in_process_steps.py", "test_network_facts.py", "test_container_runtime.py", "test_release_on_main.py"]
    assert all(LEDGER_WORDS.search(Path(n).stem) for n in bad), [n for n in bad if not LEDGER_WORDS.search(Path(n).stem)]
    assert not any(LEDGER_WORDS.search(Path(n).stem) for n in good), [n for n in good if LEDGER_WORDS.search(Path(n).stem)]
