# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The sources do not narrate.

A comment or docstring that names a stage number, a hygiene bundle's
numeral, a finding number or a date tells a reader when something was
written and nothing about what it does, and the worksheet it points at
is deleted the day its stage lands. The working memory of a session belongs in the
squash messages, the worksheets and the private notes; what stays in
the code is the behaviour's name, or, where the why matters, a reference
to the entry in ``docs/CHANGES.md`` (``docs/CHANGES.md#s<stage>``, an
anchor that page carries). ``DESIGN §3A`` and ``DESIGN N26`` are references into
a current page and stay.

What is read, and where:

- the Python sources under ``packages/*/src``: comments and docstrings
  (a string the code emits or shows is the emission's and the user's, and
  the golden holds the emission byte for byte);
- every other file under ``packages/*/src`` (the terraform modules) and
  ``tfmodules/``: the ``#`` and ``//`` comments (an IAM policy document's
  ``Version`` literal is a dated value AWS requires);
- the ``Justfile`` and ``pyproject.toml``: whole;
- the frozen fixture ``tests/fixtures/config``: the YAML comments and the
  README (the golden does not read comments), except the modification
  content the emission copies verbatim and hashes (``HASHED_CONTENT``):
  its comments are the emission's, held byte for byte by the golden;
- the tests, ``tests/`` and ``packages/*/tests``: comments and
  docstrings, except one closing ``history:`` line per module, which
  names the bundle items a test came from and is how a reader follows a
  frozen ledger entry to the test that holds it today.

Each area holds zero.

Run it by hand to list the offenders: ``uv run python
tests/test_sources_do_not_narrate.py [area ...]``.
"""
from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

NARRATION = re.compile(
    r"[Ss]tage\s*\d+"                               # the word, then a number (a space or none between)
    r"|[Hh]ygiene\s+(?:[IVXL]+|\d+)\b"              # a bundle by roman numeral or number
    r"|\b[Bb]undle\s+[IVXL]+\b"                     # a bundle by roman numeral
    r"|\bF\d{1,2}\b"                                # a finding number (ruff's codes have three digits)
    r"|\b20\d\d-\d\d-\d\d\b"                        # a date
    r"|(?<!DESIGN )§\d+"                            # a section sign and a number (DESIGN §3A is a page reference)
)
HISTORY_LINE = re.compile(r"^\s*[Hh]istory:")
COMMENT = re.compile(r"(?:^|\s)(?:#|//)(.*)$")

#: fixture files the emission copies verbatim and hashes: their text is the golden's
HASHED_CONTENT = {f"tests/fixtures/config/{name}" for name in
                  ("mod_image.sh", "modify_image.yml", "setup_dask.yml", "setup_data_science.yml")}

#: area -> what it reads
AREAS: dict[str, str] = {
    "sources": "comments and docstrings of packages/*/src/**/*.py",
    "modules": "the comments of every non-Python file under packages/*/src, and tfmodules/",
    "justfile": "the Justfile, whole",
    "pyproject": "pyproject.toml, whole",
    "fixture": "the YAML comments and the README of tests/fixtures/config, hashed content excepted",
    "tests": "comments and docstrings of tests/ and packages/*/tests, history: lines excepted",
}



def _python_hits(path: Path, *, except_history: bool) -> list[str]:
    """``file:line: text`` for every narration token in a comment or a
    docstring of one Python file."""
    src = path.read_text()
    tree = ast.parse(src, filename=str(path))
    doc_starts: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                doc_starts.add((first.value.lineno, first.value.col_offset))
    out: list[str] = []
    rel = path.relative_to(REPO)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            lines = [(tok.start[0], tok.string)]
        elif tok.type == tokenize.STRING and tok.start in doc_starts:
            lines = [(tok.start[0] + i, line) for i, line in enumerate(tok.string.splitlines())]
        else:
            continue
        for lineno, text in lines:
            if except_history and HISTORY_LINE.match(text):
                continue
            for m in NARRATION.finditer(text):
                out.append(f"{rel}:{lineno}: {m.group(0)!r} in {text.strip()[:90]}")
    return out


def _whole_file_hits(path: Path) -> list[str]:
    rel = path.relative_to(REPO)
    return [f"{rel}:{i}: {m.group(0)!r} in {line.strip()[:90]}"
            for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1)
            for m in NARRATION.finditer(line)]


def _comment_hits(path: Path) -> list[str]:
    """``#`` and ``//`` comments of a YAML, HCL or terraform file."""
    rel = path.relative_to(REPO)
    out: list[str] = []
    for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        m = COMMENT.search(line)
        if m:
            out.extend(f"{rel}:{i}: {h.group(0)!r} in {line.strip()[:90]}" for h in NARRATION.finditer(m.group(1)))
    return out


def _src_files() -> list[Path]:
    return sorted(p for p in REPO.glob("packages/*/src/**/*") if p.is_file() and "__pycache__" not in p.parts)


def hits(area: str) -> list[str]:
    if area == "sources":
        return [h for p in _src_files() if p.suffix == ".py" for h in _python_hits(p, except_history=False)]
    if area == "modules":
        files = [p for p in _src_files() if p.suffix != ".py"]
        files += sorted(p for p in (REPO / "tfmodules").rglob("*") if p.is_file())
        return [h for p in files for h in _comment_hits(p)]
    if area == "justfile":
        return _whole_file_hits(REPO / "Justfile")
    if area == "pyproject":
        return _whole_file_hits(REPO / "pyproject.toml")
    if area == "fixture":
        root = REPO / "tests/fixtures/config"
        out = [h for p in sorted(root.rglob("*.y*ml")) if str(p.relative_to(REPO)) not in HASHED_CONTENT
               for h in _comment_hits(p)]
        return out + [h for p in sorted(root.rglob("*.md")) for h in _whole_file_hits(p)]
    if area == "tests":
        files = sorted((REPO / "tests").glob("*.py")) + sorted(REPO.glob("packages/*/tests/*.py"))
        return [h for p in files for h in _python_hits(p, except_history=True)]
    raise KeyError(area)


@pytest.mark.parametrize("area", sorted(AREAS))
def test_the_area_holds_no_narration(area: str):
    found = hits(area)
    assert not found, (
        f"{area} ({AREAS[area]}): {len(found)} narration tokens; "
        "name the behaviour or point at docs/CHANGES.md:\n  " + "\n  ".join(found[:40]))


def test_the_pattern_reads_what_it_claims():
    bad = ["stage 75 step 2", "Stage 103 branch 2", "(stage1)", "hygiene XIV item 1", "hygiene 5", "bundle VIII item 5",
           "the walk's F31", "found live 2026-09-22", "§127", "TODO §40.4"]
    good = ["DESIGN §3A", "DESIGN N26", "noqa: F401", "F841", "the string stage", "docs/CHANGES.md#s75", "20261016.4",
            "2026-11", "staged", "stages"]
    assert all(NARRATION.search(s) for s in bad), [s for s in bad if not NARRATION.search(s)]
    assert not any(NARRATION.search(s) for s in good), [s for s in good if NARRATION.search(s)]
    assert HISTORY_LINE.match("  history: bundle VIII item 5.") and not HISTORY_LINE.match("the history: of it")


if __name__ == "__main__":
    for area in (sys.argv[1:] or sorted(AREAS)):
        found = hits(area)
        print(f"== {area}: {len(found)}")
        print("\n".join(found))
