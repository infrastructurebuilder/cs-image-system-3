# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "bucket_name" {
  type = string
}

variable "location" {
  type    = string
  default = "US"
}

variable "labels" {
  type    = map(string)
  default = {}
}

# Groups map to per-group prefixes (N13); "readable by all" is a
# project-wide viewer binding (plugin-owned semantics, N3).
variable "group_prefixes" {
  type    = list(string)
  default = []
}

variable "public_read" {
  type    = bool
  default = false
}
