# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The mark of a plain model field that names instances.

A foreign key (``fields.fk_field``) carries its target classification as
``FK_TARGET``, and the resolver dereferences it. A plain field whose words
name instances without being dereferenced (a storage's ``groups``, a
group's ``members``) carries it here instead, so the load reads a word the
tree wrote there in the qualified form (``<namespace>/<name>``) as the bare
word, as it reads a foreign key (``orchestrator.read_references_bare``).
"""

#: ``metadata={REFERENCE_TARGET: VCT.GROUP_MODEL}``, or a tuple of
#: classifications for a field whose word may name either kind (an image's
#: ``source_image``: a base image or an image).
REFERENCE_TARGET = "reference_target"
