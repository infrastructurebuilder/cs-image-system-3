# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "name" {
  description = "Disk name (also the device_name under /dev/disk/by-id/google-<name>)"
  type        = string
}

variable "zone" {
  type = string
}

variable "size" {
  description = "Size in GB"
  type        = number
  default     = 100
}

variable "disk_type" {
  type    = string
  default = "pd-balanced"
}

variable "labels" {
  type    = map(string)
  default = {}
}

# V2 group access (N13/N15) happens at first mount: the launch parameters
# create the per-group subtree and chgrp it to the gid by reference.
variable "snapshot" {
  description = "Create the disk FROM this snapshot (the archived state's data, stage 11.6); empty = a blank disk"
  type        = string
  default     = ""
}
