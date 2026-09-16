# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "name" {
  description = "Name of the filesystem (creation token and Name tag)"
  type        = string
}

variable "existing_file_system_id" {
  description = "If set, no filesystem is created; the module resolves the existing one"
  type        = string
  default     = ""
}

variable "performance_mode" {
  type    = string
  default = "generalPurpose"
}

variable "encrypted" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = {}
}

# V2 group access (DESIGN Q3/N13/N15): one access point per allowed group,
# rooted at the group's private subtree, owned by the group's gid (which the
# caller passes BY REFERENCE from the identity workspace's outputs -- never a
# literal), with the subtree mode from share_mode (2770 private / 2775 read-
# shared). Mounting through the access point enforces the posix identity.
variable "access_points" {
  description = "Allowed group -> { gid, path, permissions }"
  type = map(object({
    gid         = number
    path        = string
    permissions = string
  }))
  default = {}
}

variable "public_read" {
  description = "Anyone may mount read-only (N3): a root access point is exposed; posix permissions still govern readability"
  type        = bool
  default     = false
}

# Data lifecycle (stage 15, DESIGN §3H): declared on the storage as
# {ia_days, archive_days}; realized as lifecycle policies on the filesystem
# (only one the module creates; an existing filesystem keeps its own).
variable "transition_to_ia" {
  description = "Move files not accessed for this long to Infrequent Access (AFTER_N_DAYS); empty = never"
  type        = string
  default     = ""
}

variable "transition_to_archive" {
  description = "Move files not accessed for this long to Archive (AFTER_N_DAYS); empty = never"
  type        = string
  default     = ""
}
