# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

# The GitHub section of the bootstrap (cs-image-system stage 70; CI_SETUP.md 3.2):
# the repository's default branch, the Actions permissions, a ruleset on the
# production branch that still lets github-actions[bot] push the records the
# perform job writes, and the Actions variables that are not secret. The
# repository itself already exists (it was forked or cloned); it is read, never
# created or destroyed by this module.

terraform {
  required_providers {
    github = {
      source  = "integrations/github"
      version = ">= 6.0"
    }
  }
}

locals {
  owner = split("/", var.repository)[0]
  name  = split("/", var.repository)[1]
}

data "github_repository" "this" {
  full_name = var.repository
}

# develop (or whatever the answer was) is where people push
resource "github_branch_default" "this" {
  repository = local.name
  branch     = var.default_branch
}

# Actions allowed; workflow permissions stay read-only because the workflow asks
# for what each job needs (id-token: write for federation, contents: write on
# perform alone)
resource "github_actions_repository_permissions" "this" {
  repository      = local.name
  enabled         = true
  allowed_actions = "all"
}

# The production branch may not be deleted or force-pushed. Neither rule stops
# an ordinary push, so the perform job's own token still pushes its records
# (fast-forward, always) and no bypass actor is needed -- nor could one be named:
# GitHub refuses the built-in Actions app as a bypass actor on a repository
# ruleset (hygiene IX item 3, found by the first live apply).
resource "github_repository_ruleset" "production" {
  count       = var.protect_production ? 1 : 0
  name        = "cs-image-system: ${var.production_branch}"
  repository  = local.name
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["refs/heads/${var.production_branch}"]
      exclude = []
    }
  }

  rules {
    deletion         = true
    non_fast_forward = true
  }
}

# Actions variables that are not secret (PERFORM_RUNTIME, GUARD_RUNTIME, AWS_REGION)
resource "github_actions_variable" "this" {
  for_each      = var.variables
  repository    = local.name
  variable_name = each.key
  value         = each.value
}
