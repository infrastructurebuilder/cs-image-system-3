# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "name" {
  description = "Name of the volume (applied as the Name tag)"
  type        = string
}

variable "size" {
  description = "Volume size in GB"
  type        = number
  default     = 100
}

variable "volume_type" {
  type    = string
  default = "gp3"
}

variable "availability_zone" {
  description = "Availability zone the volume is created in; empty derives it from subnet_id"
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "Subnet whose availability zone is used when availability_zone is empty"
  type        = string
  default     = ""
}

variable "encrypted" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = {}
}

# archived (stage 15): a restore creates the volume FROM the archive snapshot,
# addressed by its Name tag (the snapshot is deleted after the restore and
# the id is a creation-time fact, so later plans ignore it).
variable "snapshot_name" {
  description = "Create the volume from the snapshot carrying this Name tag (the archived state's data); empty = a blank volume"
  type        = string
  default     = ""
}
