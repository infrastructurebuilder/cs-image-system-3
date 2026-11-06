# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The words of storage a storage plugin answers with: the lifecycle
states a storage is declared in and recorded under, and the attachment
cardinality a plugin declares. The state machine (which transitions are
legal, which need the storage unattached) is the core's."""

#: Storage lifecycle states. The YAML declares the REQUESTED state; the
#: authoritative current state lives in meta-state.
STORAGE_STATE_ACTIVE = "active"
STORAGE_STATE_ARCHIVED = "archived"
STORAGE_STATE_DESTROYED = "destroyed"
STORAGE_STATES = (STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED, STORAGE_STATE_DESTROYED)

#: Attachment cardinality a storage plugin declares: how many instances may
#: mount one storage instance at a time.
CARDINALITY_SINGLE = "single"
CARDINALITY_MANY = "many"
