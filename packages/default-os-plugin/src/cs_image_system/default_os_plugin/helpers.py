# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging


log = logging.getLogger(__name__)


def rpm_or_dpkg_present_check(package: str) -> str:
    """The package assertion the bakes carried before the OS type owned
    the package manager: rpm's answer, else dpkg's where dpkg exists, and
    an exit naming the package when neither says installed. Both the apt
    and the dnf types answer with it, so every bake's bytes stand as they
    were; one manager each is a later decision. The line exits for itself
    because ``set -e`` ignores a command in an AND-OR list (a bake once
    went green twice asserting a package that was not there)."""
    return (f"if ! rpm -q {package} >/dev/null 2>&1 && "
            f"! {{ command -v dpkg >/dev/null 2>&1 && dpkg -s {package} >/dev/null 2>&1; }}; "
            f"then printf 'package %s is not installed\\n' {package} >&2; exit 1; fi")
