# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar, cast

_T = TypeVar("_T")


def singleton(cls: type[_T]) -> type[_T]:
    """Cache one instance per class.

    At runtime the decorated name is a factory function that constructs the
    instance on first call and returns the cached instance thereafter. It is
    TYPED as the class itself so the name remains valid in annotations
    (``ctx: GlobalTypeContext``) and calls/members are fully checked against
    the class. Two consequences of that deliberate lie:

    - the wrapped class's ``__init__`` must give its parameters defaults if
      no-arg accessor calls are used (GlobalTypeContext enforces its required
      configuration at runtime on first construction);
    - the decorated name must not be used with ``isinstance``/``issubclass``
      (it is not actually a class at runtime).
    """
    instances: dict[type[_T], _T] = {}

    def get_instance(*args, **kwargs) -> _T:
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return cast(type[_T], get_instance)
