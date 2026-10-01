# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The interview runner.

Each section opens with its gate ("Do you want the GitHub section?"); the
section's questions follow only when it is wanted, each shown with its
default, which is the earlier answer when there is one (a second interview
re-asks only what a person wants to change), else the question's own. With
``quiet`` every default is taken and nothing is asked; a question whose
default cannot be derived is REFUSED by name rather than guessed. Sections
not named by ``only`` keep their earlier answers untouched.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from .facts import Facts
from .questions import Answers, Question, Refused, Section

Ask = Callable[[str, Any, str, tuple[str, ...]], Any]


def terminal_ask(prompt: str, default: Any, kind: str, choices: tuple[str, ...]) -> Any:
    """One question on the terminal: the prompt, the default in brackets,
    an empty answer takes the default."""
    if kind == "bool":
        shown = "Y/n" if default else "y/N"
    elif kind == "choice":
        shown = "/".join(c if c != default else f"[{c}]" for c in choices)
    else:
        shown = "" if default is None else str(default)
    suffix = f" [{shown}]" if shown and kind != "choice" else (f" ({shown})" if kind == "choice" else "")
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if raw:
            return raw
        if default is not None:
            return default
        print("  an answer is needed")


def run_interview(sections: Iterable[Section], facts: Facts, *, quiet: bool = False,
                  prior: Mapping[str, Mapping[str, Any]] | None = None,
                  only: Iterable[str] | None = None, ask: Ask = terminal_ask) -> dict[str, Answers]:
    """Answers per section: ``{"github": {"wanted": True, "repository": ...}}``."""
    prior = dict(prior or {})
    wanted_sections = set(only or ())
    result: dict[str, Answers] = {}
    for section in sections:
        prev = dict(prior.get(section.name) or {})
        if wanted_sections and section.name not in wanted_sections:
            if prev:
                result[section.name] = prev          # not asked this time: kept as answered before
            continue
        want_default = bool(prev.get("wanted", True))
        gate = Question(section.gate_id(), f"Do you want the {section.title} section?", "bool", want_default)
        wanted = want_default if quiet else gate.coerce(ask(gate.prompt, want_default, "bool", ()))
        answers: Answers = {"wanted": bool(wanted)}
        if not wanted:
            result[section.name] = answers
            continue
        for q in section.questions:
            if not q.applies(answers):
                continue
            default = prev[q.id] if q.id in prev else q.default_for(facts, answers)
            if quiet:
                if default is None or default == "" and q.kind in ("path", "secret-path"):
                    raise Refused(f"{section.name}.{q.id}: {q.prompt} -- no default can be derived"
                                  + (f" ({q.help})" if q.help else "")
                                  + "; answer it without --quiet, or put it in bootstrap.yaml")
                value = default
            else:
                value = ask(q.prompt, default, q.kind, q.choices)
                if value is None:
                    raise Refused(f"{section.name}.{q.id}: {q.prompt} -- no answer")
            answers[q.id] = q.coerce(value)
        result[section.name] = answers
    for name, prev in prior.items():            # sections this install does not know: kept, never dropped
        result.setdefault(name, dict(prev))
    return result
