# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The recipes every starter carries, run in their dry form, and the workflow that calls them.

Every starter's Justfile is the release's, one file in every tree. `take`
guards the repository (fetch, fast-forward, ancestor) before installing the
release, lists what the release changed, writes the pin, then runs init and
validate as one loop that puts the pin back when either fails, commits and
pushes develop; pushing main stays the operator's own act. `cloud-upgrade`
is the second release procedure in order (pin, replace, proof, release, one
more launch, a full record) with `require_released_builds` left on. CI's
guard checks each runtime it is given.

The helpers here (`recipe_names`, `dry_run`) are what other test modules use
to read a starter's Justfile through `just` instead of as text.

history: bundle V item 4, XXI items 3 and 4.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from cs_image_system.system.starters import STARTERS

JUST = shutil.which("just")
needs_just = pytest.mark.skipif(JUST is None, reason="`just` is not on PATH")


def recipe_names(starter: Path) -> set[str]:
    """The recipes `just --summary` names in the starter."""
    assert JUST, "`just` is not on PATH"
    out = subprocess.run([JUST, "--summary"], cwd=starter, capture_output=True, text=True, check=True).stdout
    return set(out.split())


def dry_run(starter: Path, *args: str) -> str:
    """The recipe's lines as `just -n` prints them: evaluated, nothing run."""
    assert JUST, "`just` is not on PATH"
    env = {**os.environ, "CSIS": "cs-image-system"}
    res = subprocess.run([JUST, "-n", *args], cwd=starter, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return res.stdout + res.stderr


def _order(text: str, *needles: str) -> None:
    positions = [text.index(n) for n in needles]
    assert positions == sorted(positions), needles


@needs_just
def test_every_starter_carries_the_same_take_recipe(rendered_starters: Path):
    assert STARTERS, "the release carries starters"
    texts = {s: (rendered_starters / s / "Justfile").read_text() for s in STARTERS}
    assert len(set(texts.values())) == 1                                   # the Justfile is the release's (the skeleton's), one file in every tree
    starter = rendered_starters / sorted(STARTERS)[0]
    assert "take" in recipe_names(starter)
    recipe = dry_run(starter, "take", "0.1.0")
    # the catch-up guard is the first act on the repository, before the release is installed or a file written
    _order(recipe, "git fetch -q origin", "git merge --ff-only origin/main", "merge-base --is-ancestor origin/main HEAD",
           "uv tool install", "--changes-since", "> .csis-version")
    # init, then validate, as one loop that puts the pin back when either fails
    _order(recipe, "> .csis-version", "for step in init validate", 'git commit -q -m "Take $version"')
    assert "git push origin develop" in recipe and "origin develop:main" in recipe      # pushing main stays the operator's own act
    assert "init-config . --force" in recipe                                            # the refresh is by hand, by decision
    assert "--index-strategy unsafe-first-match" in recipe                              # a development release comes from TestPyPI


@needs_just
def test_the_upgrade_recipe_is_the_second_release_procedure_with_the_rule_left_on(rendered_starters: Path):
    from harness import REPO
    assert "cloud-upgrade" not in (REPO / "Justfile").read_text(), "the cycle recipes live in a configuration repository's Justfile"
    starter = rendered_starters / sorted(STARTERS)[0]
    assert "cloud-upgrade" in recipe_names(starter)
    lines = [ln.strip() for ln in dry_run(starter, "cloud-upgrade", "rt", "inst").splitlines() if ln.strip()]
    assert "state query --strict" in lines[0], "never starts on a false belief or a lapsing session (cloud-preflight first)"
    assert any("upgrade instance inst" in ln for ln in lines)
    order = [next(i for i, ln in enumerate(lines) if key in ln) for key in
             ("upgrade instance", "just cloud-launch rt", "just cloud-verify rt inst", "run release --only-runtime rt")]
    assert order == sorted(order), "pin, replace, proof, release -- in that order"
    assert lines.count("just cloud-launch rt") == 2, "one more launch gives the machine its names"
    # a full record last, so the committed emission carries the release read-model
    last_launch = max(i for i, ln in enumerate(lines) if ln == "just cloud-launch rt")
    assert "just record" in lines[last_launch + 1:], "the record follows the last launch"
    assert "require_released_builds" not in "\n".join(ln for ln in lines if not ln.startswith("#")), "the rule is never switched off"


def test_the_guard_checks_each_runtime_it_is_given(rendered_starters: Path):
    for s in STARTERS:
        wf = rendered_starters / s / ".github" / "workflows" / "ci.yml"
        doc = yaml.safe_load(wf.read_text())
        assert doc and doc.get("jobs"), f"{s}: a workflow with jobs"
        steps = "\n".join(str(step.get("run", "")) for job in doc["jobs"].values() for step in job.get("steps", []))
        assert 'for guarded in $GUARD_RUNTIME; do' in steps and 'just runtime-unchanged "$guarded"' in steps, s
        assert 'just runtime-unchanged "$GUARD_RUNTIME"' not in steps, s
        guide = (rendered_starters / s / "CI_SETUP.md").read_text()
        assert "GUARD_RUNTIME" in guide, s
