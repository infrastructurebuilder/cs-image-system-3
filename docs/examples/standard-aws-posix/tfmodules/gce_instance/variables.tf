# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "name" {
  type = string
}

variable "zone" {
  type = string
}

variable "machine_type" {
  type    = string
  default = "e2-medium"
}

variable "image" {
  description = "Concrete image name (the pinned build); empty = latest of image_family"
  type        = string
  default     = ""
}

variable "image_family" {
  description = "Series family used when image is empty (deferred provider-specific images)"
  type        = string
  default     = ""
}

variable "subnetwork" {
  type    = string
  default = ""
}

variable "network_tags" {
  type    = list(string)
  default = []
}

variable "public_ip" {
  description = "false when the runtime's session mechanism is IAP (tunnel in, no external address)"
  type        = bool
  default     = true
}

variable "startup_script" {
  description = "Launch parameters (DESIGN N26): generated script; immutable after launch"
  type        = string
  default     = ""
}

variable "attached_disks" {
  description = "Per-instance persistent-disk attachments (N16): storage name -> { disk_self_link, device_name }"
  type = map(object({
    disk_self_link = string
    device_name    = string
  }))
  default = {}
}

variable "labels" {
  type    = map(string)
  default = {}
}
