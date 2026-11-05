# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a runtime or a state backend says about the session it needs, and
about a failure that stops a configuration from loading. The core asks
these of the plugin and prints what it answers; it reads no credential
cache, runs no provider CLI and names no provider's exception itself.
Both records are plain data: the plugin fills them, the core judges them
(``preflight`` against the expected run length, the load against its exit
codes)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SessionStatus:
    """The state of the session a runtime or backend will use.

    ``source`` says what was read (a profile name, a credentials file, a
    daemon's address); ``expires_at`` the fixed expiry when one is
    readable, else ``None``; ``note`` the one-line explanation the
    preflight prints after the source; ``present`` ``False`` when there
    is nothing to read at all; ``renews`` ``True`` when the credential
    refreshes itself and only its presence can be judged; ``renew`` the
    command that renews the session, printed when it has lapsed."""

    source: str
    expires_at: datetime | None = None
    note: str = ""
    present: bool = True
    renews: bool = False
    renew: str | None = None


@dataclass(frozen=True)
class LoadFailureReport:
    """One known load-time failure in its one-line form. ``kind`` is
    ``environment`` (a session, a key pair, an identity: the shell's
    fault; the load ends as the preflight's absent session does) or
    ``configuration`` (the tree's fault; the load ends as a validation
    error does); ``lines`` what is printed; ``code`` the exit code."""

    kind: str
    lines: list[str] = field(default_factory=list)
    code: int = 2
