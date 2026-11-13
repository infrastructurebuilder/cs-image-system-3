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
  README (the golden does not read comments). The modification content
  the emission copies verbatim and hashes (``HASHED_CONTENT``) is read
  like the rest: its comments reach the emitted tree, so cleaning one
  is a golden regeneration, never an exemption;
- the tests, ``tests/`` and ``packages/*/tests``: comments and
  docstrings, except one closing ``history:`` line per module, which
  names the bundle items a test came from and is how a reader follows a
  frozen ledger entry to the test that holds it today. A history line
  that wraps is exempt whole: the exemption runs from the ``history:``
  line to the blank line or the docstring's close that ends its
  paragraph;
- the workflows, ``.github/workflows/*.yml``: the ``#`` comments;
- the scripts under ``scripts/``: comments and docstrings of a Python
  file, the ``#`` comment lines of a shell script;
- this repository's hook, ``.githooks/pre-commit``, and its
  ``.gitignore``: the ``#`` comment lines;
- the starter trees under ``docs/examples/`` (the skeleton and every
  starter's overlay), which every template repository publishes: the
  ``Justfile`` whole, as the root's is; the Markdown pages whole, as the
  fixture's README is (an IAM policy document's ``Version`` literal is a
  dated value AWS requires); the alias pool's ``#`` lines but its spent
  ones (``# <name> -- <what took it>`` is the record the system writes, not
  a comment); and the ``#`` comments of everything else (the YAML, a
  workflow's ``run:`` scripts included, the ignore file, the hook). Not
  read: the modification content (``STARTER_HASHED``), hashed into the
  fingerprint of every image a team bakes from the starter, and the files
  that are values (``STARTER_VALUES``).

A docstring is read whole, a run of comments on consecutive lines as one
text and a file read whole as one text, so a token a line break splits
(the word ending one line, its number opening the next) is found; the
line reported is the one where the token starts.

Each area holds zero.

Run it by hand to list the offenders: ``uv run python
tests/test_sources_do_not_narrate.py [area ...]``.
"""
from __future__ import annotations

import ast
import bisect
import io
import re
import sys
import tokenize
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

NARRATION = re.compile(
    r"[Ss]tage\s*\d+"                               # the word, then a number (a space or none between)
    r"|[Hh]ygiene\s+(?:[IVXL]+|\d+)\b"              # a bundle by roman numeral or number
    r"|\b[Bb]undle\s+[IVXL]+\b"                     # a bundle by roman numeral
    r"|\bF\d{1,2}\b"                                # a finding number (ruff's codes have three digits)
    r"|\b20\d\d-\d\d-\d\d\b"                        # a date
    r"|(?<!DESIGN )§\d+"                            # a section sign and a number (DESIGN §3A is a page reference)
    r"|\b[Ll]edger\s+\d+"                           # a numbered ledger entry (a frozen worksheet's numbering)
)
HISTORY_LINE = re.compile(r"^\s*[Hh]istory:")
COMMENT = re.compile(r"(?:^|\s)(?:#|//)(.*)$")

#: fixture files the emission copies verbatim and hashes: a comment cleaned here moves the golden
HASHED_CONTENT = {f"tests/fixtures/config/{name}" for name in
                  ("mod_image.sh", "modify_image.yml", "setup_dask.yml", "setup_data_science.yml")}

EXAMPLES = REPO / "docs" / "examples"
#: starter files a modification runs or copies onto an image (the ``playbooks:`` and ``scripts:`` of an image's
#: ``modifications:`` items): their bytes are hashed into the image's input fingerprint, so a comment cleaned here
#: would re-bake every image a team builds from the starter. Unlike the fixture's, they are not read.
STARTER_HASHED = {f"docs/examples/{tree}/{f}" for tree, files in (
    ("complete", ("playbooks/modify_image.yml", "playbooks/setup_dask.yml", "playbooks/setup_data_science.yml",
                  "scripts/mod_image.sh")),
    *((tree, ("playbooks/setup-node.yml", "scripts/post-install.sh"))
      for tree in ("standard-aws", "standard-aws-posix", "standard-docker", "standard-gce")),
) for f in files}
#: starter files that are values, not prose, and are not read: the TEST age identity and its recipient (byte for
#: byte the frozen fixture's, which a test pins) and the marker naming the default starter
STARTER_VALUES = {f"docs/examples/{name}" for name in ("_skeleton/.age-identity", "_skeleton/.age-recipient", "DEFAULT")}
#: what a run or a tool leaves inside a starter's directory: never a file of the starter
STARTER_LITTER = {".DS_Store", "__pycache__", "generated", "_private", "tfmodules"}
#: a dated value, not narration: the policy language version every IAM policy document carries
IAM_POLICY_VERSION = re.compile(r'"Version":\s*"2012-10-17"')
#: an alias pool's spent line, ``# <name> -- <what took it, and when>``: the system's record, not a comment
ALIAS_SPENT = re.compile(r"^\s*#\s*[A-Za-z0-9][A-Za-z0-9-]*\s+--\s")

#: area -> what it reads
AREAS: dict[str, str] = {
    "sources": "comments and docstrings of packages/*/src/**/*.py",
    "modules": "the comments of every non-Python file under packages/*/src, and tfmodules/",
    "justfile": "the Justfile, whole",
    "pyproject": "pyproject.toml, whole",
    "fixture": "the YAML comments and the README of tests/fixtures/config, the hashed content included",
    "tests": "comments and docstrings of tests/ and packages/*/tests, history: lines (wrapped or not) excepted",
    "workflows": "the # comments of .github/workflows/*.yml",
    "scripts": "comments and docstrings of every file under scripts/ (Python, or a shell script's # lines)",
    "hook": "the # comment lines of .githooks/pre-commit, a shell script",
    "gitignore": "the # comment lines of .gitignore",
    "runner-image": "the # comment lines of the CI runner image's sources under ci/runner-image/ (its Dockerfile and probe)",
    "starters": "docs/examples: each Justfile and Markdown page whole, the # comments of the rest, "
                "the hashed modification content and the value files excepted",
}


#: consecutive lines read as one text: ``(line number, text)`` each
Block = list[tuple[int, str]]


def _block_tokens(block: Block) -> list[tuple[int, str, str]]:
    """``(line, token, that line's text)`` for every narration token in one
    block read as ONE text: each line stripped, the lines joined by a space,
    so a token split across a line break is found (and a page reference
    whose ``DESIGN`` ends one line is still excused). The line reported is
    the one where the token starts."""
    starts: list[int] = []
    parts: list[str] = []
    pos = 0
    for _, text in block:
        starts.append(pos)
        parts.append(text.strip())
        pos += len(parts[-1]) + 1
    out: list[tuple[int, str, str]] = []
    for m in NARRATION.finditer(" ".join(parts)):
        i = bisect.bisect_right(starts, m.start()) - 1
        out.append((block[i][0], m.group(0), parts[i]))
    return out


def _tokens(blocks: list[Block]) -> list[tuple[int, str, str]]:
    return sorted((t for b in blocks for t in _block_tokens(b)), key=lambda t: t[0])


def _report(rel: Path, blocks: list[Block]) -> list[str]:
    return [f"{rel}:{lineno}: {token!r} in {text[:90]}" for lineno, token, text in _tokens(blocks)]


def _extend_run(runs: list[Block], lineno: int, text: str) -> None:
    """Add a comment line to the run it continues (the line just above it is
    a comment too), or open a new run."""
    if not runs or runs[-1][-1][0] != lineno - 1:
        runs.append([])
    runs[-1].append((lineno, text))


def _docstring_blocks(first_line: int, text: str, *, except_history: bool) -> list[Block]:
    """A docstring as one block. With ``except_history`` each ``history:``
    paragraph is cut out: the ``history:`` line and every line after it up to
    a blank line or the docstring's close, so a history line that wraps onto
    the next line is exempt whole; the text before and after it are blocks of
    their own."""
    blocks: list[Block] = [[]]
    in_history = False
    for i, line in enumerate(text.splitlines()):
        if except_history and HISTORY_LINE.match(line):
            in_history = True
        elif in_history and not line.strip():
            in_history = False
            blocks.append([])
        if not in_history:
            blocks[-1].append((first_line + i, line))
    return [b for b in blocks if b]


def _python_blocks(src: str, *, except_history: bool, filename: str = "<sample>") -> list[Block]:
    """Every docstring of one Python source, and every run of comments on
    consecutive lines (the ``#`` dropped)."""
    doc_starts: set[tuple[int, int]] = set()
    for node in ast.walk(ast.parse(src, filename=filename)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                doc_starts.add((first.value.lineno, first.value.col_offset))
    docs: list[Block] = []
    runs: list[Block] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            _extend_run(runs, tok.start[0], tok.string.lstrip("#"))
        elif tok.type == tokenize.STRING and tok.start in doc_starts:
            docs += _docstring_blocks(tok.start[0], tok.string, except_history=except_history)
    return docs + runs


def _comment_blocks(text: str) -> list[Block]:
    """The runs of ``#`` and ``//`` comments on consecutive lines of a YAML,
    HCL, terraform or shell file."""
    runs: list[Block] = []
    for i, line in enumerate(text.splitlines(), 1):
        m = COMMENT.search(line)
        if m:
            _extend_run(runs, i, m.group(1))
    return runs


def _whole_blocks(text: str) -> list[Block]:
    return [list(enumerate(text.splitlines(), 1))]


def _python_hits(path: Path, *, except_history: bool) -> list[str]:
    """``file:line: text`` for every narration token in a docstring or a
    comment run of one Python file."""
    blocks = _python_blocks(path.read_text(), except_history=except_history, filename=str(path))
    return _report(path.relative_to(REPO), blocks)


def _whole_file_hits(path: Path) -> list[str]:
    return _report(path.relative_to(REPO), _whole_blocks(path.read_text(errors="replace")))


def _comment_hits(path: Path) -> list[str]:
    """``#`` and ``//`` comments of a YAML, HCL, terraform, shell or ignore file."""
    return _report(path.relative_to(REPO), _comment_blocks(path.read_text(errors="replace")))


def _starter_blocks(name: str, text: str) -> list[Block]:
    """One starter file, by its NAME, as the rule reads it: a Justfile whole,
    a Markdown page whole with an IAM policy's ``Version`` value blanked, the
    alias pool's comments with its spent lines blanked, and the ``#``
    comments of anything else. A blanked line keeps its place, so the line
    numbers stay the file's."""
    if name == "Justfile":
        return _whole_blocks(text)
    if name.endswith(".md"):
        return _whole_blocks(IAM_POLICY_VERSION.sub('"Version": ""', text))
    if name == "aliases.txt":
        text = "\n".join("" if ALIAS_SPENT.match(line) else line for line in text.splitlines())
    return _comment_blocks(text)


def _starter_files() -> list[Path]:
    """Every file of every starter tree, the skeleton included, but the
    hashed modification content, the value files and a run's litter."""
    skipped = STARTER_HASHED | STARTER_VALUES
    return sorted(p for p in EXAMPLES.rglob("*")
                  if p.is_file() and not STARTER_LITTER.intersection(p.parts) and str(p.relative_to(REPO)) not in skipped)


def _starter_hits(path: Path) -> list[str]:
    return _report(path.relative_to(REPO), _starter_blocks(path.name, path.read_text(errors="replace")))


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
        hashed = sorted(REPO / name for name in HASHED_CONTENT)
        out = [h for p in sorted(root.rglob("*.y*ml")) for h in _comment_hits(p)]
        out += [h for p in hashed if p.suffix != ".yml" for h in _comment_hits(p)]
        return out + [h for p in sorted(root.rglob("*.md")) for h in _whole_file_hits(p)]
    if area == "tests":
        files = sorted((REPO / "tests").glob("*.py")) + sorted(REPO.glob("packages/*/tests/*.py"))
        return [h for p in files for h in _python_hits(p, except_history=True)]
    if area == "workflows":
        return [h for p in sorted((REPO / ".github/workflows").glob("*.yml")) for h in _comment_hits(p)]
    if area == "scripts":
        out: list[str] = []
        for p in sorted(x for x in (REPO / "scripts").rglob("*") if x.is_file() and "__pycache__" not in x.parts):
            shebang = p.read_text(errors="replace").split("\n", 1)[0]
            python = p.suffix == ".py" or (shebang.startswith("#!") and "python" in shebang)
            out += _python_hits(p, except_history=False) if python else _comment_hits(p)
        return out
    if area == "hook":
        return _comment_hits(REPO / ".githooks/pre-commit")
    if area == "gitignore":
        return _comment_hits(REPO / ".gitignore")
    if area == "starters":
        return [h for p in _starter_files() for h in _starter_hits(p)]
    if area == "runner-image":
        return [h for p in sorted((REPO / "ci/runner-image").glob("*")) if p.is_file() and p.name != "TAG"
                for h in _comment_hits(p)]
    raise KeyError(area)


@pytest.mark.parametrize("area", sorted(AREAS))
def test_the_area_holds_no_narration(area: str):
    found = hits(area)
    assert not found, (
        f"{area} ({AREAS[area]}): {len(found)} narration tokens; "
        "name the behaviour or point at docs/CHANGES.md:\n  " + "\n  ".join(found[:40]))


def test_the_pattern_reads_what_it_claims():
    bad = ["stage 75 step 2", "Stage 103 branch 2", "(stage1)", "hygiene XIV item 1", "hygiene 5", "bundle VIII item 5",
           "the walk's F31", "found live 2026-09-22", "§127", "TODO §40.4", "ledger 12 item 3", "the Ledger 7 entry"]
    good = ["DESIGN §3A", "DESIGN N26", "noqa: F401", "F841", "the string stage", "docs/CHANGES.md#s75", "20261016.4",
            "2026-11", "staged", "stages", "the ledger", "a ledger of generations", "ledgers"]
    assert all(NARRATION.search(s) for s in bad), [s for s in bad if not NARRATION.search(s)]
    assert not any(NARRATION.search(s) for s in good), [s for s in good if NARRATION.search(s)]
    assert HISTORY_LINE.match("  history: bundle VIII item 5.") and not HISTORY_LINE.match("the history: of it")


#: a module whose docstring, comment run and wrapped history line each hold a token a line break splits,
#: and two comments a line apart that hold none between them
_SPLIT_PYTHON = "\n".join([
    '"""A docstring a wrap splits a token in: the work of stage',
    '42 is named here.',
    '',
    'history: a history line that wraps may name hygiene',
    'XIV on the line it wraps onto."""',
    'x = 1  # a comment run a wrap splits a token in: hygiene',
    '# XIV is named here',
    'y = 2',
    '# a comment that ends on stage',
    'z = 3',
    '# 9 opens a run of its own, so nothing is named',
    '',
])
#: the same split in a YAML comment run and an HCL one, then in a file read whole
_SPLIT_COMMENTS = "\n".join([
    "key: 1  # a YAML comment a wrap splits a token in: stage",
    "# 7 is named here",
    'resource "x" "y" {}',
    "// an HCL comment run: Hygiene",
    "// 3 is named here",
    "",
])
_SPLIT_WHOLE = "a paragraph a wrap splits a token in: stage\n128 is named here.\n"


def test_a_token_a_line_break_splits_is_found():
    """Each reader joins what it reads across line breaks -- a docstring
    whole, a run of comments on consecutive lines, a file read whole -- and
    reports the line where the token starts. A history line that wraps is
    exempt whole, a comment a line apart opens a run of its own, and a page
    reference that wraps stays excused."""
    samples = (_SPLIT_PYTHON, _SPLIT_COMMENTS, _SPLIT_WHOLE)
    assert not [line for s in samples for line in s.splitlines() if NARRATION.search(line)]   # no line holds one alone
    found = [(n, t) for n, t, _ in _tokens(_python_blocks(_SPLIT_PYTHON, except_history=True))]
    assert found == [(1, "stage 42"), (6, "hygiene XIV")], found
    found = [(n, t) for n, t, _ in _tokens(_python_blocks(_SPLIT_PYTHON, except_history=False))]
    assert found == [(1, "stage 42"), (4, "hygiene XIV"), (6, "hygiene XIV")], found
    found = [(n, t) for n, t, _ in _tokens(_comment_blocks(_SPLIT_COMMENTS))]
    assert found == [(1, "stage 7"), (4, "Hygiene 3")], found
    found = [(n, t) for n, t, _ in _tokens(_whole_blocks(_SPLIT_WHOLE))]
    assert found == [(1, "stage 128")], found
    wrapped_reference: Block = [(1, "a page reference that wraps: DESIGN"), (2, "§3A stays")]
    assert NARRATION.search(wrapped_reference[1][1]) and not _block_tokens(wrapped_reference)


_POOL = "# the alias pool, named by stage\n# 59 here\n# cod -- instance x as x-001 2026-09-23 run r1\neel\n"
#: one sample per reader of a starter file: (the file's name, its text, the tokens the rule finds there)
_STARTER_SAMPLES = [
    ("Justfile", "# a recipe\nr:\n\techo stage 5\n", [(3, "stage 5")]),                         # whole: a body too
    ("CI_SETUP.md", '{"Version": "2012-10-17"}\nfound 2026-09-22\n', [(2, "2026-09-22")]),      # the policy's is a value
    ("aliases.txt", _POOL, [(1, "stage 59")]),                                                  # a spent line is a record
    ("other.txt", _POOL, [(1, "stage 59"), (3, "2026-09-23")]),                                 # ... read as a comment elsewhere
    ("ci.yml", "key: stage 7  # a value\nrun: |\n  # hygiene XIV in a script\n", [(3, "hygiene XIV")]),
]


@pytest.mark.parametrize(("name", "text", "want"), _STARTER_SAMPLES, ids=[s[0] for s in _STARTER_SAMPLES])
def test_a_starter_file_is_read_as_its_kind(name: str, text: str, want: list[tuple[int, str]]):
    assert [(n, t) for n, t, _ in _tokens(_starter_blocks(name, text))] == want


def _modification_files(tree: Path) -> set[str]:
    """Every file the ``modifications:`` items of TREE's YAML name under
    ``playbooks:`` or ``scripts:`` (a path relative to the tree's root)."""
    named: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "modifications" and isinstance(value, list):
                    named.update(str(f) for item in value if isinstance(item, dict)
                                 for f in (item.get("playbooks") or []) + (item.get("scripts") or []))
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    for p in sorted(tree.rglob("*.y*ml")):
        for doc in yaml.safe_load_all(p.read_text()):
            walk(doc)
    return {str((tree / f).relative_to(REPO)) for f in named}


def test_the_starter_files_left_unread_are_the_hashed_content_and_the_values():
    """``STARTER_HASHED`` is exactly what the starters' modification items
    name, every listed file exists, and the area reads none of them."""
    named = set().union(*(_modification_files(t) for t in sorted(EXAMPLES.iterdir()) if t.is_dir()))
    assert named == STARTER_HASHED, sorted(named ^ STARTER_HASHED)
    unread = STARTER_HASHED | STARTER_VALUES
    assert [f for f in sorted(unread) if not (REPO / f).is_file()] == []
    assert not {str(p.relative_to(REPO)) for p in _starter_files()} & unread


if __name__ == "__main__":
    for area in (sys.argv[1:] or sorted(AREAS)):
        found = hits(area)
        print(f"== {area}: {len(found)}")
        print("\n".join(found))
