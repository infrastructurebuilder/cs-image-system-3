# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""One tofu process at a time (stage 43; a command of the CLI since stage 64).

OpenTofu's provider plugin cache (``TF_PLUGIN_CACHE_DIR``) is not safe under
concurrent ``init``: a cycle that overlapped the bar's tests failed on it. So
every invocation that may execute tofu takes ``cs-image-system --locked``,
which holds a lock DIRECTORY under the cache (``mkdir`` is atomic) for the
whole command and releases it however the command ends. A second holder is
refused, loudly, with exit 75 (``EX_TEMPFAIL``) and the holder's pid. Until
stage 64 this was ``scripts/with-tofu-lock``, a shell wrapper the recipes
called; the exit code, the message and the lock's shape are unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

CACHE_ENV = "TF_PLUGIN_CACHE_DIR"
LOCK_DIRNAME = ".lock"
EX_TEMPFAIL = 75


class LockHeld(Exception):
    def __init__(self, lock: Path, holder: str) -> None:
        self.lock = lock
        self.holder = holder
        super().__init__(f"another tofu-using command holds {lock} (pid {holder}) -- one tofu process at a "
                         "time; wait for it, or remove that directory if the process is gone")


class NoCacheDir(Exception):
    def __init__(self) -> None:
        super().__init__(f"{CACHE_ENV} is not set (run through just, which exports it)")


def lock_path(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    cache = env.get(CACHE_ENV)
    if not cache:
        raise NoCacheDir()
    return Path(cache) / LOCK_DIRNAME


def acquire(environ: dict[str, str] | None = None) -> Callable[[], None]:
    """Take the lock; return the function that releases it. Raises
    ``NoCacheDir`` or ``LockHeld``."""
    lock = lock_path(environ)
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        try:
            holder = (lock / "pid").read_text().strip() or "?"
        except OSError:
            holder = "?"
        raise LockHeld(lock, holder) from None
    (lock / "pid").write_text(f"{os.getpid()}\n")

    def release() -> None:
        try:
            (lock / "pid").unlink(missing_ok=True)
            lock.rmdir()
        except OSError:
            pass

    return release
