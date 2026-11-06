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
- :mod:`.commands` -- the record a plugin returns from its
  ``cs_image_system.commands`` entry point to mount a command on the
  console script;
- :mod:`.modules` -- the entry-point group a plugin declares its terraform
  modules directory in (the modules are package data inside the plugin);
- :mod:`.lineage_vocabulary`, :mod:`.launch_vocabulary`,
  :mod:`.storage_vocabulary`, :mod:`.identity_vocabulary`,
  :mod:`.power_state`, :mod:`.secrets`, :mod:`.bootstrap`, :mod:`.errors`
  -- the vocabulary: the words a plugin reads and writes (tag names, the
  launch words, the storage and identity words, the power states, the type
  a secret field is declared with, the bootstrap's question model, the
  exception the core catches by type), constants and types only; the
  services behind them are the core's and reach a plugin through the run
  context;
- :mod:`.context` -- ``RunContextProtocol``, what a plugin may read of the
  run context, ``MetaStateProtocol`` and the service protocols it reaches
  as ``ctx.services.<name>`` (stage 125);
- :mod:`.testing` -- ``assert_conforms``, the signature-level check the
  core's tests run over every base class and every built-in plugin.

The contract imports nothing from the core: a test holds the direction.
The kind modules import :mod:`.core` and only the kinds they declare they
read; the core has no path of its own for a contract name.
"""
