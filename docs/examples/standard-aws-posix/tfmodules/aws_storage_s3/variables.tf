# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "bucket_name" {
  description = "Bucket name (globally unique)"
  type        = string
}

variable "force_destroy" {
  description = "Allow terraform to delete a non-empty bucket (the storage state machine wipes it first)"
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}

# V2 group access, plugin-owned mapping for a non-POSIX store (DESIGN N3/N13):
# each allowed group owns a top-level prefix ("<group>/"); public_read grants
# read-only object access to every principal of the bucket's own account.
variable "group_prefixes" {
  description = "Allowed groups; each gets a top-level prefix marker object"
  type        = list(string)
  default     = []
}

variable "public_read" {
  description = "Read-only access for all principals in this account"
  type        = bool
  default     = false
}

# Data lifecycle (stage 15, DESIGN §3H): declared on the storage as
# {transition_days, storage_class, expire_days, prefix}; realized as one rule.
variable "lifecycle_rules" {
  description = "Data lifecycle rules: transition after N days to a storage class and/or expire after N days (0 = none)"
  type = list(object({
    id              = string
    prefix          = string
    transition_days = number
    storage_class   = string
    expire_days     = number
  }))
  default = []
}
