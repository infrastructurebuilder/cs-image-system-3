# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "account_id" {
  type        = string
  description = "the AWS account"
}

variable "region" {
  type        = string
  description = "the AWS runtime's region"
}

variable "repository" {
  type        = string
  description = "the GitHub repository the roles trust, as owner/name"
}

variable "production_branch" {
  type        = string
  description = "the branch the WRITE role trusts"
  default     = "main"
}

variable "subject_forms" {
  type        = string
  description = "the OIDC subject forms trusted: plain (repo:owner/name), ids (repo:owner@id/name@id) or both"
  default     = "plain"
  validation {
    condition     = contains(["plain", "ids", "both"], var.subject_forms)
    error_message = "subject_forms must be plain, ids or both."
  }
}

variable "owner_id" {
  type        = string
  description = "the repository owner's numeric id (needed for the id-bearing form)"
  default     = ""
}

variable "repo_id" {
  type        = string
  description = "the repository's numeric id (needed for the id-bearing form)"
  default     = ""
}

variable "oidc_provider_exists" {
  type        = bool
  description = "the account already has the GitHub OIDC identity provider: read it instead of making it"
}

variable "read_role_name" {
  type        = string
  description = "the READ-ONLY role's name"
}

variable "write_role_name" {
  type        = string
  description = "the WRITE role's name"
}

variable "state_bucket" {
  type        = string
  description = "the state bucket"
}

variable "state_prefix" {
  type        = string
  description = "the state key prefix within the bucket, without a trailing slash"
}

variable "state_bucket_exists" {
  type        = bool
  description = "the state bucket already exists: it is not made (versioned, encrypted and private when it is)"
}

variable "instance_profile" {
  type        = string
  description = "the Session Manager instance profile's name"
}

variable "instance_profile_exists" {
  type        = bool
  description = "the instance profile already exists: read it instead of making it"
}
