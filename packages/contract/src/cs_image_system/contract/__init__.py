# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The plugin contract (stage 30).

A plugin is written against this package and nothing else: the protocols a
model and a builder satisfy, the constants and field helpers a model is
declared with, the lifecycle phases a hook keys on, and the data carriers a
hook returns (assets, command lists, a state backend's registration). The
core (``cs_image_system.base``) implements the contract with its base
classes, which are the convenient implementation and not the contract
itself; a class that satisfies the protocols structurally is a first-class
plugin.

One module per kind of builder, over a shared core:

- :mod:`.core` -- what every model and every builder is to the system;
- :mod:`.runtime`, :mod:`.operating_system`, :mod:`.storage`, :mod:`.image`,
  :mod:`.instance`, :mod:`.modification`, :mod:`.group`, :mod:`.user`,
  :mod:`.state` -- the model and builder protocols of each kind;
- :mod:`.constants`, :mod:`.model_config`, :mod:`.fields`,
  :mod:`.field_kinds`, :mod:`.lifecycle`, :mod:`.lifecycles`,
  :mod:`.assets`, :mod:`.executables`, :mod:`.metadata`, :mod:`.names`,
  :mod:`.hcl` -- what a plugin declares, constructs and returns;
- :mod:`.testing` -- ``assert_conforms``, the signature-level check the
  core's tests run over every base class and every built-in plugin.

The contract imports nothing from the core: a test holds the direction.
The kind modules import :mod:`.core` and only the kinds they declare they
read.
"""
