# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "name" {
  type = string
}

variable "zone" {
  type = string
}

variable "tier" {
  type    = string
  default = "BASIC_HDD"
}

variable "capacity_gb" {
  description = "Filestore minimum is 1024 GB for BASIC tiers"
  type        = number
  default     = 1024
}

variable "network" {
  type    = string
  default = "default"
}

variable "labels" {
  type    = map(string)
  default = {}
}

# Filestore has no access points: the per-group private subtrees (N13/N15)
# are created and chgrp'ed at first mount by the launch parameters. The
# allowed groups are recorded here for review only.
variable "group_subtrees" {
  type    = list(string)
  default = []
}

variable "public_read" {
  type    = bool
  default = false
}
