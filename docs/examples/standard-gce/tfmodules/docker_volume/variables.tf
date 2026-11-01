# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "name" {
  description = "Volume name (the storage's name as the daemon allows it)"
  type        = string
}

variable "driver" {
  description = "Volume driver"
  type        = string
  default     = "local"
}

variable "driver_opts" {
  description = "Driver options"
  type        = map(string)
  default     = {}
}

variable "labels" {
  description = "Labels fixed at creation: the storage, the configuration id, the allowed groups"
  type        = map(string)
  default     = {}
}

# V2 group access (N13/N15) happens at first launch: the launch script
# creates the per-group subtree under the mount point and chgrps it.
