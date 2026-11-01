# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "repository_id" {
  value       = data.github_repository.this.repo_id
  description = "the repository's numeric id: the one the federation trust conditions pin (CI_SETUP.md 3.2 step 4)"
}

output "node_id" {
  value       = data.github_repository.this.node_id
  description = "the repository's node id"
}

output "html_url" {
  value       = data.github_repository.this.html_url
  description = "the repository's page"
}
