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

# Mount targets (stage 19). An EFS filesystem is only reachable through a mount
# target: an ENI in one subnet per availability zone. Without them `mount.efs`
# cannot even resolve the filesystem's DNS name, which is what this module
# produced until 2026-09-20 -- a filesystem nothing could mount.
variable "vpc_id" {
  type        = string
  description = "VPC the mount targets live in; empty creates none"
  default     = ""
}

variable "mount_target_subnet_ids" {
  type        = list(string)
  description = "One subnet per availability zone. EFS permits a single mount target per zone, so these must not share one."
  default     = []
}

variable "client_security_group_ids" {
  type        = list(string)
  description = "Security groups whose members may mount: NFS ingress is granted to these groups BY REFERENCE, never to a CIDR, so no shared range is opened."
  default     = []
}
