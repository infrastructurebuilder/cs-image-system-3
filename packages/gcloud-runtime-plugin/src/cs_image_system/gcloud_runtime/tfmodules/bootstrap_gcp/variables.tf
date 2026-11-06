# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "project" {
  type        = string
  description = "the GCP project id"
}

variable "project_number" {
  type        = string
  description = "the project's number (principal sets and the provider's full name use it)"
}

variable "pool" {
  type        = string
  description = "the workload identity pool's id"
  default     = "github"
}

variable "pool_exists" {
  type        = bool
  description = "the pool already exists: read it instead of making it"
}

variable "provider_id" {
  type        = string
  description = "the pool's GitHub provider id (`provider` is a reserved variable name in a module)"
  default     = "github"
}

variable "provider_exists" {
  type        = bool
  description = "the provider already exists: read it, never rewrite it (other repositories may share it)"
}

variable "principal_attribute" {
  type        = string
  description = "the token attribute the READ binding names: repository_id (cannot be recycled) or repository"
  default     = "repository_id"
  validation {
    condition     = contains(["repository_id", "repository"], var.principal_attribute)
    error_message = "principal_attribute must be repository_id or repository."
  }
}

variable "principal_value" {
  type        = string
  description = "the value of that attribute: the repository's numeric id, or its owner/name"
}

variable "attribute_condition" {
  type        = string
  description = "the provider's attribute condition; used only when the provider is made here"
  default     = ""
}

variable "production_branch" {
  type        = string
  description = "the branch the WRITE account trusts"
  default     = "main"
}

variable "read_account" {
  type        = string
  description = "the READ-ONLY service account's id"
}

variable "read_account_exists" {
  type        = bool
  description = "the READ-ONLY service account already exists: read it instead of making it"
}

variable "read_roles" {
  type        = list(string)
  description = "project roles the READ-ONLY account holds (each a single member added)"
  default     = ["roles/compute.viewer"]
}

variable "want_write" {
  type        = bool
  description = "CI performs on a GCE runtime: a WRITE service account is made or read"
  default     = false
}

variable "write_account" {
  type        = string
  description = "the WRITE service account's id (empty when there is none)"
  default     = ""
}

variable "write_account_exists" {
  type        = bool
  description = "the WRITE service account already exists: read it instead of making it"
  default     = false
}

variable "state_bucket" {
  type        = string
  default     = ""
  description = "the GCS state bucket, when the tree keeps its state in GCS (empty: none)"
}

variable "state_prefix" {
  type        = string
  default     = ""
  description = "the state prefix within that bucket"
}

variable "state_bucket_exists" {
  type        = bool
  default     = false
  description = "the bucket already stands (observed at every interview): the root's backend binds to it"
}

variable "state_bucket_managed" {
  type        = bool
  default     = false
  description = "this root manages the state bucket (hygiene XX item 2): made by an apply of it, versioned, uniform access, no public access, and kept here from then on; a destroy of the root removes it. False for a bucket that stood before this root"
}

variable "state_bucket_location" {
  type        = string
  default     = "US"
  description = "the bucket's location when this root makes it (a region such as us-east1, or a multi-region such as US)"
}

variable "labels" {
  type        = map(string)
  default     = {}
  description = "labels on what this root makes that carries labels (the bucket)"
}

variable "write_roles" {
  type        = list(string)
  description = "project roles the WRITE account holds (each a single member added)"
  default     = []
}
