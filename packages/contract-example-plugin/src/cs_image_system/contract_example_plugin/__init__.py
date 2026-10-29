# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The proof of the plugin contract (stage 30, branch 2): the ``inmem``
state backend, a plugin written against ``cs_image_system.contract`` and
nothing else of the system.

OpenTofu's ``inmem`` backend keeps a workspace's state in the running
process's memory: no bucket, no file, no credentials, gone when the
process ends. It is the smallest real backend there is, which makes it
the right subject for a proof: every line here is contract, nothing is
borrowed from the core. The model and the builder satisfy the contract's
protocols structurally -- they subclass none of the core's base classes
-- and the registry, the mapper, the runner and the terraform collector
drive them exactly as they drive the built-in state plugins.
"""
