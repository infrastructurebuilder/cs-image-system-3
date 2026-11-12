# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The test suite pins behaviour, not prose.

Every constant here is a ceiling that only moves DOWN. A test that compares an
English sentence against a command's output breaks on every rewording and
proves nothing a token would not; a test that reads the Justfile, a workflow
or a document and looks for its words pins the text, not what it does. The
measure, over ``tests/test_*.py`` and ``packages/*/tests/test_*.py``:

* **sentence pins** -- ``assert`` statements whose tested expression (the
  message after the comma is not looked at) holds a string literal, or the
  literal parts of an f-string, with ``PROSE_WORDS`` (six) or more *prose
  words*: whitespace-separated tokens made of letters and apostrophes alone,
  a trailing ``,.;:!?`` or surrounding quotes and parentheses allowed. A
  path, a flag, a key, a number, a shell command or ``name=value`` is not a
  prose word, so an exact emitted command may stay pinned; a sentence may not.
* **document pins** -- ``assert`` statements with an ``in`` / ``not in``
  comparison whose right-hand side is the text of a ``Justfile``, a
  ``.github/workflows`` file, a ``*.md`` or a ``README`` **of the repository**
  -- a path built on a module constant (an ``UPPER_CASE`` name such as ``REPO``
  or ``EXAMPLES``; a tree a test generated under ``tmp_path`` is a command's
  output and falls under the sentence rule) -- read with ``read_text()`` in
  the same scope (or the module scope, or through a helper that returns such
  a text), and whatever is derived from it by assignment or iteration. A
  ``yaml.safe_load`` of a workflow is the parsed shape, not the text, and
  does not count. The replacement for such a pin: ``just
  --summary`` names the recipe and its printed plan (``just -n``) or its dry
  form carries the fact; the workflow parses and names its jobs by key; a
  document keeps the one fact (a heading, a link target, a command that
  exists) rather than a sentence.

A change that needs a larger number has added a prose pin: pin the exit code
and ONE stable token instead. Lowering a constant after a clean-up is the
expected edit, and the test asks for it once the count falls more than
``SLACK`` below the ceiling.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# measured at the end of the behaviour-naming rewrite (the root suite and the packages' tests together)
SENTENCE_PINS_MAX = 37
DOC_PINS_MAX = 27
SLACK = 8                                # a fall larger than this asks for the constant to come down

DOC_FILE = re.compile(r"Justfile|\.github|workflows|\.md\b|README")
PROSE_WORDS = 6
_WORD = re.compile(r"^[A-Za-z][A-Za-z']*[,.;:!?]?$")
_SCOPE = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_CONSTANT = re.compile(r"^[A-Z][A-Z0-9_]*$")          # a module constant: the repository's own path, not a generated tree


def _prose_words(s: str) -> int:
    return sum(1 for w in s.split() if _WORD.match(w.strip("()\"'")))


def _literal_words(node: ast.AST) -> int:
    best = 0
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            best = max(best, _prose_words(sub.value))
        elif isinstance(sub, ast.JoinedStr):
            text = " ".join(v.value for v in sub.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            best = max(best, _prose_words(text))
    return best


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _calls(node: ast.AST) -> set[str]:
    return {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def _walk_scope(body: list[ast.stmt]):
    """Every node of the statements, without descending into a nested scope."""
    todo: list[ast.AST] = []
    for stmt in body:
        yield stmt
        if not isinstance(stmt, _SCOPE):
            todo += list(ast.iter_child_nodes(stmt))
    while todo:
        node = todo.pop()
        yield node
        todo += [c for c in ast.iter_child_nodes(node) if not isinstance(c, _SCOPE)]


class _Module:
    """One test module, read once: its source segments, and what it learns
    about which names and which helpers hold a document's text."""

    def __init__(self, path: Path):
        src = path.read_text()
        self.tree = ast.parse(src)
        self.lines = src.splitlines(keepends=True)
        self.functions = [f for f in ast.walk(self.tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
        self.doc_funcs: set[str] = set()              # helpers whose return value is a document's text
        self.module_names: set[str] = set()
        self.scope_names: dict[int, set[str]] = {}
        self._segments: dict[int, str] = {}

    def seg(self, n: ast.AST) -> str:
        key = id(n)
        if key not in self._segments:
            a, b = getattr(n, "lineno", 0), getattr(n, "end_lineno", 0)
            lines = self.lines
            if not a or not b:
                self._segments[key] = ""
            elif a == b:
                self._segments[key] = lines[a - 1][n.col_offset:n.end_col_offset]      # type: ignore[attr-defined]
            else:
                self._segments[key] = lines[a - 1][n.col_offset:] + "".join(lines[a:b - 1]) + lines[b - 1][:n.end_col_offset]   # type: ignore[attr-defined]
        return self._segments[key]

    def reads_file(self, node: ast.AST) -> bool:
        s = self.seg(node)
        return ("read_text(" in s and bool(DOC_FILE.search(s)) and "safe_load(" not in s
                and any(_CONSTANT.match(n) for n in _names(node)))

    def holds_document(self, node: ast.AST, names: set[str]) -> bool:
        """Whether the expression is a document's text: it reads one, it names
        something bound to one, or it calls a helper that returns one."""
        return self.reads_file(node) or bool(_names(node) & names) or bool(_calls(node) & self.doc_funcs)

    def bound_in(self, body: list[ast.stmt], inherited: set[str]) -> set[str]:
        """The names a scope binds to a document's text (two passes, so a name
        bound from a later-defined one is found)."""
        names: set[str] = set()
        for _ in range(2):
            for node in _walk_scope(body):
                if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                    if "safe_load(" in self.seg(node.value):
                        continue
                    if self.holds_document(node.value, names | inherited):
                        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                        for t in targets:
                            names |= _names(t)
                elif isinstance(node, (ast.For, ast.comprehension)):
                    if self.holds_document(node.iter, names | inherited):
                        names |= _names(node.target)
        return names

    def returns_document(self, f: ast.FunctionDef | ast.AsyncFunctionDef, names: set[str]) -> bool:
        for ret in _walk_scope(f.body):
            if isinstance(ret, ast.Return) and ret.value is not None and "safe_load(" not in self.seg(ret.value):
                if self.holds_document(ret.value, names | self.module_names):
                    return True
        return False

    def learn(self) -> None:
        """Find the document names of the module and of each function, and the
        helpers that return a document (two passes: a helper found in the first
        makes the names bound from its calls findable in the second)."""
        for _ in range(2):
            self.module_names = self.bound_in(self.tree.body, set())
            for f in self.functions:
                names = self.bound_in(f.body, self.module_names)
                self.scope_names[id(f)] = names
                if self.returns_document(f, names):
                    self.doc_funcs.add(f.name)

    def pins_a_document(self, test: ast.expr, names: set[str]) -> bool:
        """Whether an assertion's test holds a membership comparison against a document's text."""
        for cmp in ast.walk(test):
            if isinstance(cmp, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in cmp.ops):
                if any(self.holds_document(c, names) for c in cmp.comparators):
                    return True
        return False

    def pins(self) -> tuple[list[int], list[int]]:
        sentences: list[int] = []
        doc_pins: list[int] = []
        scopes: list[tuple[ast.AST, list[ast.stmt]]] = [(self.tree, self.tree.body), *((f, f.body) for f in self.functions)]
        for f, body in scopes:
            names = self.module_names | self.scope_names.get(id(f), set())
            for node in _walk_scope(body):
                if not isinstance(node, ast.Assert):
                    continue
                if _literal_words(node.test) >= PROSE_WORDS and node.lineno not in sentences:
                    sentences.append(node.lineno)
                if self.pins_a_document(node.test, names) and node.lineno not in doc_pins:
                    doc_pins.append(node.lineno)
        return sorted(sentences), sorted(doc_pins)


def measure_file(path: Path) -> tuple[list[int], list[int]]:
    """``(sentence pin lines, document pin lines)`` of one test module."""
    module = _Module(path)
    module.learn()
    return module.pins()


def _test_files() -> list[Path]:
    return sorted(REPO.glob("tests/test_*.py")) + sorted(REPO.glob("packages/*/tests/test_*.py"))


def measure(repo: Path = REPO) -> dict[str, tuple[list[int], list[int]]]:
    return {str(f.relative_to(repo)): measure_file(f) for f in _test_files()}


@pytest.fixture(scope="module")
def numbers() -> dict[str, tuple[list[int], list[int]]]:
    return measure()


def _worst(numbers: dict[str, tuple[list[int], list[int]]], which: int) -> str:
    rows = sorted(((len(v[which]), f, v[which][:6]) for f, v in numbers.items() if v[which]), reverse=True)[:8]
    return "; ".join(f"{f}: {n} (lines {ls})" for n, f, ls in rows)


def test_sentence_pins_only_fall(numbers):
    total = sum(len(s) for s, _ in numbers.values())
    assert total <= SENTENCE_PINS_MAX, (
        f"sentence pins {total} > {SENTENCE_PINS_MAX}: a new prose pin -- pin the exit code and one token instead. "
        f"Most in: {_worst(numbers, 0)}")
    assert total >= SENTENCE_PINS_MAX - SLACK, (
        f"sentence pins fell to {total}: lower SENTENCE_PINS_MAX to {total} (the ceiling only moves down)")


def test_document_pins_only_fall(numbers):
    total = sum(len(d) for _, d in numbers.values())
    assert total <= DOC_PINS_MAX, (
        f"document pins {total} > {DOC_PINS_MAX}: a new pin of a Justfile's, workflow's or document's text -- "
        f"`just --summary` names the recipe and its plan (`just -n`) or dry form carries the fact; the workflow "
        f"parses and names its jobs; a document keeps one fact. Most in: {_worst(numbers, 1)}")
    assert total >= DOC_PINS_MAX - SLACK, (
        f"document pins fell to {total}: lower DOC_PINS_MAX to {total} (the ceiling only moves down)")


def test_the_measure_reads_what_it_claims():
    """The measure's own contract, on a small module: a sentence, a command, a document's
    text through a helper, a parsed workflow, and the scope rule."""
    sample = '''
from pathlib import Path
import yaml
REPO = Path(".")

def _recipe():
    return (REPO / "Justfile").read_text()

def test_a(out):
    assert "the package database was held by another process" in out          # a sentence: counted
    assert "sudo apt-get -o DPkg::Lock::Timeout=30 install -y x" == out        # a command: not prose
    assert "exit 1" in out, "the message after the comma is never a pin"

def test_b():
    body = _recipe()
    assert "uv build" in body                                                  # the Justfile's text: counted
    wf = yaml.safe_load((REPO / ".github/workflows/ci.yml").read_text())
    assert "verify" in wf["jobs"]                                              # the parsed shape: not counted
    text = (REPO / "REUSE.toml").read_text()
    assert "Apache" in text                                                    # another file: not counted

def test_c(tmp_path):
    text = "no document here"
    assert "x" in text                                                         # a name shared with test_b's: its own scope
    readme = (tmp_path / "out" / "README.md").read_text()
    assert "## Heading" in readme                                              # a generated tree: a command's output
'''
    path = REPO / "tests" / "_pin_measure_sample.py"
    try:
        path.write_text(sample)
        sentences, docs = measure_file(path)
    finally:
        path.unlink(missing_ok=True)
    assert len(sentences) == 1 and len(docs) == 1, (sentences, docs)


if __name__ == "__main__":                   # `uv run python tests/test_tests_pin_behaviour.py`: the breakdown
    res = measure()
    for f, (s, d) in res.items():
        if s or d:
            print(f"{len(s):4d} {len(d):4d}  {f}  sentences={s[:12]} documents={d[:12]}")
    print("TOTAL sentence pins", sum(len(s) for s, _ in res.values()), "document pins", sum(len(d) for _, d in res.values()))
