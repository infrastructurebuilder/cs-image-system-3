# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""One line for a failure that stops the configuration from loading.

Every command loads the configuration first, and a known failure there is
one line and an exit code, not a traceback under a good message. Two
failures are the core's own: a shell with no age identity
(``MissingIdentityError``, the ENVIRONMENT's, exit 2 like the preflight's
absent session), a reserved word used as a name (``ReservedNameError``,
the CONFIGURATION's, exit 1 under ``Validation failed with 1 error(s).``),
a bare ``type:`` word that different plugins' classes answer to
(``AmbiguousTypeError``, the same line, naming every qualified form) and
a ``type:`` word no installed plugin registers (``UnknownTypeError``, the
same line, naming the umbrella's extra that installs the plugin when
the umbrella's table knows the word, else the words the installed
plugins register there).
Every other known failure is a plugin's: a runtime's lapsed credentials, a
container runtime's unreachable daemon, a group builder's missing key
pair. The core asks every registered builder class ``classify_failure``
for every exception in the cause chain -- a provider's error arrives
wrapped -- and prints the first ``LoadFailureReport`` it gets back. It
names no provider's exception itself. Anything nobody claims keeps its
traceback: an unknown failure is not dressed up as a known one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterator, cast

from cs_image_system.contract.session import LoadFailureReport

from ..encryption import MissingIdentityError
from ..loader import load_plugins
from ..registry import AmbiguousTypeError, UnknownTypeError, current_registry
from ..reserved_names import ReservedNameError

IDENTITY_REMEDY = ("the shell never loaded `.envrc` (a new terminal, a directory direnv has not entered or "
                   "allowed): `source .envrc`, or `direnv allow`")


@dataclass
class LoadFailure:
    kind: str                       # "configuration" | "environment"
    lines: list[str] = field(default_factory=list)
    code: int = 2


def _chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        yield e
        e = e.__cause__ or e.__context__


def _builder_classes() -> list[type]:
    """Every registered builder class once, in registration order."""
    load_plugins()
    seen: dict[int, type] = {}
    for cls in current_registry().builders.values():   # pre-load: no run's registry yet
        seen.setdefault(id(cls), cls)
    return list(seen.values())


def _ask_plugins(classes: list[type], e: BaseException) -> LoadFailureReport | None:
    for cls in classes:
        hook = cast(Callable[[BaseException], LoadFailureReport | None] | None, getattr(cls, "classify_failure", None))
        if not callable(hook):
            continue
        report = hook(e)
        if report is not None:
            return report
    return None


def classify_load_failure(exc: BaseException) -> LoadFailure | None:
    """The one-line form of a known load-time failure, or None for one
    that keeps its traceback."""
    classes = _builder_classes()
    for e in _chain(exc):
        if isinstance(e, (ReservedNameError, AmbiguousTypeError, UnknownTypeError)):
            # a reserved word used as a name, a bare `type:` word that several
            # plugins' classes answer to, or a `type:` word no installed plugin
            # registers (the missing extra named): the tree's fault, one line
            return LoadFailure("configuration", [f" - {e}", "Validation failed with 1 error(s)."], code=1)
        if isinstance(e, MissingIdentityError):
            return LoadFailure("environment", [f"the configuration cannot load: {e}", f"({IDENTITY_REMEDY})"])
        report = _ask_plugins(classes, e)
        if report is not None:
            return LoadFailure(report.kind, list(report.lines), code=report.code)
    return None
