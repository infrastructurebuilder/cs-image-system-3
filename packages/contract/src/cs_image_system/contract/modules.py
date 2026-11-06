# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""How a plugin declares the terraform modules it ships.

A plugin's terraform modules are package data inside its wheel, one
directory per module under one modules directory, and the plugin names
that directory with a single entry point in the group
:data:`MODULES_ENTRY_POINT_GROUP`::

    [project.entry-points."cs_image_system.modules"]
    modules = "cs_image_system.some_runtime:tfmodules"

The value is ``<package>:<dirname>``: an importable package and the name
of the directory inside it that holds the modules. The core resolves the
directory as package data (``importlib.resources``) and reads it; it never
imports the package for its code, so listing the modules costs no plugin
import. Every immediate subdirectory of that directory holding at least
one file is a module, known by its directory name (``some_instance``,
``some_storage``), which is what a generated ``module`` call's source
ends in. A module name two distributions ship is refused.

The namespace a module is reported under comes from the distribution that
declares the entry point, exactly as a plugin's registrations do: the
``cs-image-system-`` prefix and the ``-plugin`` suffix dropped, so the
``cs-image-system-some-runtime-plugin`` distribution's modules are
``some-runtime``'s and the core's are ``base``'s.
"""

#: The entry-point group a plugin declares its modules directory in: one
#: entry point per plugin, the value ``<package>:<dirname>``.
MODULES_ENTRY_POINT_GROUP = "cs_image_system.modules"
