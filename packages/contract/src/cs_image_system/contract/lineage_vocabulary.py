# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The words of lineage a runtime reads and writes: how the system tags
what it bakes and launches. The tag names and the fingerprint's length are
pinned by every tree's committed emission and by every image standing in
an account, so they are the contract's; the functions that read lineage
records are the core's and reach a plugin through the run context."""

#: Every tag the system writes starts with this; a tag without it is not ours.
TAG_PREFIX = "csis_"

#: An image's fingerprint TAG holds this many leading characters of the
#: input fingerprint; lineage records the whole of it. A build adopted with
#: ``state import`` has only the tag to go on.
FINGERPRINT_TAG_LENGTH = 16

#: The tag that says WHICH configuration an image belongs to. Two
#: configuration repositories may share an account: each sees the other's
#: images, and without this tag could only call them foreign.
CONFIG_TAG = f"{TAG_PREFIX}config"
