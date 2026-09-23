# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 62: the documentation contract.

Every package README ends with the same four sections in the same order,
so a reader finds prerequisites, configuration, tests and failures in the
same place in every package (only a Related section may follow them);
every relative link in DAILY_DRIVER.md, the root README, PLUGINS.md,
WORKLOAD_CONNECTION.md and the READMEs resolves, so a reader is never sent
to a file that is not there; the daily driver has its chapters and names
every package; PLUGINS.md names the contract. Documentation only: nothing
here reads the code, only the words about it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGES = sorted(p for p in (REPO / "packages").iterdir() if p.is_dir() and (p / "pyproject.toml").exists())
CONTRACT = ["## Prerequisites and integration", "## Configuration reference",
            "## What it tests and verifies", "## When it fails"]
CHAPTERS = ["## 1. Before the first command", "## 2. The first run", "## 3. Making things",
            "## 4. Changing things", "## 5. What specifies, and what tests it", "## 6. When it fails",
            "## 7. Every plugin, in one paragraph each", "## 8. The daily habits"]
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
DRIVER = REPO / "DAILY_DRIVER.md"
DOCS = [DRIVER, REPO / "README.md", REPO / "docs" / "PLUGINS.md", REPO / "WORKLOAD_CONNECTION.md",
        *(p / "README.md" for p in PACKAGES)]


def _headings(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.splitlines() if ln.startswith("## ")]


@pytest.mark.parametrize("package", PACKAGES, ids=[p.name for p in PACKAGES])
def test_every_package_readme_ends_with_the_contract_sections_in_order(package: Path):
    readme = package / "README.md"
    assert readme.exists(), f"{package.name} has no README.md"
    headings = _headings(readme.read_text())
    missing = [h for h in CONTRACT if h not in headings]
    assert not missing, f"{package.name}/README.md lacks {missing}"
    positions = [headings.index(h) for h in CONTRACT]
    assert positions == sorted(positions), f"{package.name}/README.md: the contract sections are out of order"
    after = headings[positions[-1] + 1:]
    assert all(h.startswith("## Related") for h in after), \
        f"{package.name}/README.md: {after} follow the contract; only a Related section may"


def _relative_links(md: Path) -> list[tuple[str, Path]]:
    out = []
    for m in LINK.finditer(md.read_text()):
        target = m.group(1)
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = target.split("#", 1)[0]
        if path:
            out.append((target, (md.parent / path).resolve()))
    return out


@pytest.mark.parametrize("doc", DOCS, ids=[str(d.relative_to(REPO)) for d in DOCS])
def test_every_relative_link_resolves(doc: Path):
    assert doc.exists(), f"{doc.relative_to(REPO)} is missing"
    broken = [target for target, path in _relative_links(doc) if not path.exists()]
    assert not broken, f"{doc.relative_to(REPO)}: broken links {broken}"


def test_the_daily_driver_has_its_chapters_and_names_every_package():
    driver = DRIVER.read_text()
    assert driver.strip(), "DAILY_DRIVER.md is empty"
    positions = [driver.find(h) for h in CHAPTERS]
    missing = [h for h, i in zip(CHAPTERS, positions) if i < 0]
    assert not missing, f"DAILY_DRIVER.md lacks {missing}"
    assert positions == sorted(positions), "the chapters are out of order"
    for package in PACKAGES:
        assert f"packages/{package.name}/README.md" in driver, f"the daily driver names no README for {package.name}"


def test_the_daily_driver_is_the_first_place_to_start():
    readme = (REPO / "README.md").read_text()
    start = readme.index("## Where to start")
    first = next(ln for ln in readme[start:].splitlines()[1:] if ln.startswith("- "))
    assert "DAILY_DRIVER.md" in first, first


def test_plugins_md_names_the_contract():
    text = (REPO / "docs" / "PLUGINS.md").read_text()
    assert "## The README contract" in text
    for heading in CONTRACT:
        assert f"`{heading}`" in text, heading
