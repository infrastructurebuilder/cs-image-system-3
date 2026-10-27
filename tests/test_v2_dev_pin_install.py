# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 99: a development pin installs from TestPyPI again.

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
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LINE = ('case "$pin" in *.dev*) indexes="--index-url https://test.pypi.org/simple/ '
        '--extra-index-url https://pypi.org/simple/ --index-strategy unsafe-first-match" ;; esac')
DOCS = [REPO / "DAILY_DRIVER.md", REPO / "docs" / "OPERATIONS.md", *sorted((REPO / "docs" / "examples").glob("*/CI_SETUP.md"))]


def test_every_starter_job_installs_a_dev_pin_with_the_strategy():
    lines = [ln.strip() for wf in sorted((REPO / "docs" / "examples").glob("*/.github/workflows/*.yml"))
             for ln in wf.read_text().splitlines() if 'case "$pin" in' in ln]
    assert len(lines) == 15, "three jobs in each ci.yml and one in each OPA probe workflow"
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


def test_the_live_check_reads_the_line_from_the_starters_and_is_a_full_test_leg():
    loader = importlib.machinery.SourceFileLoader("dev_pin_resolves", str(REPO / "scripts" / "dev-pin-resolves"))
    spec = importlib.util.spec_from_loader("dev_pin_resolves", loader)
    assert spec is not None
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    assert m.install_options(REPO)[-2:] == ["--index-strategy", "unsafe-first-match"]
    legs = (REPO / "Justfile").read_text().split("full-test-legs:", 1)[1].split("\n\n", 1)[0]
    assert "scripts/dev-pin-resolves" in legs and "FAILED dev-pin-resolves" in legs
