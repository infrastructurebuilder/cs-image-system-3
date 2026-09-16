# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Version-constraint handling for terraform providers and packer plugins.

Constraint strings from configuration (e.g. ">= 4.0.0", "~> 1.2", "= 1.0.0")
are normalized to :class:`packaging.specifiers.SpecifierSet` for conflict
analysis; the ORIGINAL strings are preserved for emission into HCL.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

log = logging.getLogger(__name__)


class HclConfigConflictError(RuntimeError):
    """Raised when collected HCL requirements are contradictory (e.g. two
    workspaces demand irreconcilable versions of the same provider)."""


_BARE_VERSION = re.compile(r"^\d+(\.\d+)*([a-zA-Z0-9.\-+]*)$")


def _pessimistic_upper(version: str) -> str:
    """Upper bound for a terraform '~>' (pessimistic) constraint."""
    parts = version.split(".")
    if len(parts) >= 3:
        # ~> X.Y.Z  =>  < X.(Y+1).0
        return f"{parts[0]}.{int(parts[1]) + 1}.0"
    if len(parts) == 2:
        # ~> X.Y  =>  < (X+1).0
        return f"{int(parts[0]) + 1}.0"
    # ~> X  =>  < (X+1)
    return f"{int(parts[0]) + 1}"


def normalize_constraint(spec: str | None) -> SpecifierSet:
    """Translate a terraform/packer constraint string into a SpecifierSet.

    Handles comma-separated clauses, terraform's '~>' pessimistic operator,
    '=' (as '=='), and bare versions (as '=='). Unparseable clauses raise
    ValueError so config typos surface early.
    """
    if not spec or not spec.strip():
        return SpecifierSet()
    clauses: list[str] = []
    for raw in spec.split(","):
        clause = raw.strip()
        if not clause:
            continue
        if clause.startswith("~>"):
            base = clause[2:].strip()
            clauses.append(f">={base}")
            clauses.append(f"<{_pessimistic_upper(base)}")
        elif clause.startswith("=") and not clause.startswith("=="):
            clauses.append(f"=={clause[1:].strip()}")
        elif _BARE_VERSION.match(clause):
            clauses.append(f"=={clause}")
        else:
            # ">= 1.0", "<2", "!= 1.5", "== 1.0" pass through (whitespace ok)
            clauses.append(clause.replace(" ", ""))
    return SpecifierSet(",".join(clauses))


def merge_constraints(specs: Sequence[str]) -> tuple[str, SpecifierSet]:
    """Merge constraint strings: emission string preserves the originals
    (deduped, comma-joined = logical AND for terraform); the returned
    SpecifierSet is the AND of all normalized clauses for analysis."""
    originals = [s.strip() for s in specs if s and s.strip()]
    emission = ", ".join(dict.fromkeys(originals))
    combined = SpecifierSet()
    for s in originals:
        combined &= normalize_constraint(s)
    return emission, combined


def _candidate_versions(combined: SpecifierSet) -> list[Version]:
    """Witness candidates: every version literal mentioned in any clause,
    plus micro/minor/major bumps of each, plus 0."""
    candidates: list[Version] = [Version("0")]
    for clause in combined:
        try:
            v = Version(clause.version.rstrip(".*"))
        except InvalidVersion:
            continue
        release = list(v.release) + [0, 0]
        major, minor, micro = release[0], release[1], release[2]
        candidates.append(v)
        candidates.append(Version(f"{major}.{minor}.{micro + 1}"))
        candidates.append(Version(f"{major}.{minor + 1}.0"))
        candidates.append(Version(f"{major + 1}.0.0"))
    return candidates


def is_satisfiable(combined: SpecifierSet) -> bool:
    """Whether some version can satisfy the combined constraint.

    Approximation: tests a finite witness set derived from the version
    literals in the clauses (each literal and its micro/minor/major bumps).
    This catches practical conflicts (disjoint pins, non-overlapping ranges);
    exotic gap constructions may pass undetected.
    """
    if not len(combined):
        return True
    return any(
        combined.contains(c, prereleases=True) for c in _candidate_versions(combined)
    )


def assert_satisfiable(
    name: str,
    requirements: Iterable[tuple[str | None, str | None]],
) -> str:
    """Validate requirements for one provider/plugin and return the merged
    emission string.

    ``requirements`` is an iterable of (version_constraint, requested_by).
    Raises HclConfigConflictError when the combined constraints are
    unsatisfiable.
    """
    reqs = list(requirements)
    specs = [v for v, _ in reqs if v]
    emission, combined = merge_constraints(specs)
    if not is_satisfiable(combined):
        detail = "; ".join(
            f"'{v}' requested by {who or 'unknown'}" for v, who in reqs if v
        )
        raise HclConfigConflictError(
            f"Irreconcilable version constraints for '{name}': {detail}"
        )
    return emission
