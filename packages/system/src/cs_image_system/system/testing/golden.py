# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The test kit's golden: what a run emitted, compared byte for byte with a
committed tree, and the deliberate rewrite of that tree.

A golden directory holds exactly what a dry ``run --all`` over a fixture
generates plus the meta-state files it writes. A comparison fails on any
difference; a golden is rewritten only on purpose, by a recipe a person
runs, and the rewritten tree is read file by file.
"""
from __future__ import annotations

import difflib
import shutil
from collections.abc import Mapping
from pathlib import Path

from .run import tree

#: files a run writes that carry run-local detail, or that are the test's
#: INPUT (written into the copy before the load; a dry run never rewrites
#: it), and so are in no golden
IGNORED_FILES = frozenset({"run-summary.json", "runs.yaml", "runtime-facts.yaml"})


def emitted(generated: Path, meta_state: Path) -> dict[str, str]:
    """``{relative path: text}`` of what a run has emitted so far: its
    ``generated`` tree and its ``meta_state`` tree (a run's attributes of
    those names), without :data:`IGNORED_FILES`. Nothing in an emission may
    name the (temporary, per-run) root -- the run scripts reach it through
    ``$CSIS_ROOT`` -- so the result is compared verbatim and a stray
    absolute path is a difference."""
    out = {f"generated/{k}": v for k, v in tree(generated).items()}
    out.update({f"meta-state/{k}": v for k, v in tree(meta_state).items()})
    return {k: v for k, v in out.items() if Path(k).name not in IGNORED_FILES}


def differences(golden_dir: Path, output: Mapping[str, str]) -> list[str]:
    """Every way ``output`` differs from the tree at ``golden_dir``: a file
    missing from the output, a file the golden does not hold, and a unified
    diff for each file whose text differs. Empty when they are equal."""
    golden = tree(golden_dir)
    problems: list[str] = []
    for rel in sorted(set(golden) | set(output)):
        if rel not in output:
            problems.append(f"missing from output: {rel}")
        elif rel not in golden:
            problems.append(f"new file not in golden: {rel}")
        elif golden[rel] != output[rel]:
            problems.append("\n".join(difflib.unified_diff(
                golden[rel].splitlines(), output[rel].splitlines(),
                f"golden/{rel}", f"output/{rel}", lineterm="", n=2)))
    return problems


def assert_matches(golden_dir: Path, output: Mapping[str, str], regenerate_with: str = "") -> None:
    """Fail, listing :func:`differences`, unless ``output`` equals the tree
    at ``golden_dir``. ``regenerate_with`` names the recipe that rewrites
    this golden, for the failure's last line."""
    assert golden_dir.is_dir(), f"no golden tree at {golden_dir}" + (
        f"; run `{regenerate_with}`" if regenerate_with else "")
    problems = differences(golden_dir, output)
    hint = f"\n\n(run `{regenerate_with}` if intended)" if regenerate_with else ""
    assert not problems, "\n\n".join(problems) + hint


def write(golden_dir: Path, output: Mapping[str, str]) -> int:
    """Replace the tree at ``golden_dir`` with ``output``; the number of
    files written is returned."""
    if golden_dir.exists():
        shutil.rmtree(golden_dir)
    for rel, content in output.items():
        p = golden_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return len(output)
