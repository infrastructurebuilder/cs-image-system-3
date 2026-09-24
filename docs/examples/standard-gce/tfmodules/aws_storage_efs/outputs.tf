# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "file_system_id" {
  value = local.file_system_id
}

output "access_point_ids" {
  description = "Allowed group -> access point id"
  value       = { for g, ap in aws_efs_access_point.group : g => ap.id }
}

output "public_read_access_point_id" {
  value = var.public_read ? aws_efs_access_point.public_read[0].id : null
}
