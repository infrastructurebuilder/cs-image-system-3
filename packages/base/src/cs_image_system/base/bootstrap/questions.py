# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The question model: what an interview asks, and what a section renders.

A ``Question`` has an id, a prompt, a kind, a default (a literal, or a
function of the checkout's facts and the earlier answers), a ``when``
condition on the earlier answers, and optionally the name of the terraform
variable it feeds (a question with no ``var`` is for the interview alone --
the secrets directory, say). A ``Section`` groups questions under a gate
("Do you want the GitHub section?") and knows how to render its part of the
root: the module call, the variables, the outputs, the secrets the script
sets, and what remains by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .facts import Facts

Answers = dict[str, Any]

KINDS = ("text", "bool", "choice", "path", "secret-path")


class Refused(Exception):
    """A question that cannot be answered without a person: under ``--quiet``
    its default could not be derived, or the person gave nothing. The
    message names the question."""


@dataclass(frozen=True)
class Question:
    id: str
    prompt: str
    kind: str = "text"
    default: Any = None                               # a literal, or callable(facts, answers) -> value | None
    choices: tuple[str, ...] = ()
    when: Callable[[Answers], bool] | None = None
    var: str | None = None                            # the terraform variable this answer feeds
    help: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"question {self.id!r}: kind must be one of {KINDS}, not {self.kind!r}")
        if self.kind == "choice" and not self.choices:
            raise ValueError(f"question {self.id!r}: a choice question needs choices")

    def default_for(self, facts: "Facts", answers: Answers) -> Any:
        return self.default(facts, answers) if callable(self.default) else self.default

    def applies(self, answers: Answers) -> bool:
        return self.when is None or bool(self.when(answers))

    def coerce(self, value: Any) -> Any:
        """The answer in the type the kind implies; a wrong choice or an
        unreadable yes/no is refused by name."""
        if self.kind == "bool":
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in ("y", "yes", "true", "1"):
                return True
            if text in ("n", "no", "false", "0"):
                return False
            raise Refused(f"{self.id}: {value!r} is not yes or no")
        if self.kind == "choice":
            text = str(value).strip()
            if text not in self.choices:
                raise Refused(f"{self.id}: {text!r} is not one of {', '.join(self.choices)}")
            return text
        return str(value).strip() if value is not None else None


@dataclass(frozen=True)
class Secret:
    """A repository secret the generated script sets: from a file the
    interview named (``source="file"``: ``<secrets dir>/<name>``) or from an
    output of the applied root (``source="output"``, ``detail`` the output's
    name)."""
    name: str
    source: str                       # "file" | "output"
    detail: str = ""
    comment: str = ""


@dataclass(frozen=True)
class Rendered:
    """A section's contribution to the root, from its answers."""
    module: str | None = None                                        # tfmodules/<module>
    module_args: dict[str, Any] = field(default_factory=dict)        # argument -> HCL value (Raw for references)
    variables: tuple[tuple[str, str, str], ...] = ()                 # (name, type, description)
    tfvars: dict[str, Any] = field(default_factory=dict)             # variable -> value
    outputs: tuple[tuple[str, str, str], ...] = ()                   # (name, expression, description)
    required_providers: dict[str, dict[str, str]] = field(default_factory=dict)
    provider_blocks: str = ""                                        # rendered provider "x" {} blocks
    secrets: tuple[Secret, ...] = ()
    by_hand: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()                                      # README lines about what was generated


@dataclass(frozen=True)
class Section:
    name: str
    title: str
    questions: tuple[Question, ...]
    render: Callable[[Answers], Rendered]
    description: str = ""

    def gate_id(self) -> str:
        return f"want_{self.name}"


class Raw(str):
    """An HCL expression written as is (a reference, a function call)."""
