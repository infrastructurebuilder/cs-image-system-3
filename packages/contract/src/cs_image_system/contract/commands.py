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

A mount is one of three things:

* a **sub-app**: ``CommandMount(name="workload", app=<a typer.Typer>)``
  adds the whole sub-app under the root as ``cs-image-system workload``;
* a **command under an existing sub-app**: ``CommandMount(name="login",
  path=("verify",), callback=<a function>)`` adds ``cs-image-system verify
  login``, the callback's signature and docstring making its options and
  help the way any typer command's do;
* a **command the core provides**, mounted by name: ``CommandMount(
  name="login", path=("verify",), kit_command=VERIFY_LOGIN)`` asks the
  console script to mount the core's own login proof there (a plugin
  names the command, and imports nothing of the core to mount it).
  The names are the :data:`KIT_COMMANDS` below.

The shared-command rule: two plugins may mount the SAME callback (the
same function object), the same core command by name, or the same sub-app
object under the same name and path -- the core's ``verify login`` is one
command every identity plugin mounts -- and the console script mounts it
once; a DIFFERENT callback or sub-app under a name a built-in or an
earlier mount took is refused when the script starts, because two owners
of one command is a packaging error, never a silent replacement.

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

#: The core's commands a plugin may mount by name (``kit_command``): the
#: login proof, which every identity plugin mounts as ``verify login``.
VERIFY_LOGIN = "verify-login"
KIT_COMMANDS = (VERIFY_LOGIN,)


@dataclass(frozen=True)
class CommandMount:
    """One thing a plugin adds to the command line: a sub-app (``app``) under
    the root, or a command (``callback``, or one of the core's by name,
    ``kit_command``) under the sub-app ``path`` names. Exactly one of
    ``app``, ``callback`` and ``kit_command`` is given; ``path`` is empty
    for a sub-app and names the enclosing sub-apps, outermost first, for a
    command (``()`` mounts the command on the root itself)."""

    name: str
    app: Any = None
    path: tuple[str, ...] = ()
    callback: Callable[..., Any] | None = None
    deferred_load: bool = False
    kit_command: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not str(self.name).strip():
            raise ValueError("a command mount needs a name")
        given = sum(x is not None for x in (self.app, self.callback, self.kit_command))
        if given != 1:
            raise ValueError(f"command mount {self.name!r}: give exactly one of app and callback (or kit_command)")
        if self.kit_command is not None and self.kit_command not in KIT_COMMANDS:
            raise ValueError(f"command mount {self.name!r}: the core provides no command {self.kit_command!r} "
                             f"(it provides {', '.join(KIT_COMMANDS)})")
        if self.app is not None and self.path:
            raise ValueError(f"command mount {self.name!r}: a sub-app mounts on the root; path must be empty")
        if self.app is None and self.deferred_load:
            raise ValueError(f"command mount {self.name!r}: deferred_load is a sub-app's setting; a command "
                             "under an existing sub-app loads the way that sub-app does")

    @property
    def is_app(self) -> bool:
        return self.app is not None
