# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Licence headers by REUSE: every source file carries the SPDX
two-liner, the files that must not (hashed modification content, the golden,
prose) are declared in REUSE.toml, `just lint` runs `reuse lint`, and `just
headers` adds the header to a file that lacks one without touching the
fixtures.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from v2_support import FIXTURE_CONFIG, REPO

HEADER = "SPDX-License-" + "Identifier: Apache-2.0"   # concatenated: a literal tag would be parsed by reuse
HOLDER = "Mykel Alvis <mykelalvis@infrastructurebuilder.org>"


def _recipe(name: str) -> str:
    text = (REPO / "Justfile").read_text()
    m = re.search(rf"^{re.escape(name)}(?: [^\n]*)?:.*?\n(.*?)(?=\n\S|\Z)", text, flags=re.M | re.S)
    assert m, f"no recipe {name}"
    return m.group(1)


def test_lint_runs_the_licensing_check_and_the_recipes_exist():
    assert "reuse lint" in _recipe("lint")
    headers = _recipe("headers")
    assert "--skip-existing" in headers and HOLDER in headers and "reuse lint" in headers
    assert "tests/fixtures" not in headers, "the fixtures never receive a header"
    assert re.search(r'reuse"? lint', _recipe("reuse-live")), "the sibling lint runs the venv's reuse"


def test_reuse_toml_declares_what_carries_no_header():
    text = (REPO / "REUSE.toml").read_text()
    for path in ('"tests/fixtures/**"', '"docs/**"', '"**/*.md"', '"uv.lock"'):
        assert path in text, path
    assert "SPDX-File" + f'CopyrightText = "2026 {HOLDER}"' in text
    assert "SPDX-License-" + 'Identifier = "Apache-2.0"' in text
    assert (REPO / "LICENSES" / "Apache-2.0.txt").exists()


def test_every_source_file_carries_the_header_and_no_hashed_file_does():
    sources = [p for p in (REPO / "packages").rglob("*.py") if ".venv" not in p.parts]
    sources += list((REPO / "tests").glob("*.py")) + list((REPO / "tfmodules").rglob("*.tf"))
    sources += list((REPO / "bin").glob("*.sh")) + [REPO / "Justfile", REPO / ".githooks" / "pre-commit"]
    assert len(sources) > 300
    missing = [str(p.relative_to(REPO)) for p in sources if HEADER not in "\n".join(p.read_text().splitlines()[:6])]
    assert not missing, f"sources without the header: {missing[:10]}"
    for name in ("setup_dask.yml", "setup_data_science.yml", "modify_image.yml", "mod_image.sh"):
        assert HEADER not in (FIXTURE_CONFIG / name).read_text(), f"{name} is hashed into lineage: no header"


def test_a_source_without_the_header_fails_reuse_lint(tmp_path: Path):
    (tmp_path / "LICENSES").mkdir()
    shutil.copy(REPO / "LICENSES" / "Apache-2.0.txt", tmp_path / "LICENSES" / "Apache-2.0.txt")
    src = tmp_path / "thing.py"
    src.write_text('"""A module."""\n')
    lint = [sys.executable, "-m", "reuse", "lint", "--quiet"]
    assert subprocess.run(lint, cwd=tmp_path).returncode != 0
    src.write_text("# SPDX-File" + f"CopyrightText: 2026 {HOLDER}\n#\n# {HEADER}\n\n" + src.read_text())
    assert subprocess.run(lint, cwd=tmp_path).returncode == 0
