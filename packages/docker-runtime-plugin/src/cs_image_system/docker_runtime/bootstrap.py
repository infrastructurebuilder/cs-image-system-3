# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The container-host section of the bootstrap.

A read-and-say section with no terraform module, because by decision
nothing in it can be created: a docker daemon is a host somebody runs, and
whoever reaches it is root on that host. What the section does instead is
read the tree's docker runtime from the raw ``cfg/`` (never loading it, and
never printing an address: a ``host`` may be an ``ENC[age:...]`` marker) and
ask the one question the rest of the bootstrap needs answered, *can CI reach
the daemon?*

* **Yes** (an ``ssh://`` host, or the environment's daemon with an address
  in the workflow, the transports the starters' workflow reaches): the two
  repository secrets that workflow reads to reach it, the ssh private key and
  the host's ``known_hosts`` line (``DOCKER_HOST_SSH_KEY`` and
  ``DOCKER_HOST_KNOWN_HOSTS``: this section's own, which the GitHub
  section's script sets with the rest), are set from files, and the section says that neither is made here. The key
  belongs to a user on the host who may use the daemon; it is made on your
  machine, never by the system.
* **No** (a local socket, a context, a ``tcp://`` host, or a host the YAML
  keeps as a marker): CI never performs on the runtime, and the section says
  to name it in ``GUARD_RUNTIME`` so a change to its declaration fails CI
  loudly before anything runs (the GitHub section's default for that
  variable already names a runtime CI cannot reach).

The section also records what it does NOT make, in the audit the README
tabulates: the daemon, the network it names, the docker CLI on the runner.
"""

from __future__ import annotations

from typing import Any

from cs_image_system.contract.bootstrap import (BY_HAND, READ, Answers, FactsProtocol as Facts, Question, Rendered,
                                                Secret, Section, ci_can_reach, real)

RUNTIME_TYPE = "docker"
GUIDE = "CI_SETUP.md 3.4a"

#: The repository secrets the starters' workflow reads to reach a docker
#: host over ssh; both from files, since neither is made by any root.
SECRETS: tuple[Secret, ...] = (
    Secret("DOCKER_HOST_SSH_KEY", "file",
           comment="the private key (PEM) of a user on the docker host who may use its daemon (3.4a; only with a docker host CI reaches)",
           order=50),
    Secret("DOCKER_HOST_KNOWN_HOSTS", "file",
           comment="the docker host's known_hosts line, checked by hand (3.4a; only with a docker host CI reaches)", order=51),
)

def _runtime(facts: Facts) -> dict[str, Any]:
    return facts.runtime_of_type(RUNTIME_TYPE) or {}


def _runtime_default(facts: Facts, answers: Answers) -> str | None:
    name = _runtime(facts).get("name")
    return str(name) if name else None


def _transport(runtime: dict[str, Any]) -> str:
    """How the runtime names its daemon, from the raw YAML: ``ssh``, ``tcp``,
    ``unix``, ``context``, ``marker`` (an encrypted host, unreadable here) or
    ``environment`` (neither: the daemon of the machine that runs the tool)."""
    host = str(runtime.get("host") or "").strip()
    if host.startswith("ENC["):
        return "marker"
    if host:
        scheme = host.split("://", 1)[0].lower() if "://" in host else "unix"
        return scheme if scheme in ("ssh", "tcp", "unix") else "unix"
    return "context" if real(runtime.get("context")) else "environment"


def _reach_default(facts: Facts, answers: Answers) -> bool:
    return ci_can_reach(_runtime(facts))


QUESTIONS: tuple[Question, ...] = (
    Question("runtime", "The docker runtime this section is about (a `name:` from cfg/runtime-builders.yml)", "text",
             default=_runtime_default,
             help="no runtime of type docker could be read from cfg/"),
    Question("ci_reaches", "Can CI reach the docker daemon (an ssh:// host the workflow can log in to)?", "bool",
             default=_reach_default,
             help="the starters' workflow reaches an ssh:// host only; say no for a socket, a context or a tcp:// host"),
)


def render(answers: Answers, facts: Facts | None = None) -> Rendered:
    name = str(answers.get("runtime") or "the docker runtime")
    reaches = bool(answers.get("ci_reaches"))
    transport = _transport(_runtime(facts)) if facts is not None else "environment"
    by_hand: list[str] = [
        f"The daemon of `{name}` is the team's: install, patch and secure it on its host; whoever can reach it is "
        "root on that host, and the system says so rather than hiding it (CONFIGURATION.md section 4).",
    ]
    if reaches:
        by_hand.append(
            "CI's way in: make an ed25519 key for a user on the docker host who may use the daemon "
            f"(`ssh-keygen -t ed25519 -f DOCKER_HOST_SSH_KEY -N ''`), authorize its public half there, put the private "
            "half in the secrets directory as `DOCKER_HOST_SSH_KEY`, and the host's key line (`ssh-keyscan -t ed25519 "
            f"HOST`, checked against the host by another route) as `DOCKER_HOST_KNOWN_HOSTS` ({GUIDE}).")
    else:
        by_hand.append(
            f"CI cannot reach `{name}`: name it in the `GUARD_RUNTIME` Actions variable (the GitHub section's default "
            "does) so a change to its declaration fails CI before anything runs, and keep PERFORM_RUNTIME on a "
            "runtime CI can reach, or leave the `perform` job unconfigured (it skips, and says so).")
    return Rendered(
        by_hand=tuple(by_hand),
        notes=(
            f"the docker runtime `{name}`: its daemon is named by "
            + {"ssh": "an ssh:// host", "tcp": "a tcp:// host", "unix": "a local socket", "context": "a docker context",
               "marker": "an encrypted host", "environment": "the environment (DOCKER_HOST, else the local socket)"}.get(
                   transport, "the environment"),
            "CI " + ("reaches it over ssh with DOCKER_HOST_SSH_KEY and DOCKER_HOST_KNOWN_HOSTS"
                     if reaches else "does not reach it: it is a runtime CI must never bake on"),
            "nothing here is terraform: the section reads the declaration and says what remains",
        ),
        coverage=(
            (f"the daemon of `{name}`", BY_HAND, "a host somebody runs; the system never installs or configures a daemon"),
            ("the network the runtime names", BY_HAND, "referenced by name and never created or changed: the team's, by decision"),
            ("the docker CLI on the runner", READ, "the runner image carries it (CI_RUNNER.md); the workflow only checks it is there"),
            ("CI's key to the daemon's host" if reaches else "CI's performing run on the runtime",
             BY_HAND,
             "made on your machine and set by the script from a file; the system never makes a key" if reaches
             else "not built: CI has no way into the daemon, so the runtime is guarded instead"),
        ),
    )


def wanted(facts: Facts) -> bool:
    """The tree declares a docker runtime."""
    return facts.runtime_of_type(RUNTIME_TYPE) is not None


def docker_section() -> Section:
    return Section(name="docker", title="Container host", questions=QUESTIONS, render=render, wanted=wanted,
                   wants_facts=True, secrets=SECRETS,
                   description="the docker daemon CI can or cannot reach, the secrets that reach it, the runtime to guard")
