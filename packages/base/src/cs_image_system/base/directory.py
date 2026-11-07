# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The working directory, scoped: a module that imports nothing of the
package, so a model (``models/executable.py``) and the helpers above it
(``utils.py``, which imports that model) can both use it."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Iterator


@contextlib.contextmanager
def in_directory(path: str | Path) -> Iterator[Path]:
    """Run the block inside ``path`` and come back.

    The process's working directory is ``path`` for the block and the
    directory the caller had afterwards, however the block ends -- an
    exception included. Blocks nest like a stack: each one restores the
    directory the block around it was in. Yields the directory entered,
    absolute, for the caller's logging.
    """
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield Path.cwd()
    finally:
        os.chdir(previous)
