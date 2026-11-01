# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene bundle XXI (stage 108): the parts that are texts, not behaviour.

Item 1 (the release's probes) is in test_v2_release_probes.py, item 3 (``take`` and
``init-config --changes-since``) in test_v2_take_recipe.py and test_v2_changes_since.py.
Here: item 2, the IDE's workspace file is no longer the repository's; item 3, every
starter carries the same ``take`` recipe; item 4, CI's guard takes a list of runtimes.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "docs" / "examples"
STARTERS = sorted(p.name for p in EXAMPLES.iterdir() if (p / "Justfile").is_file())


def test_the_ide_workspace_file_is_untracked_and_ignored():
    tracked = subprocess.run(["git", "ls-files", "*.code-workspace"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    assert tracked.strip() == ""
    ignore = (REPO / ".gitignore").read_text().splitlines()
    assert "/*.code-workspace" in ignore and "packages/**/*.code-workspace" in ignore


def test_every_starter_carries_the_same_take_recipe():
    assert len(STARTERS) == 5
    texts = {s: (EXAMPLES / s / "Justfile").read_text() for s in STARTERS}
    assert len(set(texts.values())) == 1                                   # the Justfile is the release's, one file five times
    just = next(iter(texts.values()))
    assert "\ntake version patched=\"no\":\n" in just
    recipe = just[just.index("\ntake version"):]
    recipe = recipe[:recipe.index("\n\n", 1)]
    # the catch-up guard is the first act on the repository, before the release is installed or a file written
    assert recipe.index("git fetch -q origin") < recipe.index("git merge --ff-only origin/main") < recipe.index("merge-base --is-ancestor origin/main HEAD")
    assert recipe.index("merge-base --is-ancestor origin/main HEAD") < recipe.index("uv tool install") < recipe.index("--changes-since") < recipe.index("> .csis-version")
    assert recipe.index("> .csis-version") < recipe.index("just init") < recipe.index("just validate") < recipe.index('git commit -q -m "Take $version"')
    assert "git push origin develop" in recipe and "origin develop:main" in recipe      # pushing main stays the operator's own act
    assert "init-config . --force" in recipe                                            # the refresh is by hand, by decision
    assert "--index-strategy unsafe-first-match" in recipe                              # a development release (stage 99)


def test_the_guard_checks_each_runtime_it_is_given():
    for s in STARTERS:
        wf = EXAMPLES / s / ".github" / "workflows" / "ci.yml"
        text = wf.read_text()
        yaml.safe_load(text)                                                 # still a workflow
        assert 'for guarded in $GUARD_RUNTIME; do' in text and 'just runtime-unchanged "$guarded"' in text, s
        assert 'just runtime-unchanged "$GUARD_RUNTIME"' not in text, s
        assert "several separated by spaces" in text, s
        guide = (EXAMPLES / s / "CI_SETUP.md").read_text()
        assert "several separated by spaces (the guard checks each)" in guide, s
