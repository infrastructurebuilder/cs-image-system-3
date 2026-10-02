# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "repository" {
  type        = string
  description = "the repository as owner/name; it must already exist"
}

variable "default_branch" {
  type        = string
  description = "the default branch, where people push"
}

variable "production_branch" {
  type        = string
  description = "the branch the perform job runs on"
}

variable "protect_production" {
  type        = bool
  description = "a ruleset on the production branch: no deletion, no force push (an ordinary push, the perform job's, is unaffected)"
  default     = true
}

variable "variables" {
  type        = map(string)
  description = "Actions variables that are not secret"
  default     = {}
}
