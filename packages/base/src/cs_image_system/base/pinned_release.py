# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A committing run is made by the release the tree pins.

A configuration tree names the release it runs in a one-line file at its
root (``.csis-version``). The tree's CI installs exactly that release from
an index and compares the committed emission with the one it generates
itself, so a recording made by anything else can be judged BEHIND there:
another version, or -- the case a version comparison cannot see -- a source
checkout whose version string equals the pin while it holds commits no
release carries.

So a run that will commit is held to the pin BEFORE it generates
(:func:`hold_to_pin`). It is refused when the version running is not the
pinned one, and when any distribution of the system was installed from
somewhere other than an index, whatever its version says. A tree without
the file is not checked, and neither is a run that does not commit. The
operator goes on deliberately with ``--allow-unpinned`` (or
``CSIS_ALLOW_UNPINNED`` in the environment), and the run then says, in one
line, what it was allowed past.

A committing restamp of lineage is held the same way (:data:`RESTAMP`): it
records, as each build's current fingerprint, the one the code running
computes, and the pinned release may not compute the same. A disposal is
not held: it records what was removed, which no version of the code
computes differently.

How an install is told from an index install: an installer writes
``direct_url.json`` (PEP 610) into the dist-info of whatever it installed
from a URL or a path -- an editable workspace member, a local directory, an
archive, a repository reference -- and never for a distribution resolved
from an index. Every installed distribution of the system is read, not the
umbrella alone: one part installed from a path under an umbrella from an
index is still code no release carries.

Everything here takes the tree's root and the facts about the install as
arguments; nothing reads a run's context.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from urllib.parse import unquote, urlparse

from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

#: the one-line file at a tree's root that names the release the tree runs
PIN_FILE = ".csis-version"
#: the option of ``run`` that lets a committing run go on unpinned, and the same thing in the environment
ALLOW_FLAG = "--allow-unpinned"
ALLOW_ENVVAR = "CSIS_ALLOW_UNPINNED"
#: the tokens the two outcomes carry in what the run prints
REFUSED = "REFUSED unpinned"
ALLOWED = "ALLOWED unpinned"

#: the release's own distribution (what a tree's CI installs at the pin); every part's name starts with it
RELEASE_DISTRIBUTION = "cs-image-system"
#: read for the version when the umbrella is not installed (the parts installed one by one)
SYSTEM_DISTRIBUTION = "cs-image-system-system"

DIRECTORY, REPOSITORY, ARCHIVE = "directory", "repository", "archive"

_SHOWN = 3


@dataclass(frozen=True)
class HeldCommand:
    """A committing command the pin holds, in the words its refusal uses:
    ``name`` begins every line it prints, ``stake`` is what goes wrong when
    something other than the pinned release makes it (and what was not
    done), ``verb`` and ``recipe`` are how the tree's shell does it, and
    ``risk`` closes the one line of a command that was allowed past."""
    name: str
    stake: str
    verb: str
    recipe: str
    risk: str


#: a run that commits its emission and meta-state
RUN = HeldCommand(
    name="run --commit",
    stake="The tree's CI installs the pinned release and compares the committed emission with its own, so a "
          "recording made by anything else can be judged BEHIND there. Nothing was generated and nothing was "
          "committed.",
    verb="record", recipe="just record",
    risk="the tree's CI may judge this recording BEHIND")
#: a restamp that writes fingerprints into lineage and commits them
RESTAMP = HeldCommand(
    name="lineage restamp --commit",
    stake="A restamp records, as each build's current fingerprint, the one the code running computes. The pinned "
          "release, which the tree's CI and every later run use, may not compute the same, and would then read "
          "those builds as changed. Nothing was computed, written, retagged or committed.",
    verb="restamp", recipe="just cli --no-dry-run lineage restamp --runtime <runtime> --commit",
    risk="the pinned release may not agree with the fingerprints this restamp records")


@dataclass(frozen=True)
class SourceInstall:
    """One distribution installed from somewhere other than an index:
    ``kind`` is ``directory`` (a source checkout, editable or not),
    ``repository`` or ``archive``; ``url`` is what its record names."""
    distribution: str
    url: str
    kind: str = DIRECTORY

    @property
    def path(self) -> str | None:
        """The local path a ``file:`` URL names; None for any other URL."""
        parsed = urlparse(self.url)
        return unquote(parsed.path) if parsed.scheme == "file" and parsed.path else None

    def describe(self) -> str:
        if self.kind == DIRECTORY:
            return f"a development checkout at {self.path or self.url or 'a path its record does not name'}"
        return f"installed from the {self.kind} {self.url or 'its record does not name'}"


@dataclass(frozen=True)
class Installed:
    """What is installed: the release's version (None when neither the
    umbrella nor the system distribution is installed) and every
    distribution of the system that did not come from an index."""
    version: str | None
    sources: tuple[SourceInstall, ...] = ()


def source_install(distribution: str, direct_url: str | None) -> SourceInstall | None:
    """The record ``direct_url.json`` holds for one distribution, or None
    for an index install (no such file). A file that cannot be read as the
    record still says the distribution did not come from an index."""
    if not direct_url:
        return None
    try:
        doc = json.loads(direct_url)
    except ValueError:
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    kind = DIRECTORY if "dir_info" in doc else REPOSITORY if "vcs_info" in doc else ARCHIVE
    return SourceInstall(distribution, str(doc.get("url") or ""), kind)


def installed_release(distributions: Iterable[metadata.Distribution] | None = None) -> Installed:
    """The facts about the running install, read from the installed
    distributions' own records (``distributions``: the environment's unless
    given). A name found twice counts once, the first as the import system
    would take it."""
    versions: dict[str, str] = {}
    sources: list[SourceInstall] = []
    for dist in metadata.distributions() if distributions is None else distributions:
        name = canonicalize_name(dist.metadata.get("Name") or "")
        if name in versions or not (name == RELEASE_DISTRIBUTION or name.startswith(RELEASE_DISTRIBUTION + "-")):
            continue
        versions[name] = dist.version
        source = source_install(name, dist.read_text("direct_url.json"))
        if source is not None:
            sources.append(source)
    version = versions.get(RELEASE_DISTRIBUTION) or versions.get(SYSTEM_DISTRIBUTION)
    return Installed(version, tuple(sorted(sources, key=lambda s: s.distribution)))


def read_pin(root: Path) -> str | None:
    """The release ``<root>/.csis-version`` names: its first line holding
    anything. None when the file is absent or names nothing."""
    try:
        text = (Path(root) / PIN_FILE).read_text()
    except OSError:
        return None
    return next((line.strip() for line in text.splitlines() if line.strip()), None)


def same_release(pinned: str, running: str | None) -> bool:
    """Is ``running`` the pinned version? Compared as versions, so two
    spellings of one version are one; a pin that is no version at all is
    compared as text."""
    if running is None:
        return False
    try:
        return Version(pinned) == Version(running)
    except InvalidVersion:
        return pinned == running


@dataclass(frozen=True)
class PinVerdict:
    """What :func:`hold_to_pin` found. ``pinned`` None means nothing was
    checked (no pin, or the run does not commit)."""
    pinned: str | None = None
    running: str | None = None
    version_differs: bool = False
    sources: tuple[SourceInstall, ...] = ()
    allowed: bool = False

    @property
    def unpinned(self) -> bool:
        """The system running is not the pinned release from an index."""
        return self.version_differs or bool(self.sources)

    @property
    def refused(self) -> bool:
        return self.unpinned and not self.allowed

    def running_as(self) -> str:
        """The running system in a phrase: its version, the pin when they
        differ, and where it was installed from when not an index."""
        said = f"{RELEASE_DISTRIBUTION} {self.running or 'at no installed version'}"
        if self.version_differs:
            said += f" (the pin is {self.pinned})"
        if self.sources:
            lead = next((s for s in self.sources if s.distribution == RELEASE_DISTRIBUTION), self.sources[0])
            names = ", ".join(s.distribution for s in self.sources[:_SHOWN])
            more = ", ..." if len(self.sources) > _SHOWN else ""
            count = f"{len(self.sources)} distribution{'' if len(self.sources) == 1 else 's'}"
            said += f", {lead.describe()} ({count} not installed from an index: {names}{more})"
        return said

    def lines(self, held: HeldCommand = RUN) -> list[str]:
        """What the command prints: nothing when the pin holds or nothing
        was checked, ONE line when it was allowed past the pin, the refusal
        with both remedies otherwise. ``held`` is the command that asked."""
        if not self.unpinned:
            return []
        pin = f"this tree pins {RELEASE_DISTRIBUTION} {self.pinned} ({PIN_FILE})"
        if self.allowed:
            return [f"{held.name}: {ALLOWED} -- {pin} and what is running is {self.running_as()}; going on because "
                    f"{ALLOW_FLAG} (or {ALLOW_ENVVAR}) says so, and {held.risk}"]
        return [
            f"{held.name}: {REFUSED} -- {pin} and the system running is not that release installed from an index:",
            f"  running: {self.running_as()}",
            f"  {held.stake}",
            f"  Either {held.verb} with the pinned release -- in the tree's shell: "
            f"CSIS=\"$HOME/.local/bin/{RELEASE_DISTRIBUTION}\" {held.recipe} -- after `just take <version>` if the tree "
            "should move to another release,",
            f"  or go on deliberately: {ALLOW_FLAG} on this command, or {ALLOW_ENVVAR}=1 in the environment "
            f"({ALLOW_ENVVAR}=1 {held.recipe}).",
        ]


def hold_to_pin(root: Path, *, commit: bool, allow: bool = False, installed: Installed | None = None) -> PinVerdict:
    """Hold a command over the tree at ``root`` to the release the tree
    pins (a run, or a restamp of lineage).

    Nothing is checked for a command that does not commit or a tree without
    a pin. Otherwise the verdict says whether the version running differs
    from the pin and which distributions did not come from an index;
    ``allow`` is the operator's word to go on all the same. ``installed``
    is the facts about the install (the environment's unless given). The
    caller prints :meth:`PinVerdict.lines` and stops on ``refused``."""
    if not commit:
        return PinVerdict()
    pinned = read_pin(root)
    if pinned is None:
        return PinVerdict()
    facts = installed_release() if installed is None else installed
    return PinVerdict(pinned=pinned, running=facts.version, version_differs=not same_release(pinned, facts.version),
                      sources=facts.sources, allowed=allow)
