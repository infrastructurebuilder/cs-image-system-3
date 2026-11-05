# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a plugin adds to the command line.

The system's console script owns the root command and its own sub-apps
(``run``, ``verify``, ``state``, ...). A plugin that has commands of its
own -- an identity plugin's token minting, a login proof that only its
client can drive -- registers an entry point in the group
:data:`COMMANDS_ENTRY_POINT_GROUP`. The entry point is a callable that
returns a list of :class:`CommandMount`; the console script reads every
installed entry point of the group when it starts and mounts each record,
so a command appears exactly when the plugin that owns it is installed and
is absent otherwise.

A mount is one of two things:

* a **sub-app**: ``CommandMount(name="workload", app=<a typer.Typer>)``
  adds the whole sub-app under the root as ``cs-image-system workload``;
* a **command under an existing sub-app**: ``CommandMount(name="login",
  path=("verify",), callback=<a function>)`` adds ``cs-image-system verify
  login``, the callback's signature and docstring making its options and
  help the way any typer command's do.

The shared-command rule: two plugins may mount the SAME callback (the
same function object) or the same sub-app object under the same name and
path -- the core's ``verify login`` is one callback every identity plugin
mounts -- and the console script mounts it once; a DIFFERENT callback or
sub-app under a name a built-in or an earlier mount took is refused when
the script starts, because two owners of one command is a packaging
error, never a silent replacement.

The record types the app and the callback loosely on purpose: the contract
imports no command-line library, and the console script is the only
reader. ``deferred_load`` says the sub-app's commands decide for themselves
whether the configuration tree loads (they find a ``deferred_load``
callable in ``ctx.obj`` and call it when they need the tree); without it
the tree loads before the command runs, as for every built-in command.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

#: The entry-point group a plugin registers its command mounts in; the entry
#: point's value is a callable returning ``list[CommandMount]``.
COMMANDS_ENTRY_POINT_GROUP = "cs_image_system.commands"


@dataclass(frozen=True)
class CommandMount:
    """One thing a plugin adds to the command line: a sub-app (``app``) under
    the root, or a command (``callback``) under the sub-app ``path`` names.
    Exactly one of ``app`` and ``callback`` is given; ``path`` is empty for
    a sub-app and names the enclosing sub-apps, outermost first, for a
    command (``()`` mounts the command on the root itself)."""

    name: str
    app: Any = None
    path: tuple[str, ...] = ()
    callback: Callable[..., Any] | None = None
    deferred_load: bool = False

    def __post_init__(self) -> None:
        if not self.name or not str(self.name).strip():
            raise ValueError("a command mount needs a name")
        if (self.app is None) == (self.callback is None):
            raise ValueError(f"command mount {self.name!r}: give exactly one of app and callback")
        if self.app is not None and self.path:
            raise ValueError(f"command mount {self.name!r}: a sub-app mounts on the root; path must be empty")
        if self.callback is not None and self.deferred_load:
            raise ValueError(f"command mount {self.name!r}: deferred_load is a sub-app's setting; a command "
                             "under an existing sub-app loads the way that sub-app does")

    @property
    def is_app(self) -> bool:
        return self.app is not None
