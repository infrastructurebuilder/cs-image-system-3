# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "user_group_id" {
  description = "Id of the <group_id>_user okta group"
  value       = oktapam_group.user.id
}

output "admin_group_id" {
  description = "Id of the <group_id>_admin okta group"
  value       = oktapam_group.admin.id
}

output "user_group_name" {
  value = oktapam_group.user.name
}

output "admin_group_name" {
  value = oktapam_group.admin.name
}

output "resource_group_id" {
  description = "Id of the <group_id>_rg resource group"
  value       = oktapam_resource_group.rg.id
}

output "enrollment_token" {
  description = "Launch enrollment token for the <group_id>_rg_login project; consume by remote-state reference only"
  # the provider does not mark `token` sensitive; we must
  sensitive = true
  value     = oktapam_resource_group_server_enrollment_token.login.token
}
