# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

# The GCP section of the bootstrap (cs-image-system stage 70 step 5; CI_SETUP.md 3.4):
# the workload identity pool and its GitHub provider, the READ-ONLY service
# account and the optional WRITE one, the project roles they hold and the
# workloadIdentityUser bindings that let the repository impersonate them.
# What exists is READ (a data source), never managed: a provider's condition
# may admit other repositories that share it. Every role and binding is a
# single member added, so no existing grant is replaced.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

locals {
  pool_name     = "projects/${var.project_number}/locations/global/workloadIdentityPools/${var.pool}"
  provider_name = "${local.pool_name}/providers/${var.provider_id}"

  # who may impersonate: this repository on any ref (read), and the production
  # branch alone (write; the provider's condition already limits the repository)
  read_member  = "principalSet://iam.googleapis.com/${local.pool_name}/attribute.${var.principal_attribute}/${var.principal_value}"
  write_member = "principalSet://iam.googleapis.com/${local.pool_name}/attribute.ref/refs/heads/${var.production_branch}"

  read_email  = var.read_account_exists ? data.google_service_account.read[0].email : google_service_account.read[0].email
  write_email = !var.want_write ? "" : (var.write_account_exists ? data.google_service_account.write[0].email : google_service_account.write[0].email)
}

# ------------------------------------------------------------ the pool and provider
data "google_iam_workload_identity_pool" "github" {
  count                     = var.pool_exists ? 1 : 0
  project                   = var.project
  workload_identity_pool_id = var.pool
}

resource "google_iam_workload_identity_pool" "github" {
  count                     = var.pool_exists ? 0 : 1
  project                   = var.project
  workload_identity_pool_id = var.pool
  display_name              = "GitHub Actions"
  description               = "cs-image-system CI: GitHub Actions tokens"
}

data "google_iam_workload_identity_pool_provider" "github" {
  count                              = var.provider_exists ? 1 : 0
  project                            = var.project
  workload_identity_pool_id          = var.pool
  workload_identity_pool_provider_id = var.provider_id
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = var.provider_exists ? 0 : 1
  project                            = var.project
  workload_identity_pool_id          = var.pool_exists ? var.pool : google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = var.provider_id
  display_name                       = "GitHub"
  attribute_mapping = {
    "google.subject"          = "assertion.sub"
    "attribute.repository"    = "assertion.repository"
    "attribute.repository_id" = "assertion.repository_id"
    "attribute.ref"           = "assertion.ref"
  }
  attribute_condition = var.attribute_condition
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# -------------------------------------------------------------- the READ-ONLY account
data "google_service_account" "read" {
  count      = var.read_account_exists ? 1 : 0
  project    = var.project
  account_id = var.read_account
}

resource "google_service_account" "read" {
  count        = var.read_account_exists ? 0 : 1
  project      = var.project
  account_id   = var.read_account
  display_name = "cs-image-system CI, read-only"
  description  = "what a load and the state query read"
}

resource "google_project_iam_member" "read" {
  for_each = toset(var.read_roles)
  project  = var.project
  role     = each.value
  member   = "serviceAccount:${local.read_email}"
}

resource "google_service_account_iam_member" "read" {
  service_account_id = "projects/${var.project}/serviceAccounts/${local.read_email}"
  role               = "roles/iam.workloadIdentityUser"
  member             = local.read_member
  depends_on         = [google_iam_workload_identity_pool_provider.github]
}

# ---------------------------------------------- the WRITE account, when CI performs here
data "google_service_account" "write" {
  count      = var.want_write && var.write_account_exists ? 1 : 0
  project    = var.project
  account_id = var.write_account
}

resource "google_service_account" "write" {
  count        = var.want_write && !var.write_account_exists ? 1 : 0
  project      = var.project
  account_id   = var.write_account
  display_name = "cs-image-system CI, write"
  description  = "what a bake, a release and retention do, on the production branch alone"
}

resource "google_project_iam_member" "write" {
  for_each = var.want_write ? toset(var.write_roles) : toset([])
  project  = var.project
  role     = each.value
  member   = "serviceAccount:${local.write_email}"
}

resource "google_service_account_iam_member" "write" {
  count              = var.want_write ? 1 : 0
  service_account_id = "projects/${var.project}/serviceAccounts/${local.write_email}"
  role               = "roles/iam.workloadIdentityUser"
  member             = local.write_member
  depends_on         = [google_iam_workload_identity_pool_provider.github]
}
