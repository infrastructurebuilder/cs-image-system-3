# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0


"""The bootstrap's question model: what an interview asks, and what a
section renders. A plugin contributes a :class:`Section` through the
:data:`ENTRY_POINT_GROUP` entry-point group, each owning the questions and
the module for its runtime or identity provider.

A ``Question`` has an id, a prompt, a kind, a default (a literal, or a
function of the checkout's facts and the earlier answers), a ``when``
condition on the earlier answers, and optionally the name of the terraform
variable it feeds (a question with no ``var`` is for the interview alone --
the secrets directory, say). A ``Section`` groups questions under a gate
("Do you want the GitHub section?") and knows how to render its part of the
root: the module call, the variables, the outputs, the secrets the script
sets, and what remains by hand.

The facts a default or a gate reads (the repository, the declared
runtimes, a probe of an account) are gathered by the core from the checkout
and reach these callables as a :class:`FactsProtocol` (stage 125): the
members a section reads, and the questions it asks of them as methods on
the object it is handed. Two rules over a value need no facts at all and
are functions here: :func:`real` (a starter placeholder is no value) and
:func:`ci_can_reach` (whether CI can be expected to reach a runtime, judged
from the shape of its declaration).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

#: The entry-point group a plugin's bootstrap section is registered in: an
#: entry point is a callable returning a :class:`Section`.
ENTRY_POINT_GROUP = "cs_image_system.bootstrap"

Answers = dict[str, Any]
KINDS = ("text", "bool", "choice", "path", "secret-path")

#: The words the coverage audit speaks (hygiene XX item 3).
MADE, READ, ADOPTED, BY_HAND = "MADE", "READ", "ADOPTED", "BY HAND"
COVERAGE_STATUSES = (MADE, READ, ADOPTED, BY_HAND)


#: The answer that means "nothing" for a question whose answer may be
#: empty (hygiene XII item 23): an empty line takes the default, so where a
#: default exists -- the roles an account holds, the subjects a role keeps
#: trusting, the labels -- the word is the only way to decline it. The
#: prompt says so.
NONE_ANSWER = "none"
EMPTY_HINT = f"answer {NONE_ANSWER} for none"


class Refused(Exception):
    """A question that cannot be answered without a person: under ``--quiet``
    its default could not be derived, or the person gave nothing. The
    message names the question."""


# ------------------------------------------------------------------ the facts

#: What a starter tree carries where a team's value goes. A default that is
#: still one of these was never filled in, so it is no default at all.
PLACEHOLDER_MARKS = ("REPLACE-ME", "REPLACE_ME", "123456789012")


def is_placeholder(value: Any) -> bool:
    return value is None or any(mark in str(value) for mark in PLACEHOLDER_MARKS) or str(value).strip() == ""


def real(value: Any) -> str | None:
    """The value as text, or None when it is empty or a starter placeholder."""
    return None if is_placeholder(value) else str(value).strip()


def ci_can_reach(runtime: dict[str, Any]) -> bool:
    """Whether CI can be expected to reach the runtime, judged from the shape
    of its declaration and from nothing provider-specific. A runtime that
    names no daemon address is a cloud's API, or the environment's own
    daemon whose address the workflow supplies: reachable from anywhere. A
    runtime that names a ``host`` is a daemon on someone's machine, and the
    starters' workflow reaches an ``ssh://`` one only; a local socket, a
    ``tcp://`` host, a host the YAML keeps as an ``ENC[...]`` marker
    (unreadable here) and a named ``context`` are not assumed reachable: the
    interview asks."""
    host = str(runtime.get("host") or "").strip()
    if host:
        return host.startswith("ssh://")
    return not str(runtime.get("context") or "").strip()


class FactsProtocol(Protocol):
    """What the checkout can tell a section without loading anything,
    gathered by the core: the repository from ``git remote`` and its ids
    from ``gh``, the runtimes, the team, the module source base and the
    state backends from the raw ``cfg/*.yml`` (read as YAML, never templated
    or validated). ``probe`` runs a read-only CLI call against an account
    and answers ``(exit code, output)``; a test answers instead."""

    config_root: Path
    remote_url: str | None
    owner: str | None
    repo: str | None
    owner_id: int | None
    repo_id: int | None
    default_branch: str | None
    runtimes: list[dict[str, Any]]
    team: str | None
    module_source_base: str
    state_backends: list[dict[str, Any]]
    probe: Callable[..., tuple[int, str]]

    @property
    def repository(self) -> str | None: ...

    def runtimes_of_type(self, type_word: str) -> list[dict[str, Any]]:
        """Every runtime the tree declares with ``type: <type_word>`` (the
        word a runtime plugin registers), in declaration order."""
        ...

    def runtime_of_type(self, kind: str) -> dict[str, Any] | None:
        """The tree's runtime of one type: the default one of that type, else
        the first declared."""
        ...

    def default_state_backend(self, kind: str) -> dict[str, Any] | None:
        """The tree's declared state backend of a type: the default, else the first."""
        ...

    def other_state_backends(self, kind: str) -> list[dict[str, Any]]:
        """The tree's OTHER declared backends of a type: every one but the
        default, in declaration order."""
        ...

    def bound_backend_names(self) -> set[str]:
        """The backends some root is bound to: every ``state_configuration`` a
        builder or runtime names, resolved through aliases, plus the default."""
        ...

    def first_runtime_name(self, *, prefer: tuple[str, ...] = ()) -> str | None:
        """The default runtime's name: the one marked ``is_default``, else the
        first whose type or aliases name a preferred cloud, else the first CI
        can reach, else the first."""
        ...

    def collect(self, key: str, *, named: bool = True) -> list[dict[str, Any]]:
        """Every entry under ``key`` in ANY ``cfg/*.yml`` of the checkout, in
        file-name order (the loader reads the whole directory, so must this)."""
        ...


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
    #: An OBSERVATION of the world (is the connection active?), not a choice:
    #: every interview asks the world again and the earlier answer is only the
    #: fallback when the world cannot be asked. A choice keeps its earlier
    #: answer as its default.
    observed: bool = False
    #: The answer may be empty: the prompt says ``(answer none for none)`` and
    #: the word ``none`` is coerced to the empty answer (an empty line takes
    #: the default, which for such a question may itself be empty, shown as
    #: ``[none]``).
    may_be_empty: bool = False

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"question {self.id!r}: kind must be one of {KINDS}, not {self.kind!r}")
        if self.kind == "choice" and not self.choices:
            raise ValueError(f"question {self.id!r}: a choice question needs choices")

    def default_for(self, facts: Any, answers: Answers) -> Any:
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
        text = str(value).strip() if value is not None else None
        if self.may_be_empty and text is not None and text.lower() == NONE_ANSWER:
            return ""
        return text


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
    #: Where the script lists it: lower first, ties in the order met. The
    #: core's two and the plugins' pick values that keep a generated script
    #: and README in the order they had before sections declared their own
    #: secrets, so a committed root does not reorder; a section that picks
    #: none comes after them all.
    order: int = 100


@dataclass(frozen=True)
class Variable:
    """A repository Actions variable (not secret) the workflow reads, set by
    the GitHub section's module from the interview: ``name`` is the
    variable's, ``answer`` the id of the declaring section's question whose
    answer is its value. An empty or missing answer sets nothing, and an
    unwanted section's variables are not set."""
    name: str
    answer: str
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
    #: The root's state backend when this section can name one (decision D8:
    #: the tree's declared backend once its bucket exists): ``(type,
    #: settings)``. The first section offering one decides; none means local.
    backend: tuple[str, dict[str, Any]] | None = None
    root_hcl: str = ""                                               # blocks for the root's main.tf (import blocks, say)
    #: What the operator's shell must carry to plan and apply this section:
    #: ``(NAME, shell expression, why)``. Printed as ``export`` lines in the
    #: README's Apply block, so the identity terraform acts as is the one the
    #: interview asked as, and nobody discovers it from a 403.
    apply_env: tuple[tuple[str, str, str], ...] = ()
    #: What a ``tofu destroy`` of the root would take that the root did not
    #: make (hygiene XII item 23): a grant added to an account that already
    #: existed, which every tree reading the account relied on; a role
    #: adopted by import, which the destroy deletes outright. Listed in the
    #: README so nobody learns it from the plan.
    destroy_takes: tuple[str, ...] = ()
    #: The audit (hygiene XX item 3): for every underlying resource the
    #: tree's declarations imply, what this section does about it --
    #: ``(resource, status, why)`` with status one of MADE, READ, ADOPTED,
    #: BY HAND -- so a gap is a line, never a silence. The README tabulates
    #: it; each BY HAND line carries its reason.
    coverage: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class Section:
    name: str
    title: str
    questions: tuple[Question, ...]
    render: Callable[..., Rendered]
    description: str = ""
    #: The render reads the checkout's facts too (``render(answers,
    #: facts)``): a section that says what it does NOT make (a declared
    #: backend bound to no root) needs the declarations, not only the
    #: answers. The generator gathers them from the raw ``cfg/`` without
    #: loading, as the interview does.
    wants_facts: bool = False
    #: The render reads the loaded sections too (``render(answers, ...,
    #: sections=...)``): the section that writes the secrets script sets
    #: every loaded section's secrets, so it must see them. The generator
    #: passes every section this install offers, wanted or not.
    wants_sections: bool = False
    #: Whether the section is wanted when nobody has said: a cloud's section
    #: asks the tree (it is wanted where the tree declares a runtime of its
    #: type, or keeps its state in that cloud), so the quiet interview of a
    #: tree on one cloud is not refused on another cloud's questions. None
    #: means wanted.
    wanted: Callable[[Any], bool] | None = None
    #: The repository secrets this section's part of CI reads, each set by
    #: the generated script from a file named after it in the secrets
    #: directory. The core knows only its own (the age identity, the proof
    #: user's key); a cloud's section names the credentials its workflow
    #: steps read, and the script sets the union, the core's first, then
    #: each loaded section's in section-name order. A section whose render
    #: can do better -- an ARN that is an output of the applied root -- also
    #: lists that secret in its ``Rendered`` with ``source="output"``, and
    #: the output wins over the file.
    secrets: tuple[Secret, ...] = ()
    #: The Actions variables this section's part of CI reads, each valued
    #: by one of the section's answers: the GitHub section's module sets the
    #: union of every wanted section's, the core's first, then each
    #: section's in section-name order. The core names only the runtime to
    #: perform on and the runtimes to guard; a cloud's section names what
    #: its workflow steps read (a region, say).
    variables: tuple[Variable, ...] = ()

    def gate_id(self) -> str:
        return f"want_{self.name}"

    def wanted_default(self, facts: Any) -> bool:
        return True if self.wanted is None else bool(self.wanted(facts))


class Raw(str):
    """An HCL expression written as is (a reference, a function call)."""
