# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "group_id" {
  description = "Unique name for the group; the module derives <group_id>_user / <group_id>_admin okta groups from it"
  type        = string
}

variable "members" {
  description = "Usernames attached to the user group"
  type        = list(string)
  default     = []
}

variable "admins" {
  description = "Usernames attached to the admin group"
  type        = list(string)
  default     = []
}

variable "delegated_admin_group_ids" {
  description = "Group ids delegated as resource admins on the resource group. Empty means this group's own admin group (use for the root group)."
  type        = list(string)
  default     = []
}

variable "gateway_selector" {
  description = "Gateway selector for the resource group project; empty omits it"
  type        = string
  default     = ""
}

variable "account_discovery" {
  description = "Enable account discovery on the resource group project"
  type        = bool
  default     = false
}

variable "server_labels" {
  description = "Extra server label selectors merged over the defaults (system.os_type=linux, sftd.tx.group=<group_id>)"
  type        = map(string)
  default     = {}
}
