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
pair. The core asks the builder classes ``classify_failure`` for every
exception in the cause chain -- a provider's error arrives wrapped -- and
prints the first ``LoadFailureReport`` it gets back. It names no
provider's exception itself. Anything nobody claims keeps its traceback:
an unknown failure is not dressed up as a known one.

The classes asked are those of the ``type:`` words the configuration
DECLARES, when the load got far enough to read them: a provider installed
beside the configuration and not used by it is never asked, so installing
it cannot change what a failure of this configuration says. Only a load
that failed before its builder lists were read asks every installed class.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, cast

from cs_image_system.base.encryption import MissingIdentityError
from cs_image_system.base.registry import AmbiguousTypeError, Registry, UnknownTypeError, bare_name
from cs_image_system.contract.session import LoadFailureReport

from ..loader import Unusable, installed_registry, unusable_plugins
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


def _builder_classes(reg: Registry | None = None) -> list[type]:
    """Every builder class ``reg`` holds once, in registration order. A
    load that failed left no run to ask, so without a registry the
    installed plugins are read into one of this function's own."""
    seen: dict[int, type] = {}
    for cls in (reg if reg is not None else installed_registry()).builders.values():
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


def unknown_type_lines(e: UnknownTypeError, unusable: tuple[Unusable, ...] | None = None) -> list[str]:
    """The configuration error for a ``type:`` word nothing usable registers.

    When an installed plugin that could not be used (``unusable``: this
    process's, from discovery, unless given) would have registered the
    word, the line names that plugin and why it could not be used, and
    says nothing about installing: it IS installed. Otherwise the line is
    the unknown word's own (the missing extra named), followed by one line
    for each unusable plugin whose words discovery could not read (its
    module did not import, or its entry point collided), since the word
    may be one of those."""
    plugins = unusable_plugins() if unusable is None else unusable
    name = bare_name(e.word)
    owners = [u for u in plugins if any(w.split(":", 1)[1] == name for w in u.words)]
    kind = e.classification.value.removesuffix("_model").removesuffix("_builder").replace("_", " ")
    if owners:
        return [f" - {kind} type {e.word!r} is registered by {u.named()}, which is installed but could not be "
                f"used: {u.said().split(': ', 1)[1]}" for u in owners]
    unread = [u for u in plugins if not u.words]
    return [f" - {e}", *(f"   (installed but could not be used: {u.said()})" for u in unread)]


def declared_classes(classes: list[type], declared_types: Iterable[str]) -> list[type]:
    """The classes of ``classes`` that a configuration declaring the
    ``type:`` words ``declared_types`` uses: those whose registered word is
    one of them (a qualified word names its class by its last part)."""
    words = {bare_name(str(word)) for word in declared_types}
    return [cls for cls in classes if bare_name(str(getattr(cls, "csis_name", lambda: "")())) in words]


def classify_load_failure(exc: BaseException, reg: Registry | None = None, *,
                          declared_types: Iterable[str] | None = None) -> LoadFailure | None:
    """The one-line form of a known load-time failure, or None for one
    that keeps its traceback. The builder classes asked are ``reg``'s,
    or the installed plugins' when none is given (the CLI's case: the
    load failed, so there is no run's registry); with ``declared_types``
    (the ``type:`` words the configuration declares) only the classes those
    words name are asked."""
    classes = _builder_classes(reg)
    if declared_types is not None:
        classes = declared_classes(classes, declared_types)
    for e in _chain(exc):
        if isinstance(e, UnknownTypeError):
            # a `type:` word no USABLE plugin registers: either none is installed (the missing extra named)
            # or the plugin that would register it is installed and could not be used, which is said instead
            return LoadFailure("configuration", [*unknown_type_lines(e), "Validation failed with 1 error(s)."], code=1)
        if isinstance(e, (ReservedNameError, AmbiguousTypeError)):
            # a reserved word used as a name, or a bare `type:` word that several
            # plugins' classes answer to: the tree's fault, one line
            return LoadFailure("configuration", [f" - {e}", "Validation failed with 1 error(s)."], code=1)
        if isinstance(e, MissingIdentityError):
            return LoadFailure("environment", [f"the configuration cannot load: {e}", f"({IDENTITY_REMEDY})"])
        report = _ask_plugins(classes, e)
        if report is not None:
            return LoadFailure(report.kind, list(report.lines), code=report.code)
    return None
