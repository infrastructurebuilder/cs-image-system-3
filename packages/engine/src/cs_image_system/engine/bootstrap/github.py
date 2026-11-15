# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The GitHub section (CI_SETUP.md section 3.2 and 3.7): the repository's
default branch, the ruleset that protects the production branch while
letting ``github-actions[bot]`` push the records ``perform`` writes, the
Actions permissions, the Actions variables that are not secret, and the
script that sets the secrets from files the interview named.

The script sets every secret the install's CI reads, but this module
names only the system's own: each plugin's section declares the secrets
its part of the workflow reads (``Section.secrets``), and the render here
takes the union of every loaded section's -- the core's first, then each
section's in section-name order -- so the core names no cloud. The Actions
variables that are not secret work the same way: this module names the
runtime to perform on and the runtimes to guard, a cloud's section names
what its workflow steps read, and the module here sets the union."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .facts import Facts, first_runtime_name, first_unreachable_runtime_name
from .questions import BY_HAND, MADE, READ, Answers, Question, Raw, Rendered, Secret, Section, Variable

MODULE = "bootstrap_github"

#: The system's own secrets (CI_SETUP.md 3.6 and 3.7), each read from a file
#: the interview named. A cloud's credentials are its section's to name.
SECRETS: tuple[Secret, ...] = (
    Secret("CSIS_CONFIG_IDENTITY", "file", comment="CI's age identity, the whole file (3.6)", order=40),
    Secret("CSIS_PROOF_SSH_KEY", "file", comment="a posix group's proof user's private key, PEM (3.7; only with one)", order=60),
)

#: The Actions variables the core's part of the workflow reads.
VARIABLES: tuple[Variable, ...] = (
    Variable("PERFORM_RUNTIME", "perform_runtime", "the runtime the perform job bakes, releases and applies retention on"),
    Variable("GUARD_RUNTIME", "guard_runtime", "the runtimes CI must never bake on"),
)


def secrets_union(sections: Iterable[Section] = ()) -> tuple[Secret, ...]:
    """Every repository secret the script sets: the system's own first, then
    each loaded section's in section-name order, each name once (the first
    to name it keeps it). A section with no secrets adds none; a section
    not installed contributes none, so the script lists exactly what this
    install's CI can read."""
    out: list[Secret] = list(SECRETS)
    seen = {s.name for s in out}
    for section in sorted(sections, key=lambda s: s.name):
        for s in section.secrets:
            if s.name not in seen:
                seen.add(s.name)
                out.append(s)
    return tuple(sorted(out, key=lambda s: s.order))        # a stable sort: ties keep the order met


def declared_variables(sections: Iterable[Section] = ()) -> tuple[tuple[str, Variable], ...]:
    """Every Actions variable a loaded section declares, as ``(section name,
    variable)``: the core's first, then each section's in section-name
    order, each variable name once."""
    out: list[tuple[str, Variable]] = [("github", v) for v in VARIABLES]
    seen = {v.name for _, v in out}
    for section in sorted(sections, key=lambda s: s.name):
        for v in section.variables:
            if v.name not in seen:
                seen.add(v.name)
                out.append((section.name, v))
    return tuple(out)


def actions_variables(sections: Iterable[Section], all_answers: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """The Actions variables to set, from the answers: each declared variable
    whose section is wanted and whose answer is not empty."""
    out: dict[str, str] = {}
    for section_name, v in declared_variables(sections):
        answers = all_answers.get(section_name) or {}
        value = answers.get(v.answer) if answers.get("wanted") else None
        if value:
            out[v.name] = str(value)
    return out


def _listed(names: list[str]) -> str:
    """``A, B and C``: the names as prose."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def _perform_default(facts: Facts, answers: Answers) -> str | None:
    return first_runtime_name(facts)


def _guard_default(facts: Facts, answers: Answers) -> str:
    """A runtime CI cannot reach (a container daemon on a host it has no
    way into) is the one it must never bake on; empty when every runtime is
    reachable."""
    unreachable = first_unreachable_runtime_name(facts)
    return unreachable if unreachable and unreachable != answers.get("perform_runtime") else ""


QUESTIONS: tuple[Question, ...] = (
    Question("repository", "The GitHub repository, as owner/name", "text",
             default=lambda f, a: f.repository, var="github_repository",
             help="read from `git remote get-url origin` when the checkout has a GitHub remote"),
    Question("default_branch", "The default branch, where people push", "text",
             default=lambda f, a: f.default_branch or "develop", var="github_default_branch"),
    Question("production_branch", "The branch the perform job runs on", "text", default="main",
             var="github_production_branch"),
    Question("protect_production", "Protect the production branch with a ruleset (no deletion, no force "
             "push; github-actions[bot] may still push the records)?", "bool", default=True,
             var="github_protect_production"),
    Question("perform_runtime", "PERFORM_RUNTIME: the runtime the perform job bakes, releases and applies "
             "retention on", "text", default=_perform_default,
             help="a `name:` from cfg/runtime-builders.yml; none could be read"),
    Question("guard_runtime", "GUARD_RUNTIME: a runtime CI must never bake on (several, separated by spaces)", "text",
             default=_guard_default, may_be_empty=True,
             help="by default a container runtime whose daemon CI has no way into (not an ssh:// host)"),
    Question("secrets_dir", "The directory holding one file per secret, named after the secret, that "
             "set-secrets.sh reads (never committed)", "path", default="_uncommitted/secrets",
             help="a path relative to the repository root"),
)


def render(answers: Answers, *, sections: Iterable[Section] = (),
           all_answers: Mapping[str, Mapping[str, Any]] | None = None) -> Rendered:
    """The section's rendering; ``sections`` are every section this install
    offers, whose secrets the script sets beside the system's own and whose
    Actions variables the module sets from ``all_answers`` (every section's
    answers, this section's included)."""
    repository = str(answers["repository"])
    owner = repository.split("/", 1)[0]
    sections = tuple(sections)
    variables = actions_variables(sections, {**(all_answers or {}), "github": answers})
    declared = _listed([v.name for _, v in declared_variables(sections)])
    return Rendered(
        module=MODULE,
        module_args={
            "repository": Raw("var.github_repository"),
            "default_branch": Raw("var.github_default_branch"),
            "production_branch": Raw("var.github_production_branch"),
            "protect_production": Raw("var.github_protect_production"),
            "variables": Raw("var.github_actions_variables"),
        },
        variables=(
            ("github_owner", "string", "the repository's owner, for the github provider"),
            ("github_repository", "string", "the repository as owner/name"),
            ("github_default_branch", "string", "the default branch, where people push"),
            ("github_production_branch", "string", "the branch the perform job runs on"),
            ("github_protect_production", "bool", "a ruleset on the production branch: no deletion, no force push"),
            ("github_actions_variables", "map(string)", "Actions variables that are not secret"),
        ),
        tfvars={
            "github_owner": owner,
            "github_repository": repository,
            "github_default_branch": answers["default_branch"],
            "github_production_branch": answers["production_branch"],
            "github_protect_production": bool(answers["protect_production"]),
            "github_actions_variables": variables,
        },
        outputs=(
            ("github_repository_id", f"module.{MODULE}.repository_id", "the repository's numeric id (the one trust conditions pin)"),
            ("github_repository_node_id", f"module.{MODULE}.node_id", "the repository's node id"),
        ),
        required_providers={"github": {"source": "integrations/github", "version": ">= 6.0"}},
        provider_blocks='provider "github" {\n  owner = var.github_owner   # the token: GITHUB_TOKEN (README.md, "Apply")\n}\n',
        apply_env=(("GITHUB_TOKEN", "$(gh auth token)", "the github provider's token; `gh` must be logged in as someone "
                    "who administers the repository"),),
        secrets=secrets_union(sections),
        by_hand=(
            "The secrets' VALUES: one file per secret under the secrets directory "
            f"(`{answers.get('secrets_dir')}`, never committed), then `bash set-secrets.sh` (CI_SETUP.md 3.7).",
            "The age identity for CI (CI_SETUP.md 3.6): `age-keygen`, the public key into encryption.recipients, `reencrypt`.",
            f"The values in `.github/workflows/ci.yml` still marked REPLACE-ME: {declared} "
            "are set as Actions variables by this root, but the workflow reads its own literals until a release makes it read `vars`.",
        ),
        notes=(
            f"the repository `{repository}`: default branch `{answers['default_branch']}`, perform on "
            f"`{answers['production_branch']}`" + (" (a ruleset: no deletion, no force push; ordinary pushes, the perform job's included, unaffected)"
                                                    if answers["protect_production"] else " (unprotected)"),
            "Actions enabled for all actions; workflow permissions stay read-only (the workflow asks for what each job needs)",
            "Actions variables: " + (", ".join(f"{k}={v}" for k, v in variables.items()) or "none"),
        ),
        coverage=(
            (f"the repository `{repository}`", READ, "it exists: read as a data source; the bootstrap never creates a repository"),
            (f"the default branch `{answers['default_branch']}`", MADE, "set on the repository"),
            ("Actions enabled, workflow permissions read-only", MADE, "set on the repository"),
            (f"the ruleset on `{answers['production_branch']}`", MADE if answers["protect_production"] else BY_HAND,
             "no deletion, no force push" if answers["protect_production"] else "declined at the interview (protect_production: no)"),
            ("the Actions variables", MADE if variables else BY_HAND,
             ", ".join(variables) if variables else f"none named: {declared} stay literals in the workflow"),
            ("the secrets' values", BY_HAND, "one file per secret under the secrets directory, set by the script; "
             "a value never enters the tfvars or the state (decision D2)"),
            ("the age identity for CI", BY_HAND, "made on your machine (`age-keygen`); the system never makes a key"),
        ),
    )


def github_section() -> Section:
    return Section(name="github", title="GitHub", questions=QUESTIONS, render=render, wants_sections=True,
                   secrets=SECRETS, variables=VARIABLES,
                   description="the repository's branches, protection, Actions permissions and variables; the secrets script")
