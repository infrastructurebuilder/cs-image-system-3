# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A development pin installs from TestPyPI again.

Once 0.1.1 was on PyPI, uv's default index strategy stopped at PyPI for
`cs-image-system` and never looked for a `.dev` version on TestPyPI: every
development pin failed to install. Every install line -- the starters'
workflow jobs and the commands the documents show -- names
`--index-strategy unsafe-first-match`, which keeps PyPI first and falls
through to TestPyPI only for what PyPI cannot satisfy. The live check that
the line resolves (ours from TestPyPI, nothing else from it) is a full-test
leg, scripts/dev-pin-resolves.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LINE = ('case "$pin" in *.dev*) indexes="--index-url https://test.pypi.org/simple/ '
        '--extra-index-url https://pypi.org/simple/ --index-strategy unsafe-first-match" ;; esac')
DOCS = [REPO / "docs" / "DAILY_DRIVER.md", REPO / "docs" / "OPERATIONS.md", *sorted((REPO / "docs" / "examples").glob("*/CI_SETUP.md"))]


def test_every_starter_job_installs_a_dev_pin_with_the_strategy():
    lines = [ln.strip() for wf in sorted((REPO / "docs" / "examples").glob("*/.github/workflows/*.yml"))
             for ln in wf.read_text().splitlines() if 'case "$pin" in' in ln]
    assert len(lines) == 18, "three jobs in each ci.yml and one in each OPA probe workflow"
    assert set(lines) == {LINE}


def test_every_install_command_in_the_documents_names_the_strategy():
    for doc in DOCS:
        # every paragraph or code block that names PyPI as the extra index names the strategy too
        blocks = re.split(r"\n\s*\n", doc.read_text())
        named = [b for b in blocks if "--extra-index-url https://pypi.org/simple/" in b]
        assert named, f"{doc.relative_to(REPO)} shows no TestPyPI install"
        for b in named:
            flat = " ".join(b.split())
            assert "--index-strategy unsafe-first-match" in flat, f"{doc.relative_to(REPO)}: {flat[:120]}"


def _the_check():
    loader = importlib.machinery.SourceFileLoader("dev_pin_resolves", str(REPO / "scripts" / "dev-pin-resolves"))
    spec = importlib.util.spec_from_loader("dev_pin_resolves", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


def test_a_package_with_a_version_of_its_own_resolves_at_it_and_still_from_testpypi():
    """The contract's version is its own (the bump excludes its manifest), so a
    development pin resolves it at that version, never at the release's."""
    m = _the_check()
    own_line = m.own_version_line(REPO)
    assert own_line == {"cs-image-system-contract"}
    test, pypi = "https://test.pypi.org/simple", "https://pypi.org/simple"
    ours = {"cs-image-system": ("0.1.7.dev2", test), "cs-image-system-base": ("0.1.7.dev2", test),
            "cs-image-system-contract": ("0.3.0", test)}
    assert m.misplaced(ours, "0.1.7.dev2", own_line) == []
    assert m.misplaced(ours, "0.1.7.dev2", set()) == ["cs-image-system-contract"]       # without the exclusion it is refused
    assert m.misplaced({**ours, "cs-image-system-contract": ("0.3.0", pypi)}, "0.1.7.dev2", own_line) == ["cs-image-system-contract"]
    assert m.misplaced({**ours, "cs-image-system-base": ("0.1.6", test)}, "0.1.7.dev2", own_line) == ["cs-image-system-base"]
    assert m.misplaced({**ours, "cs-image-system-base": ("0.1.7.dev2", pypi)}, "0.1.7.dev2", own_line) == ["cs-image-system-base"]


def test_the_live_check_reads_the_line_from_the_starters_and_is_a_full_test_leg():
    m = _the_check()
    assert m.install_options(REPO)[-2:] == ["--index-strategy", "unsafe-first-match"]
    if not shutil.which("just"):
        pytest.skip("needs just")
    assert "full-test-legs" in subprocess.run(["just", "--summary"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    legs = subprocess.run(["just", "-n", "full-test-legs"], cwd=REPO, capture_output=True, text=True, check=True).stderr   # the printed plan
    assert "scripts/dev-pin-resolves" in legs and "FAILED dev-pin-resolves" in legs
