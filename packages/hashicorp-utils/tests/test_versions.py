# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins constraint normalization, merging, and conflict detection."""
import pytest

from cs_image_system.hashicorp_utils.versions import (
    HclConfigConflictError,
    assert_satisfiable,
    is_satisfiable,
    merge_constraints,
    normalize_constraint,
)


class TestNormalize:
    def test_plain_operators_pass_through(self):
        s = normalize_constraint(">= 4.0.0, < 6.0")
        assert s.contains("5.0.0") and not s.contains("6.1.0") and not s.contains("3.9")

    def test_pessimistic_three_part(self):
        s = normalize_constraint("~> 1.2.3")
        assert s.contains("1.2.9") and not s.contains("1.3.0") and not s.contains("1.2.2")

    def test_pessimistic_two_part(self):
        s = normalize_constraint("~> 1.2")
        assert s.contains("1.9.0") and not s.contains("2.0.0")

    def test_pessimistic_one_part(self):
        s = normalize_constraint("~> 1")
        assert s.contains("1.5") and not s.contains("2.0")

    def test_single_equals(self):
        assert normalize_constraint("= 1.0.0").contains("1.0.0")

    def test_bare_version_is_exact(self):
        s = normalize_constraint("1.0.0")
        assert s.contains("1.0.0") and not s.contains("1.0.1")

    def test_empty_is_unconstrained(self):
        assert len(normalize_constraint(None)) == 0
        assert len(normalize_constraint("  ")) == 0


class TestMergeAndSatisfy:
    def test_emission_string_dedupes_and_preserves_originals(self):
        emission, _ = merge_constraints([">= 4.0.0", "< 6.0.0", ">= 4.0.0"])
        assert emission == ">= 4.0.0, < 6.0.0"

    def test_overlapping_ranges_satisfiable(self):
        _, combined = merge_constraints([">= 1.0, < 2.0", ">= 1.5"])
        assert is_satisfiable(combined)

    def test_disjoint_pins_unsatisfiable(self):
        _, combined = merge_constraints(["== 1.2.0", "== 1.3.0"])
        assert not is_satisfiable(combined)

    def test_disjoint_ranges_unsatisfiable(self):
        _, combined = merge_constraints([">= 4.0.0", "< 3.0"])
        assert not is_satisfiable(combined)

    def test_assert_satisfiable_returns_merged_string(self):
        assert assert_satisfiable("aws", [(">= 4.0.0", "a"), ("< 6.0.0", "b")]) \
            == ">= 4.0.0, < 6.0.0"

    def test_assert_satisfiable_error_names_requesters(self):
        with pytest.raises(HclConfigConflictError) as e:
            assert_satisfiable("aws", [("== 1.0.0", "ws-one"), ("== 2.0.0", "ws-two")])
        msg = str(e.value)
        assert "aws" in msg and "ws-one" in msg and "ws-two" in msg
